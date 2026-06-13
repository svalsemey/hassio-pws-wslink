"""Config flow for Weather Station integration."""

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError

from .const import (
    API_ID,
    API_KEY,
    DEV_DBG,
    DOMAIN,
    INVALID_CREDENTIALS,
    SENSORS_TO_LOAD,
    WSLINK,
)


class CannotConnect(HomeAssistantError):
    """We can not connect. - not used in push mechanism."""


class InvalidAuth(HomeAssistantError):
    """Invalid auth exception."""


class ConfigOptionsFlowHandler(OptionsFlow):
    """Handle WeatherStation ConfigFlow."""

    def __init__(self) -> None:
        """Initialize flow."""
        super().__init__()
        # self.config_entry = config_entry

        self.user_data: dict[str, Any] = {}
        self.user_data_schema = {}
        self.sensors: dict[str, Any] = {}
        self.migrate_schema = {}

    async def _get_entry_data(self):
        """Get entry data."""
        entry_data = {**self.config_entry.data, **self.config_entry.options}

        self.user_data = {
            API_ID: entry_data.get(API_ID),
            API_KEY: entry_data.get(API_KEY),
            WSLINK: entry_data.get(WSLINK, False),
            DEV_DBG: entry_data.get(DEV_DBG, False),
        }

        self.user_data_schema = {
            vol.Required(API_ID, default=self.user_data.get(API_ID, "")): str,
            vol.Required(API_KEY, default=self.user_data.get(API_KEY, "")): str,
            vol.Optional(WSLINK, default=self.user_data.get(WSLINK, False)): bool,
            vol.Optional(DEV_DBG, default=self.user_data.get(DEV_DBG, False)): bool,
        }

        self.sensors = {
            SENSORS_TO_LOAD: (
                entry_data.get(SENSORS_TO_LOAD)
                if isinstance(entry_data.get(SENSORS_TO_LOAD), list)
                else []
            )
        }

    async def async_step_init(self, user_input=None):
        """Manage options."""
        return await self.async_step_basic(user_input)

    async def async_step_basic(self, user_input=None):
        """Manage basic options - credentials."""
        errors = {}

        await self._get_entry_data()

        if user_input is None:
            return self.async_show_form(
                step_id="basic",
                data_schema=vol.Schema(self.user_data_schema),
                errors=errors,
            )

        if user_input[API_ID] in INVALID_CREDENTIALS:
            errors[API_ID] = "valid_credentials_api"
        elif user_input[API_KEY] in INVALID_CREDENTIALS:
            errors[API_KEY] = "valid_credentials_key"
        elif user_input[API_KEY] == user_input[API_ID]:
            errors["base"] = "valid_credentials_match"
        else:
            # retain sensors
            user_input.update(self.sensors)

            return self.async_create_entry(title=DOMAIN, data=user_input)

        self.user_data = user_input

        # we are ending with error msg, reshow form
        return self.async_show_form(
            step_id="basic",
            data_schema=vol.Schema(self.user_data_schema),
            errors=errors,
        )


class ConfigFlowHandler(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Weather Station."""

    data_schema = {
        vol.Required(API_ID): str,
        vol.Required(API_KEY): str,
        vol.Optional(WSLINK): bool,
        vol.Optional(DEV_DBG): bool,
    }

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()

            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(self.data_schema),
            )

        errors = {}

        if user_input[API_ID] in INVALID_CREDENTIALS:
            errors[API_ID] = "valid_credentials_api"
        elif user_input[API_KEY] in INVALID_CREDENTIALS:
            errors[API_KEY] = "valid_credentials_key"
        elif user_input[API_KEY] == user_input[API_ID]:
            errors["base"] = "valid_credentials_match"
        else:
            return self.async_create_entry(
                title=DOMAIN, data=user_input, options=user_input
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(self.data_schema),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> ConfigOptionsFlowHandler:
        """Get the options flow for this handler."""
        return ConfigOptionsFlowHandler()
