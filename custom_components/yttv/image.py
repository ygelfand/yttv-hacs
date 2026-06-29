"""Per-channel image entities: current-airing artwork and a live frame."""

from __future__ import annotations

import logging

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util, slugify

from .const import (
    CONF_ENABLE_SENSORS,
    CONF_PINNED_CHANNELS,
    DEFAULT_ENABLE_SENSORS,
    DOMAIN,
    LIVE_THUMB_TTL,
)
from .coordinator import YttvCoordinator

_LOGGER = logging.getLogger(__name__)

_UID_KINDS = ("channel_image", "channel_live_image")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    if not entry.options.get(CONF_ENABLE_SENSORS, DEFAULT_ENABLE_SENSORS):
        return

    coordinator: YttvCoordinator = hass.data[DOMAIN][entry.entry_id]
    known: set[str] = set()

    def _pinned_slugs() -> set[str]:
        return {
            slugify(n) for n in (entry.options.get(CONF_PINNED_CHANNELS) or []) if n
        }

    _sync_registry_disabled(hass, entry, _pinned_slugs())

    @callback
    def _sync_entities() -> None:
        pinned_slugs = _pinned_slugs()
        new: list[ImageEntity] = []
        for ch in coordinator.channels():
            name = ch.get("name")
            if not name or name in known:
                continue
            known.add(name)
            pinned = slugify(name) in pinned_slugs
            new.append(YttvChannelImage(hass, coordinator, entry, name, pinned))
            new.append(YttvChannelLiveImage(hass, coordinator, entry, name, pinned))
        if new:
            async_add_entities(new)

    _sync_entities()
    entry.async_on_unload(coordinator.async_add_listener(_sync_entities))


@callback
def _sync_registry_disabled(
    hass: HomeAssistant, entry: ConfigEntry, pinned_slugs: set[str]
) -> None:
    prefixes = tuple(f"{entry.entry_id}:{kind}:" for kind in _UID_KINDS)
    registry = er.async_get(hass)
    for reg in er.async_entries_for_config_entry(registry, entry.entry_id):
        if reg.domain != "image":
            continue
        uid = reg.unique_id or ""
        prefix = next((p for p in prefixes if uid.startswith(p)), None)
        if prefix is None:
            continue
        slug = uid[len(prefix):]
        desired = None if slug in pinned_slugs else er.RegistryEntryDisabler.INTEGRATION
        if reg.disabled_by == desired:
            continue
        if reg.disabled_by not in (None, er.RegistryEntryDisabler.INTEGRATION):
            continue
        registry.async_update_entity(reg.entity_id, disabled_by=desired)


class _YttvChannelImageBase(CoordinatorEntity[YttvCoordinator], ImageEntity):
    _attr_has_entity_name = False
    _attr_content_type = "image/jpeg"
    _uid_kind = "channel_image"
    _name_suffix = ""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: YttvCoordinator,
        entry: ConfigEntry,
        channel_name: str,
        pinned: bool,
    ) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        ImageEntity.__init__(self, hass)
        self._channel_name = channel_name
        slug = slugify(channel_name) or "unknown"
        self._attr_unique_id = f"{entry.entry_id}:{self._uid_kind}:{slug}"
        self._attr_name = f"yttv {channel_name}{self._name_suffix}"
        self._attr_entity_registry_enabled_default = pinned
        self._refresh_url()

    def _resolve_url(self) -> str | None:
        raise NotImplementedError

    def _refresh_url(self) -> bool:
        url = self._resolve_url()
        if url == self._attr_image_url:
            return False
        self._attr_image_url = url
        self._attr_image_last_updated = dt_util.utcnow() if url else None
        return True

    @callback
    def _handle_coordinator_update(self) -> None:
        self._refresh_url()
        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        return (
            super().available
            and self.coordinator.find_channel(self._channel_name) is not None
        )


class YttvChannelImage(_YttvChannelImageBase):
    """Static program artwork for the current airing (icon as fallback)."""

    _uid_kind = "channel_image"

    def _resolve_url(self) -> str | None:
        ch = self.coordinator.find_channel(self._channel_name)
        if not ch:
            return None
        cur = ch.get("current_airing")
        if isinstance(cur, dict) and cur.get("thumbnail_url"):
            return cur["thumbnail_url"]
        return ch.get("icon_url") or None


class YttvChannelLiveImage(_YttvChannelImageBase):
    """A frame of the channel's live broadcast. No image when nothing is live."""

    _uid_kind = "channel_live_image"
    _name_suffix = " live"

    def _resolve_url(self) -> str | None:
        ch = self.coordinator.find_channel(self._channel_name)
        if not ch:
            return None
        live = ch.get("live_thumbnail_url")
        if not live:
            return None
        # Stable URL, but content updates ~every 5 min. A bucketed ?ts= rolls the
        # URL once per window so _refresh_url re-fetches a fresh frame (and busts
        # ytimg's edge cache) without per-poll churn.
        bucket = int(dt_util.utcnow().timestamp() // LIVE_THUMB_TTL)
        return f"{live}?ts={bucket}"
