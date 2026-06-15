"""DataUpdateCoordinator that polls /snapshot."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import BridgeClient, BridgeError
from .const import DOMAIN, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)


class YttvCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Owns a single bridge client and the shared snapshot."""

    def __init__(self, hass: HomeAssistant, client: BridgeClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            snap = await self.client.snapshot()
        except BridgeError as err:
            raise UpdateFailed(str(err)) from err
        # Defensive: bridge guarantees the keys, but normalize for downstream.
        snap.setdefault("channels", [])
        snap.setdefault("devices", [])
        return snap

    def devices(self) -> list[dict[str, Any]]:
        return list(self.data.get("devices", [])) if self.data else []

    def channels(self) -> list[dict[str, Any]]:
        return list(self.data.get("channels", [])) if self.data else []

    def channel_names(self) -> list[str]:
        return [c["name"] for c in self.channels() if c.get("name")]

    def find_channel(self, name: str) -> dict[str, Any] | None:
        for ch in self.channels():
            if ch.get("name") == name:
                return ch
        return None
