"""Config flow for Weather Station integration."""

from typing import Any, ClassVar

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    API_ID,
    API_KEY,
    API_MODE,
    API_MODE_PWS,
    API_MODE_WSLINK,
    DEV_DBG,
    DOMAIN,
    INVALID_CREDENTIALS,
    SENSORS_TO_LOAD,
    URL_WSLINK_ADDON,
)
from .helpers import ha_https_enabled

CONFIRM_HTTPS = "confirm_https"


class ConfigOptionsFlowHandler(OptionsFlow):
    """Handle WeatherStation ConfigFlow."""

    def __init__(self) -> None:
        """Initialize flow."""
        super().__init__()
        self.user_data: dict[str, Any] = {}
        self.user_data_schema = {}
        self.sensors: dict[str, Any] = {}
        self._pending_user_input: dict[str, Any] | None = None

    async def _get_entry_data(self):
        """Get entry data."""
        entry_data = {**self.config_entry.data, **self.config_entry.options}

        self.user_data = {
            API_ID: entry_data.get(API_ID),
            API_KEY: entry_data.get(API_KEY),
            API_MODE: entry_data.get(API_MODE, API_MODE_PWS),
            DEV_DBG: entry_data.get(DEV_DBG, False),
        }

        self.user_data_schema = {
            vol.Required(API_ID, default=self.user_data.get(API_ID, "")): str,
            vol.Required(API_KEY, default=self.user_data.get(API_KEY, "")): str,
            vol.Required(
                API_MODE,
                default=self.user_data.get(API_MODE, API_MODE_PWS),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        {"value": API_MODE_PWS, "label": "PWS / WU"},
                        {"value": API_MODE_WSLINK, "label": "WS-Link"},
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
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
            # Retain sensors
            user_input.update(self.sensors)

            if not ha_https_enabled(self.hass):
                self._pending_user_input = user_input
                return await self.async_step_https_warning()

            return self.async_create_entry(title="", data=user_input)

        self.user_data = user_input

        return self.async_show_form(
            step_id="basic",
            data_schema=vol.Schema(self.user_data_schema),
            errors=errors,
        )

    async def async_step_https_warning(self, user_input=None):
        """Warn user if WSLink is enabled while HA HTTPS is not detected."""
        errors = {}

        if user_input is not None:
            if user_input.get(CONFIRM_HTTPS):
                if self._pending_user_input is None:
                    return self.async_abort(reason="unknown")

                return self.async_create_entry(title="", data=self._pending_user_input)

            errors["base"] = "confirm_https"

        return self.async_show_form(
            step_id="https_warning",
            data_schema=vol.Schema(
                {
                    vol.Required(CONFIRM_HTTPS, default=False): bool,
                }
            ),
            errors=errors,
            description_placeholders={
                "url_wslink_addon": URL_WSLINK_ADDON,
            },
        )


class ConfigFlowHandler(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Weather Station."""

    data_schema: ClassVar[dict[Any, Any]] = {
        vol.Required(API_ID): str,
        vol.Required(API_KEY): str,
        vol.Required(
            API_MODE,
            default=API_MODE_PWS,
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    {
                        "value": API_MODE_PWS,
                        "label": "PWS (Personal Weather Station / WeatherUnderground)",
                    },
                    {"value": API_MODE_WSLINK, "label": "WS-Link"},
                ],
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Optional(DEV_DBG): bool,
    }

    VERSION = 1

    def __init__(self) -> None:
        """Initialize flow."""
        self._pending_user_input: dict[str, Any] | None = None

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
            if not ha_https_enabled(self.hass):
                self._pending_user_input = user_input
                return await self.async_step_https_warning()

            return self.async_create_entry(
                title=str(user_input.get(API_ID) or DOMAIN),
                data=user_input,
                options=user_input,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(self.data_schema),
            errors=errors,
        )

    async def async_step_https_warning(self, user_input=None) -> ConfigFlowResult:
        """Warn user if HA HTTPS is not detected."""
        errors = {}

        if user_input is not None:
            if user_input.get(CONFIRM_HTTPS):
                if self._pending_user_input is None:
                    return self.async_abort(reason="unknown")

                return self.async_create_entry(
                    title=str(self._pending_user_input.get(API_ID) or DOMAIN),
                    data=self._pending_user_input,
                    options=self._pending_user_input,
                )

            errors["base"] = "confirm_https"

        return self.async_show_form(
            step_id="https_warning",
            data_schema=vol.Schema(
                {
                    vol.Required(CONFIRM_HTTPS, default=False): bool,
                }
            ),
            errors=errors,
            description_placeholders={
                "url_wslink_addon": URL_WSLINK_ADDON,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> ConfigOptionsFlowHandler:
        """Get the options flow for this handler."""
        return ConfigOptionsFlowHandler()
