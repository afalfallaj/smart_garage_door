"""Config flow for Smart Garage Door integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
)

from .const import (
    DOMAIN,
    TOGGLE_DOMAINS,
    ATTR_OPEN_SENSOR,
    ATTR_CLOSED_SENSOR,
    ATTR_TOGGLE_ENTITY,
    ATTR_MOTION_DURATION,
    DEFAULT_MOTION_DURATION,
    ATTR_SENSOR_DEBOUNCE_MS,
    DEFAULT_SENSOR_DEBOUNCE_MS,
    STEP_USER,
)

_LOGGER = logging.getLogger(__name__)


def validate_toggle_entity(value: str) -> str:
    """Validate that the toggle entity is a switch or light."""
    entity_id = cv.entity_id(value)
    domain = entity_id.split('.')[0]
    if domain not in TOGGLE_DOMAINS:
        raise vol.Invalid(f"Toggle entity must be from domains: {TOGGLE_DOMAINS}, got: {domain}")
    return entity_id


class SmartGarageConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Smart Garage Door."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self.garage_data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                # Validate the toggle entity
                validate_toggle_entity(user_input[ATTR_TOGGLE_ENTITY])
                
                # Create a unique ID based on the garage name
                unique_id = user_input["name"].lower().replace(" ", "_")
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=user_input["name"],
                    data=user_input,
                )
            except vol.Invalid:
                errors[ATTR_TOGGLE_ENTITY] = "invalid_toggle_entity"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        schema = vol.Schema({
            vol.Required("name", default="Garage Door"): TextSelector(),
            vol.Required(ATTR_OPEN_SENSOR): EntitySelector(
                EntitySelectorConfig(domain="binary_sensor")
            ),
            vol.Required(ATTR_CLOSED_SENSOR): EntitySelector(
                EntitySelectorConfig(domain="binary_sensor")
            ),
            vol.Required(ATTR_TOGGLE_ENTITY): EntitySelector(
                EntitySelectorConfig(domain=TOGGLE_DOMAINS)
            ),
            vol.Optional(
                ATTR_MOTION_DURATION, 
                default=DEFAULT_MOTION_DURATION
            ): NumberSelector(
                NumberSelectorConfig(
                    mode=NumberSelectorMode.BOX,
                    min=5,
                    max=120,
                    unit_of_measurement="seconds",
                )
            ),
            vol.Optional(
                ATTR_SENSOR_DEBOUNCE_MS,
                default=DEFAULT_SENSOR_DEBOUNCE_MS
            ): NumberSelector(
                NumberSelectorConfig(
                    mode=NumberSelectorMode.BOX,
                    min=50,
                    max=2000,
                    unit_of_measurement="ms",
                )
            ),
        })

        return self.async_show_form(
            step_id=STEP_USER,
            data_schema=schema,
            errors=errors,
        ) 