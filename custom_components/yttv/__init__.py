"""yttv-bridge integration entry points."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry

from .api import BridgeClient, BridgeError
from .const import (
    ATTR_CHANNEL,
    ATTR_DEVICE,
    CONF_BRIDGE_URL,
    DOMAIN,
    SERVICE_CAST,
    SERVICE_STOP,
)
from .coordinator import YttvCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.MEDIA_PLAYER, Platform.SENSOR, Platform.IMAGE]

CAST_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE): cv.entity_id,
        vol.Required(ATTR_CHANNEL): cv.string,
    }
)

STOP_SCHEMA = vol.Schema({vol.Required(ATTR_DEVICE): cv.entity_id})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a bridge instance."""
    session = async_get_clientsession(hass)
    client = BridgeClient(session, entry.data[CONF_BRIDGE_URL])
    coordinator = YttvCoordinator(hass, client)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_reload_on_options))
    _async_register_services(hass)
    return True


async def _async_reload_on_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when the user changes options (e.g. enable_sensors, pinned_channels)."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Tear down a bridge instance."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_CAST)
            hass.services.async_remove(DOMAIN, SERVICE_STOP)
    return unloaded


def _resolve_target(
    hass: HomeAssistant, entity_id: str
) -> tuple[YttvCoordinator, str, int]:
    """media_player.<...> → (coordinator, host, port)."""
    registry = async_get_entity_registry(hass)
    entry = registry.async_get(entity_id)
    if entry is None or entry.platform != DOMAIN:
        raise HomeAssistantError(f"{entity_id} is not a yttv entity")
    coordinator: YttvCoordinator | None = hass.data.get(DOMAIN, {}).get(
        entry.config_entry_id
    )
    if coordinator is None:
        raise HomeAssistantError(f"{entity_id}: bridge not loaded")
    # unique_id format: "<entry_id>:<host>:<port>"
    parts = (entry.unique_id or "").rsplit(":", 2)
    if len(parts) != 3:
        raise HomeAssistantError(f"{entity_id}: malformed unique_id")
    _, host, port_s = parts
    try:
        port = int(port_s)
    except ValueError as err:
        raise HomeAssistantError(f"{entity_id}: bad port") from err
    return coordinator, host, port


def _async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_CAST):
        return

    async def _cast(call: ServiceCall) -> None:
        coord, host, port = _resolve_target(hass, call.data[ATTR_DEVICE])
        try:
            await coord.client.cast(
                host=host, port=port, channel=call.data[ATTR_CHANNEL]
            )
        except BridgeError as err:
            raise HomeAssistantError(f"yttv cast failed: {err}") from err

    async def _stop(call: ServiceCall) -> None:
        coord, host, port = _resolve_target(hass, call.data[ATTR_DEVICE])
        try:
            await coord.client.stop(host=host, port=port)
        except BridgeError as err:
            raise HomeAssistantError(f"yttv stop failed: {err}") from err

    hass.services.async_register(DOMAIN, SERVICE_CAST, _cast, schema=CAST_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_STOP, _stop, schema=STOP_SCHEMA)
