"""Per-channel "what's airing now" sensors."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

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
        new: list[YttvChannelSensor] = []
        for ch in coordinator.channels():
            name = ch.get("name")
            if not name or name in known:
                continue
            known.add(name)
            new.append(
                YttvChannelSensor(
                    coordinator, entry, name, slugify(name) in pinned_slugs
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
    prefix = f"{entry.entry_id}:channel:"
    registry = er.async_get(hass)
    for reg in er.async_entries_for_config_entry(registry, entry.entry_id):
        if reg.domain != "sensor" or not (reg.unique_id or "").startswith(prefix):
            continue
        slug = reg.unique_id[len(prefix):]
        desired = None if slug in pinned_slugs else er.RegistryEntryDisabler.INTEGRATION
        if reg.disabled_by == desired:
            continue
        if reg.disabled_by not in (None, er.RegistryEntryDisabler.INTEGRATION):
            continue
        registry.async_update_entity(reg.entity_id, disabled_by=desired)


class YttvChannelSensor(CoordinatorEntity[YttvCoordinator], SensorEntity):
    """State = current airing title; attributes = airing details."""

    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator: YttvCoordinator,
        entry: ConfigEntry,
        channel_name: str,
        pinned: bool,
    ) -> None:
        super().__init__(coordinator)
        self._channel_name = channel_name
        slug = slugify(channel_name) or "unknown"
        self._attr_unique_id = f"{entry.entry_id}:channel:{slug}"
        self._attr_name = f"yttv {channel_name}"
        self._attr_entity_registry_enabled_default = pinned

    def _channel(self) -> dict[str, Any] | None:
        return self.coordinator.find_channel(self._channel_name)

    def _airing(self) -> dict[str, Any] | None:
        ch = self._channel()
        if not ch:
            return None
        cur = ch.get("current_airing")
        return cur if isinstance(cur, dict) else None

    @property
    def available(self) -> bool:
        return super().available and self._channel() is not None

    @property
    def native_value(self) -> str | None:
        airing = self._airing()
        return airing.get("title") if airing else None

    @property
    def entity_picture(self) -> str | None:
        airing = self._airing()
        return airing.get("thumbnail_url") if airing else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        ch = self._channel() or {}
        airing = self._airing() or {}
        return {
            "channel": ch.get("name"),
            "station_icon": ch.get("icon_url"),
            "synopsis": airing.get("synopsis"),
            "subtitle": airing.get("subtitle"),
            "starts_at": airing.get("starts_at"),
            "ends_at": airing.get("ends_at"),
            "is_live": airing.get("is_live"),
            "video_id": airing.get("video_id"),
        }
