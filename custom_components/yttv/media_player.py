"""media_player entities backed by the bridge snapshot."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
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
    """Stable per-device key (mDNS UUID, survives IP changes)."""
    return dev.get("uuid") or None


class YttvMediaPlayer(CoordinatorEntity[YttvCoordinator], MediaPlayerEntity):
    """One entity per Chromecast known to the bridge."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_supported_features = (
        MediaPlayerEntityFeature.SELECT_SOURCE
        | MediaPlayerEntityFeature.STOP
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.PLAY
        | MediaPlayerEntityFeature.PAUSE
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
        self._uuid = device.get("uuid") or ""
        self._host = device["host"]
        self._port = device.get("port") or 8009
        uid = _device_uid(device)
        self._attr_unique_id = f"{entry.entry_id}:{uid}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, uid)},
            name=f"yttv {self._device_name}",
            manufacturer="Google",
            model="Chromecast",
            via_device=(DOMAIN, entry.entry_id),
        )

    @property
    def available(self) -> bool:
        return super().available and self._current_device() is not None

    _STATES = {
        "PLAYING": MediaPlayerState.PLAYING,
        "PAUSED": MediaPlayerState.PAUSED,
        "BUFFERING": MediaPlayerState.BUFFERING,
    }

    @property
    def state(self) -> MediaPlayerState:
        st = self._status()
        if st is None or st.get("idle"):
            return MediaPlayerState.IDLE
        return self._STATES.get((st.get("player_state") or "").upper(), MediaPlayerState.IDLE)

    @property
    def source(self) -> str | None:
        # Prefer the matched channel; fall back to the app name.
        st = self._status() or {}
        return st.get("channel") or st.get("app") or None

    @property
    def source_list(self) -> list[str]:
        return self.coordinator.channel_names()

    @property
    def media_title(self) -> str | None:
        return (self._status() or {}).get("title") or None

    @property
    def media_content_type(self) -> str | None:
        return MediaType.CHANNEL if self._status() else None

    @property
    def media_image_url(self) -> str | None:
        return (self._status() or {}).get("image_url") or None

    @property
    def volume_level(self) -> float | None:
        st = self._status()
        return st.get("volume") if st else None

    @property
    def is_volume_muted(self) -> bool | None:
        st = self._status()
        return st.get("muted") if st else None

    def _current_device(self) -> dict[str, Any] | None:
        for dev in self.coordinator.devices():
            if dev.get("uuid") == self._uuid:
                return dev
        return None

    def _status(self) -> dict[str, Any] | None:
        dev = self._current_device()
        if not dev:
            return None
        st = dev.get("status")
        return st if isinstance(st, dict) else None

    def _target(self) -> tuple[str, int]:
        """Current host/port, re-resolved so DHCP changes are honored."""
        dev = self._current_device()
        if dev:
            self._host = dev["host"]
            self._port = dev.get("port") or 8009
        return self._host, self._port

    async def async_select_source(self, source: str) -> None:
        host, port = self._target()
        try:
            await self.coordinator.client.cast(host=host, port=port, channel=source)
        except BridgeError as err:
            raise HomeAssistantError(f"yttv cast failed: {err}") from err

    async def async_media_stop(self) -> None:
        host, port = self._target()
        try:
            await self.coordinator.client.stop(host=host, port=port)
        except BridgeError as err:
            raise HomeAssistantError(f"yttv stop failed: {err}") from err

    async def async_set_volume_level(self, volume: float) -> None:
        host, port = self._target()
        try:
            await self.coordinator.client.set_volume(host=host, port=port, level=volume)
        except BridgeError as err:
            raise HomeAssistantError(f"yttv volume failed: {err}") from err
        await self.coordinator.async_request_refresh()

    async def async_mute_volume(self, mute: bool) -> None:
        host, port = self._target()
        try:
            await self.coordinator.client.set_muted(host=host, port=port, muted=mute)
        except BridgeError as err:
            raise HomeAssistantError(f"yttv mute failed: {err}") from err
        await self.coordinator.async_request_refresh()

    async def async_media_play(self) -> None:
        await self._play_pause()

    async def async_media_pause(self) -> None:
        await self._play_pause()

    async def _play_pause(self) -> None:
        host, port = self._target()
        try:
            await self.coordinator.client.play_pause(host=host, port=port)
        except BridgeError as err:
            raise HomeAssistantError(f"yttv play/pause failed: {err}") from err
        await self.coordinator.async_request_refresh()
