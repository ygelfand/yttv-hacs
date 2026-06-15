"""media_player entities backed by the bridge snapshot."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import BridgeError
from .const import DOMAIN
from .coordinator import YttvCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: YttvCoordinator = hass.data[DOMAIN][entry.entry_id]
    known: set[str] = set()

    @callback
    def _sync_entities() -> None:
        new: list[YttvMediaPlayer] = []
        for dev in coordinator.devices():
            uid = _device_uid(dev)
            if not uid or uid in known:
                continue
            known.add(uid)
            new.append(YttvMediaPlayer(coordinator, entry, dev))
        if new:
            async_add_entities(new)

    _sync_entities()
    entry.async_on_unload(coordinator.async_add_listener(_sync_entities))


def _device_uid(dev: dict[str, Any]) -> str | None:
    host = dev.get("host")
    port = dev.get("port") or 8009
    if not host:
        return None
    return f"{host}:{port}"


class YttvMediaPlayer(CoordinatorEntity[YttvCoordinator], MediaPlayerEntity):
    """One entity per Chromecast known to the bridge."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_supported_features = (
        MediaPlayerEntityFeature.SELECT_SOURCE | MediaPlayerEntityFeature.STOP
    )

    def __init__(
        self,
        coordinator: YttvCoordinator,
        entry: ConfigEntry,
        device: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry.entry_id
        self._device_name = device["name"]
        self._host = device["host"]
        self._port = device.get("port") or 8009
        self._attr_unique_id = f"{entry.entry_id}:{self._host}:{self._port}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{self._host}:{self._port}")},
            name=self._device_name,
            manufacturer="Google",
            model="Chromecast",
            via_device=(DOMAIN, entry.entry_id),
        )

    @property
    def available(self) -> bool:
        return super().available and self._current_device() is not None

    @property
    def state(self) -> MediaPlayerState:
        # Bridge doesn't push playback state in v0.1, so default to idle.
        return MediaPlayerState.IDLE

    @property
    def source(self) -> str | None:
        # No playback feedback from the bridge yet — leave unknown.
        return None

    @property
    def source_list(self) -> list[str]:
        return self.coordinator.channel_names()

    def _current_device(self) -> dict[str, Any] | None:
        for dev in self.coordinator.devices():
            if dev.get("host") == self._host and (dev.get("port") or 8009) == self._port:
                return dev
        return None

    async def async_select_source(self, source: str) -> None:
        try:
            await self.coordinator.client.cast(
                host=self._host, port=self._port, channel=source
            )
        except BridgeError as err:
            raise HomeAssistantError(f"yttv cast failed: {err}") from err

    async def async_media_stop(self) -> None:
        try:
            await self.coordinator.client.stop(host=self._host, port=self._port)
        except BridgeError as err:
            raise HomeAssistantError(f"yttv stop failed: {err}") from err
