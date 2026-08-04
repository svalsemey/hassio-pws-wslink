"""Config flow for Weather Station integration."""

from collections.abc import Mapping
from typing import Any, Final

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
    API_MODE,
    API_MODE_PWS,
    API_MODE_WSLINK,
    DEV_DBG,
    DOMAIN,
    SENSORS_TO_LOAD,
    STATION_ID,
    STATION_PASSWORD,
    URL_WSLINK_ADDON,
)
from .helpers import ha_https_enabled, is_placeholder_credential

CONFIRM_HTTPS = "confirm_https"

CONFIRM_HTTPS_SCHEMA = vol.Schema({vol.Required(CONFIRM_HTTPS, default=False): bool})

_API_MODE_OPTIONS: Final = [
    {"value": API_MODE_PWS, "label": "PWS / WeatherUnderground"},
    {"value": API_MODE_WSLINK, "label": "WS-Link"},
]


def _credentials_schema(defaults: Mapping[str, Any]) -> vol.Schema:
    """Build the credential form, prefilled with the given values."""
    return vol.Schema(
        {
            vol.Required(STATION_ID, default=defaults.get(STATION_ID, "")): str,
            vol.Required(
                STATION_PASSWORD, default=defaults.get(STATION_PASSWORD, "")
            ): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
            vol.Required(
                API_MODE, default=defaults.get(API_MODE, API_MODE_PWS)
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=_API_MODE_OPTIONS,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(DEV_DBG, default=defaults.get(DEV_DBG, False)): bool,
        }
    )


def _trimmed(user_input: dict[str, Any]) -> dict[str, Any]:
    """Return the input with surrounding blanks removed from the credentials."""
    return {
        **user_input,
        STATION_ID: user_input[STATION_ID].strip(),
        STATION_PASSWORD: user_input[STATION_PASSWORD].strip(),
    }


def _credential_errors(user_input: dict[str, Any]) -> dict[str, str]:
    """Return the credential form errors, empty when both fields are valid."""
    if is_placeholder_credential(user_input[STATION_ID]):
        return {STATION_ID: "valid_station_id"}
    if is_placeholder_credential(user_input[STATION_PASSWORD]):
        return {STATION_PASSWORD: "valid_station_password"}
    if user_input[STATION_PASSWORD] == user_input[STATION_ID]:
        return {"base": "valid_credentials_match"}
    return {}


class ConfigOptionsFlowHandler(OptionsFlow):
    """Handle the options of one configured weather station."""

    def __init__(self) -> None:
        """Initialize flow."""
        super().__init__()
        self._pending_user_input: dict[str, Any] | None = None

    def _retained_sensors(self) -> dict[str, Any]:
        """Return the discovered sensor keys, carried over when saving."""
        keys = self.config_entry.options.get(SENSORS_TO_LOAD)
        return {SENSORS_TO_LOAD: keys if isinstance(keys, list) else []}

    def _async_save(self, user_input: dict[str, Any]) -> ConfigFlowResult:
        """Store the options, renaming the entry when the station id changed."""
        if user_input[STATION_ID] != self.config_entry.unique_id:
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                unique_id=user_input[STATION_ID],
                title=user_input[STATION_ID],
            )
        return self.async_create_entry(title="", data=user_input)

    async def async_step_init(self, user_input=None) -> ConfigFlowResult:
        """Manage options."""
        return await self.async_step_basic(user_input)

    async def async_step_basic(self, user_input=None) -> ConfigFlowResult:
        """Manage the credentials and the protocol of this station."""
        errors: dict[str, str] = {}

        if user_input is not None:
            user_input = _trimmed(user_input)
            errors = _credential_errors(user_input)

            if not errors and any(
                entry.unique_id == user_input[STATION_ID]
                and entry.entry_id != self.config_entry.entry_id
                for entry in self.hass.config_entries.async_entries(DOMAIN)
            ):
                errors = {STATION_ID: "duplicate_station"}

            if not errors:
                user_input.update(self._retained_sensors())

                if not ha_https_enabled(self.hass):
                    self._pending_user_input = user_input
                    return await self.async_step_https_warning()

                return self._async_save(user_input)

        return self.async_show_form(
            step_id="basic",
            data_schema=_credentials_schema(
                user_input or {**self.config_entry.data, **self.config_entry.options}
            ),
            errors=errors,
        )

    async def async_step_https_warning(self, user_input=None) -> ConfigFlowResult:
        """Warn the user when Home Assistant is not reachable over HTTPS."""
        errors: dict[str, str] = {}

        if user_input is not None:
            if user_input[CONFIRM_HTTPS]:
                if self._pending_user_input is None:
                    return self.async_abort(reason="unknown")
                return self._async_save(self._pending_user_input)

            errors["base"] = "confirm_https"

        return self.async_show_form(
            step_id="https_warning",
            data_schema=CONFIRM_HTTPS_SCHEMA,
            errors=errors,
            description_placeholders={"url_wslink_addon": URL_WSLINK_ADDON},
        )


class ConfigFlowHandler(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Weather Station."""

    VERSION = 2

    def __init__(self) -> None:
        """Initialize flow."""
        self._pending_user_input: dict[str, Any] | None = None

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            user_input = _trimmed(user_input)
            errors = _credential_errors(user_input)

            if not errors:
                await self.async_set_unique_id(user_input[STATION_ID])
                self._abort_if_unique_id_configured()

                if not ha_https_enabled(self.hass):
                    self._pending_user_input = user_input
                    return await self.async_step_https_warning()

                return self.async_create_entry(
                    title=user_input[STATION_ID],
                    data=user_input,
                    options=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_credentials_schema(user_input or {}),
            errors=errors,
        )

    async def async_step_https_warning(self, user_input=None) -> ConfigFlowResult:
        """Warn the user when Home Assistant is not reachable over HTTPS."""
        errors: dict[str, str] = {}

        if user_input is not None:
            if user_input[CONFIRM_HTTPS]:
                if self._pending_user_input is None:
                    return self.async_abort(reason="unknown")

                return self.async_create_entry(
                    title=self._pending_user_input[STATION_ID],
                    data=self._pending_user_input,
                    options=self._pending_user_input,
                )

            errors["base"] = "confirm_https"

        return self.async_show_form(
            step_id="https_warning",
            data_schema=CONFIRM_HTTPS_SCHEMA,
            errors=errors,
            description_placeholders={"url_wslink_addon": URL_WSLINK_ADDON},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> ConfigOptionsFlowHandler:
        """Get the options flow for this handler."""
        return ConfigOptionsFlowHandler()
