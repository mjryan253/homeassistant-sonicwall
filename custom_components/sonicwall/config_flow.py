"""Adds config flow for SonicWall."""

from __future__ import annotations

import re

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.loader import async_get_loaded_integration

from .api import (
    SonicWallApiClient,
    SonicWallApiClientAuthenticationError,
    SonicWallApiClientCommunicationError,
    SonicWallApiClientError,
)
from .const import (
    CONF_VERIFY_SSL,
    DEFAULT_PORT,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
    LOGGER,
)


class SonicWallConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for SonicWall."""

    VERSION = 1

    async def async_step_user(
        self,
        user_input: dict | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle a flow initialized by the user."""
        _errors: dict[str, str] = {}
        if user_input is not None:
            try:
                serial = await self._test_credentials(user_input)
            except SonicWallApiClientAuthenticationError as exception:
                LOGGER.warning(exception)
                _errors["base"] = "auth"
            except SonicWallApiClientCommunicationError as exception:
                LOGGER.error(exception)
                _errors["base"] = "connection"
            except SonicWallApiClientError as exception:
                LOGGER.exception(exception)
                _errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(serial)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"SonicWall ({user_input[CONF_HOST]})",
                    data=user_input,
                )

        integration = async_get_loaded_integration(self.hass, DOMAIN)
        assert integration.documentation is not None, (  # noqa: S101
            "Integration documentation URL is not set in manifest.json"
        )

        return self.async_show_form(
            step_id="user",
            description_placeholders={
                "documentation_url": integration.documentation,
            },
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_HOST,
                        default=(user_input or {}).get(CONF_HOST, vol.UNDEFINED),
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.TEXT,
                        ),
                    ),
                    vol.Required(
                        CONF_PORT,
                        default=(user_input or {}).get(CONF_PORT, DEFAULT_PORT),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1,
                            max=65535,
                            mode=selector.NumberSelectorMode.BOX,
                        ),
                    ),
                    vol.Required(
                        CONF_USERNAME,
                        default=(user_input or {}).get(CONF_USERNAME, vol.UNDEFINED),
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.TEXT,
                        ),
                    ),
                    vol.Required(CONF_PASSWORD): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD,
                        ),
                    ),
                    vol.Required(
                        CONF_VERIFY_SSL,
                        default=(user_input or {}).get(
                            CONF_VERIFY_SSL,
                            DEFAULT_VERIFY_SSL,
                        ),
                    ): selector.BooleanSelector(),
                },
            ),
            errors=_errors,
        )

    async def _test_credentials(self, user_input: dict) -> str:
        """Validate credentials and return the normalised device serial."""
        client = SonicWallApiClient(
            host=user_input[CONF_HOST],
            port=int(user_input[CONF_PORT]),
            username=user_input[CONF_USERNAME],
            password=user_input[CONF_PASSWORD],
            verify_ssl=user_input[CONF_VERIFY_SSL],
            session=async_create_clientsession(self.hass),
        )
        try:
            version = await client.async_version()
        finally:
            await client.async_logout()
        return _normalize_serial(version.get("serial_number"))


def _normalize_serial(raw: str | None) -> str:
    """Strip non-alphanumerics and uppercase. ``2CB8-ED3C-A53C`` -> ``2CB8ED3CA53C``."""
    if not raw:
        return "unknown"
    return re.sub(r"[^A-Z0-9]", "", str(raw).upper()) or "unknown"
