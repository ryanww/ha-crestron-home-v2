"""Config flow for the Crestron Home (CRPC bridge) integration."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import AbortFlow, FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector

from .api import (
    CrpcBridgeAuthError,
    CrpcBridgeClient,
    CrpcBridgeConnectionError,
    CrpcBridgeError,
)
from .const import (
    ALL_DEVICE_TYPES,
    CONF_API_TOKEN,
    CONF_ENABLED_DEVICE_TYPES,
    CONF_HOST,
    CONF_IGNORED_DEVICE_NAMES,
    CONF_PORT,
    DEFAULT_IGNORED_DEVICE_NAMES,
    DEFAULT_PORT,
    DEVICE_TYPE_BINARY_SENSOR,
    DEVICE_TYPE_CLIMATE,
    DEVICE_TYPE_LIGHT,
    DEVICE_TYPE_MEDIA_PLAYER,
    DEVICE_TYPE_SCENE,
    DEVICE_TYPE_SHADE,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

DEVICE_TYPE_OPTIONS = [
    {"value": DEVICE_TYPE_LIGHT, "label": "Lights"},
    {"value": DEVICE_TYPE_SHADE, "label": "Shades"},
    {"value": DEVICE_TYPE_SCENE, "label": "Scenes"},
    {"value": DEVICE_TYPE_CLIMATE, "label": "Thermostats"},
    {"value": DEVICE_TYPE_MEDIA_PLAYER, "label": "Media Players"},
    {"value": DEVICE_TYPE_BINARY_SENSOR, "label": "Doors"},
]


async def validate_input(hass: HomeAssistant, data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate the user input allows us to connect to the bridge."""
    client = CrpcBridgeClient(
        hass=hass,
        host=data[CONF_HOST],
        port=data.get(CONF_PORT, DEFAULT_PORT),
        api_token=data.get(CONF_API_TOKEN, ""),
    )

    try:
        status = await client.get_status()
    except CrpcBridgeConnectionError as error:
        raise CannotConnect from error
    except CrpcBridgeAuthError as error:
        raise InvalidAuth from error
    except CrpcBridgeError as error:
        raise CannotConnect from error

    if not status.get("connected", False):
        _LOGGER.warning(
            "CRPC bridge is reachable but not connected to the Crestron "
            "processor yet; continuing setup"
        )

    return {"title": f"Crestron Home ({client.bridge_id})"}


class CrestronHomeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Crestron Home via the CRPC bridge."""

    VERSION = 2

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> CrestronHomeOptionsFlowHandler:
        """Get the options flow for this handler."""
        return CrestronHomeOptionsFlowHandler()

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)

                if CONF_ENABLED_DEVICE_TYPES not in user_input:
                    user_input[CONF_ENABLED_DEVICE_TYPES] = list(ALL_DEVICE_TYPES)

                await self.async_set_unique_id(
                    f"{user_input[CONF_HOST]}:{user_input.get(CONF_PORT, DEFAULT_PORT)}"
                )
                self._abort_if_unique_id_configured()

                return self.async_create_entry(title=info["title"], data=user_input)

            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except AbortFlow:
                raise
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Required(
                        CONF_PORT, default=DEFAULT_PORT
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1,
                            max=65535,
                            mode=selector.NumberSelectorMode.BOX,
                        ),
                    ),
                    vol.Optional(
                        CONF_ENABLED_DEVICE_TYPES, default=list(ALL_DEVICE_TYPES)
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=DEVICE_TYPE_OPTIONS,
                            multiple=True,
                            mode=selector.SelectSelectorMode.LIST,
                        ),
                    ),
                    vol.Optional(
                        CONF_IGNORED_DEVICE_NAMES,
                        default=DEFAULT_IGNORED_DEVICE_NAMES,
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(
                            multiple=True,
                        ),
                    ),
                }
            ),
            errors=errors,
        )


class CrestronHomeOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle Crestron Home options.

    Uses the OptionsFlow.config_entry property provided by Home Assistant
    (2024.11+); do not assign it explicitly.
    """

    async def async_step_init(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Manage the options."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            try:
                client = CrpcBridgeClient(
                    hass=self.hass,
                    host=self.config_entry.data[CONF_HOST],
                    port=self.config_entry.data.get(CONF_PORT, DEFAULT_PORT),
                    api_token=self.config_entry.data.get(CONF_API_TOKEN, ""),
                )
                await client.get_status()

                return self.async_create_entry(title="", data=user_input)

            except CrpcBridgeConnectionError:
                errors["base"] = "cannot_connect"
            except CrpcBridgeAuthError:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        current_enabled_types = self.config_entry.data.get(
            CONF_ENABLED_DEVICE_TYPES, list(ALL_DEVICE_TYPES)
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ENABLED_DEVICE_TYPES, default=current_enabled_types
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=DEVICE_TYPE_OPTIONS,
                            multiple=True,
                            mode=selector.SelectSelectorMode.LIST,
                        ),
                    ),
                    vol.Optional(
                        CONF_IGNORED_DEVICE_NAMES,
                        default=self.config_entry.data.get(
                            CONF_IGNORED_DEVICE_NAMES, DEFAULT_IGNORED_DEVICE_NAMES
                        ),
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(
                            multiple=True,
                        ),
                    ),
                }
            ),
            errors=errors,
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
