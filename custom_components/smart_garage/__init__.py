"""Smart Garage Door Integration for Home Assistant."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, TOGGLE_DOMAINS

_LOGGER = logging.getLogger(__name__)

# Load sensors first, then covers (covers depend on sensors)
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.COVER]


def validate_toggle_entity(value):
    """Validate that the toggle entity is a switch or light."""
    entity_id = cv.entity_id(value)
    domain = entity_id.split('.')[0]
    if domain not in TOGGLE_DOMAINS:
        raise vol.Invalid(f"Toggle entity must be from domains: {TOGGLE_DOMAINS}, got: {domain}")
    return entity_id


# Configuration schema for YAML setup
GARAGE_SCHEMA = vol.Schema({
    vol.Required("name"): cv.string,
    vol.Required("open_sensor"): cv.entity_id,
    vol.Required("closed_sensor"): cv.entity_id,
    vol.Required("toggle_entity"): validate_toggle_entity,
    vol.Optional("opening_duration", default=35): cv.positive_int,
})

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Required("garages"): vol.All(cv.ensure_list, [GARAGE_SCHEMA]),
    })
}, extra=vol.ALLOW_EXTRA)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Smart Garage component from YAML configuration."""
    _LOGGER.debug("Setting up Smart Garage integration from YAML")
    
    if DOMAIN not in config:
        _LOGGER.debug("No Smart Garage configuration found in YAML")
        return True

    hass.data.setdefault(DOMAIN, {})
    
    # Store garage configurations
    garages = config[DOMAIN].get("garages", [])
    hass.data[DOMAIN]["garages"] = garages
    
    _LOGGER.info("Setting up Smart Garage with %d garage(s) from YAML", len(garages))
    for garage in garages:
        _LOGGER.debug("YAML Garage config: %s", garage)
    
    # Load platforms in order (sensors first, then covers)
    _LOGGER.debug("Loading sensor platform from YAML")
    hass.async_create_task(
        hass.helpers.discovery.async_load_platform(Platform.SENSOR, DOMAIN, {}, config)
    )
    
    _LOGGER.debug("Loading cover platform from YAML")
    hass.async_create_task(
        hass.helpers.discovery.async_load_platform(Platform.COVER, DOMAIN, {}, config)
    )
    
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Smart Garage from a config entry."""
    _LOGGER.debug("Setting up Smart Garage from config entry: %s", entry.title)
    _LOGGER.debug("Config entry data: %s", entry.data)
    
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry.data

    _LOGGER.debug("Forwarding setup to platforms: %s", PLATFORMS)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    _LOGGER.info("Successfully set up Smart Garage: %s", entry.title)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading Smart Garage config entry: %s", entry.title)
    
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        _LOGGER.debug("Successfully unloaded Smart Garage: %s", entry.title)
    else:
        _LOGGER.error("Failed to unload Smart Garage: %s", entry.title)

    return unload_ok 