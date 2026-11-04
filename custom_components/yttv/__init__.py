"""yttv-bridge integration entry points."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry

from .api import BridgeClient, BridgeError
from .const import (
    ATTR_CHANNEL,
    ATTR_DEVICE,
    ATTR_VIDEO_ID,
    CONF_BRIDGE_URL,
    CONF_PINNED_CHANNELS,
    DOMAIN,
    SERVICE_CAST,
    SERVICE_GUIDE,
    SERVICE_STOP,
)
from .coordinator import YttvCoordinator
from .guide import guide
from .media_player import _device_uid

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.MEDIA_PLAYER, Platform.SENSOR, Platform.IMAGE]

CAST_SCHEMA = vol.All(
    vol.Schema(
        {
            vol.Required(ATTR_DEVICE): cv.entity_id,
            vol.Optional(ATTR_CHANNEL): cv.string,
            vol.Optional(ATTR_VIDEO_ID): cv.string,
        }
    ),
    cv.has_at_least_one_key(ATTR_CHANNEL, ATTR_VIDEO_ID),
)

STOP_SCHEMA = vol.Schema({vol.Required(ATTR_DEVICE): cv.entity_id})

GUIDE_SCHEMA = vol.Schema({vol.Optional("start", default=0): vol.Coerce(int)})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a bridge instance."""
    session = async_get_clientsession(hass)
    client = BridgeClient(session, entry.data[CONF_BRIDGE_URL])
    coordinator = YttvCoordinator(hass, client)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Live status push (SSE); the coordinator's poll remains as a fallback.
    entry.async_create_background_task(
        hass, coordinator.consume_events(), name=f"{DOMAIN}_events"
    )

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
            hass.services.async_remove(DOMAIN, SERVICE_GUIDE)
    return unloaded


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: ConfigEntry, device_entry: DeviceEntry
) -> bool:
    """Allow deleting a device from the UI once it's no longer present."""
    coordinator: YttvCoordinator | None = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coordinator is None:
        return True
    present = {d.get("uuid") for d in coordinator.devices() if d.get("uuid")}
    ours = {ident for dom, ident in device_entry.identifiers if dom == DOMAIN}
    return ours.isdisjoint(present)


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
    # unique_id is "<entry_id>:<device-uuid>"; resolve current host/port.
    key = (entry.unique_id or "").removeprefix(f"{entry.config_entry_id}:")
    for d in coordinator.devices():
        if d.get("uuid") == key:
            return coordinator, d["host"], d.get("port") or 8009
    raise HomeAssistantError(f"{entity_id}: device not currently available")


def _async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_CAST):
        return

    async def _cast(call: ServiceCall) -> None:
        coord, host, port = _resolve_target(hass, call.data[ATTR_DEVICE])
        try:
            await coord.client.cast(
                host=host,
                port=port,
                channel=call.data.get(ATTR_CHANNEL, ""),
                video_id=call.data.get(ATTR_VIDEO_ID, ""),
            )
        except BridgeError as err:
            raise HomeAssistantError(f"yttv cast failed: {err}") from err

    async def _stop(call: ServiceCall) -> None:
        coord, host, port = _resolve_target(hass, call.data[ATTR_DEVICE])
        try:
            await coord.client.stop(host=host, port=port)
        except BridgeError as err:
            raise HomeAssistantError(f"yttv stop failed: {err}") from err

    async def _guide(call: ServiceCall) -> ServiceResponse:
        loaded = list(hass.data.get(DOMAIN, {}).items())
        if not loaded:
            raise HomeAssistantError("yttv bridge not loaded")
        entry_id, coord = loaded[0]
        entry = hass.config_entries.async_get_entry(entry_id)
        pinned = set((entry.options.get(CONF_PINNED_CHANNELS) if entry else None) or [])
        return guide(coord.channels(), pinned, call.data["start"], _tvs(hass, entry_id, coord))

    hass.services.async_register(DOMAIN, SERVICE_CAST, _cast, schema=CAST_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_STOP, _stop, schema=STOP_SCHEMA)
    hass.services.async_register(
        DOMAIN,
        SERVICE_GUIDE,
        _guide,
        schema=GUIDE_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )


def _tvs(hass: HomeAssistant, entry_id: str, coord: YttvCoordinator) -> list[dict[str, Any]]:
    registry = async_get_entity_registry(hass)
    out = []
    for dev in coord.devices():
        uid = _device_uid(dev)
        if not uid or not dev.get("video"):
            continue
        entity = registry.async_get_entity_id("media_player", DOMAIN, f"{entry_id}:{uid}")
        if entity:
            out.append(
                {
                    "entity_id": entity,
                    "name": dev.get("name") or "",
                    "uuid": dev.get("uuid") or "",
                    "host": dev.get("host") or "",
                }
            )
    return out
