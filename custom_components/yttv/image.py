"""Per-channel image entities exposing the current airing thumbnail."""

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
)
from .coordinator import YttvCoordinator

_LOGGER = logging.getLogger(__name__)


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
        new: list[YttvChannelImage] = []
        for ch in coordinator.channels():
            name = ch.get("name")
            if not name or name in known:
                continue
            known.add(name)
            new.append(
                YttvChannelImage(
                    hass, coordinator, entry, name, slugify(name) in pinned_slugs
                )
            )
        if new:
            async_add_entities(new)

    _sync_entities()
    entry.async_on_unload(coordinator.async_add_listener(_sync_entities))


@callback
def _sync_registry_disabled(
    hass: HomeAssistant, entry: ConfigEntry, pinned_slugs: set[str]
) -> None:
    prefix = f"{entry.entry_id}:channel_image:"
    registry = er.async_get(hass)
    for reg in er.async_entries_for_config_entry(registry, entry.entry_id):
        if reg.domain != "image" or not (reg.unique_id or "").startswith(prefix):
            continue
        slug = reg.unique_id[len(prefix):]
        desired = None if slug in pinned_slugs else er.RegistryEntryDisabler.INTEGRATION
        if reg.disabled_by == desired:
            continue
        if reg.disabled_by not in (None, er.RegistryEntryDisabler.INTEGRATION):
            continue
        registry.async_update_entity(reg.entity_id, disabled_by=desired)


class YttvChannelImage(CoordinatorEntity[YttvCoordinator], ImageEntity):
    _attr_has_entity_name = False
    _attr_content_type = "image/jpeg"

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
        self._attr_unique_id = f"{entry.entry_id}:channel_image:{slug}"
        self._attr_name = f"yttv {channel_name}"
        self._attr_entity_registry_enabled_default = pinned
        self._refresh_url()

    def _resolve_url(self) -> str | None:
        ch = self.coordinator.find_channel(self._channel_name)
        if not ch:
            return None
        cur = ch.get("current_airing")
        if isinstance(cur, dict):
            thumb = cur.get("thumbnail_url")
            if thumb:
                return thumb
        return ch.get("icon_url") or None

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
