"""Config flow for yttv-bridge."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import BridgeAuthError, BridgeClient, BridgeError
from .const import (
    CONF_BRIDGE_URL,
    CONF_ENABLE_SENSORS,
    CONF_PINNED_CHANNELS,
    DEFAULT_BRIDGE_URL,
    DEFAULT_ENABLE_SENSORS,
    DOMAIN,
)
from .coordinator import YttvCoordinator

STEP_USER_SCHEMA = vol.Schema(
    {vol.Required(CONF_BRIDGE_URL, default=DEFAULT_BRIDGE_URL): str}
)


class YttvConfigFlow(ConfigFlow, domain=DOMAIN):
    """Single-step flow: ask for the bridge URL, probe /healthz."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            url = user_input[CONF_BRIDGE_URL].strip().rstrip("/")
            await self.async_set_unique_id(url)
            self._abort_if_unique_id_configured()

            client = BridgeClient(async_get_clientsession(self.hass), url)
            try:
                await client.healthz()
            except BridgeAuthError:
                errors["base"] = "auth"
            except BridgeError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=f"yttv-bridge ({url})",
                    data={CONF_BRIDGE_URL: url},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return YttvOptionsFlow(entry)


class YttvOptionsFlow(OptionsFlow):
    """Toggle per-channel sensors and pick which channels are pinned."""

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        coordinator: YttvCoordinator | None = self.hass.data.get(DOMAIN, {}).get(
            self._entry.entry_id
        )
        channels = sorted(coordinator.channel_names()) if coordinator else []

        current_enabled = self._entry.options.get(
            CONF_ENABLE_SENSORS, DEFAULT_ENABLE_SENSORS
        )
        current_pinned = self._entry.options.get(CONF_PINNED_CHANNELS, []) or []
        # Channels the user has pinned but the bridge no longer reports —
        # keep them as options so the user can intentionally remove them.
        option_values = sorted(set(channels) | set(current_pinned))

        schema = vol.Schema(
            {
                vol.Required(CONF_ENABLE_SENSORS, default=current_enabled): bool,
                vol.Optional(
                    CONF_PINNED_CHANNELS, default=current_pinned
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=option_values,
                        multiple=True,
                        custom_value=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
