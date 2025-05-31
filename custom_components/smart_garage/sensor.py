"""Sensor platform for Smart Garage integration."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    ATTR_OPEN_SENSOR,
    ATTR_CLOSED_SENSOR,
    ATTR_TOGGLE_ENTITY,
    ATTR_OPENING_DURATION,
    STATE_OPENING,
    STATE_CLOSED,
    STATE_OPEN,
    STATE_UNAVAILABLE,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistant,
    config: dict[str, Any],
    async_add_entities: AddEntitiesCallback,
    discovery_info: dict[str, Any] | None = None,
) -> None:
    """Set up the Smart Garage sensors from YAML configuration."""
    if DOMAIN not in hass.data:
        return

    garages = hass.data[DOMAIN].get("garages", [])
    entities = []

    for garage_config in garages:
        sensor = SmartGarageSensor(hass, garage_config)
        entities.append(sensor)

    async_add_entities(entities, True)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Smart Garage sensors from config entry."""
    config = config_entry.data
    sensor = SmartGarageSensor(hass, config)
    async_add_entities([sensor], True)


class SmartGarageSensor(SensorEntity):
    """Representation of a Smart Garage Door sensor."""

    def __init__(self, hass: HomeAssistant, config: dict[str, Any]) -> None:
        """Initialize the sensor."""
        self.hass = hass
        self._config = config
        self._name = config["name"]
        self._open_sensor = config[ATTR_OPEN_SENSOR]
        self._closed_sensor = config[ATTR_CLOSED_SENSOR]
        self._toggle_entity = config[ATTR_TOGGLE_ENTITY]
        self._opening_duration = config.get(ATTR_OPENING_DURATION, 35)
        
        self._attr_unique_id = f"{DOMAIN}_{self._name.lower().replace(' ', '_')}_state"
        self._attr_name = f"{self._name} State"
        self._attr_should_poll = False
        
        # Track entity states
        self._entities_to_track = [
            self._open_sensor,
            self._closed_sensor,
            self._toggle_entity,
        ]

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()
        
        # Track state changes of related entities
        async_track_state_change_event(
            self.hass, self._entities_to_track, self._handle_state_change
        )
        
        # Initial state update
        self._update_state()

    @callback
    def _handle_state_change(self, event) -> None:
        """Handle state changes of tracked entities."""
        self._update_state()
        self.async_write_ha_state()

    @callback
    def _update_state(self) -> None:
        """Update the sensor state based on garage door logic."""
        open_sensor_state = self.hass.states.get(self._open_sensor)
        closed_sensor_state = self.hass.states.get(self._closed_sensor)
        toggle_entity_state = self.hass.states.get(self._toggle_entity)

        if not open_sensor_state or not closed_sensor_state or not toggle_entity_state:
            self._attr_native_value = STATE_UNAVAILABLE
            self._attr_available = False
            return

        # Check if sensors are unavailable
        if (open_sensor_state.state == STATE_UNAVAILABLE or 
            closed_sensor_state.state == STATE_UNAVAILABLE):
            self._attr_native_value = STATE_UNAVAILABLE
            self._attr_available = False
            return

        self._attr_available = True

        # Determine state based on sensor readings
        open_sensor_on = open_sensor_state.state == STATE_ON
        closed_sensor_on = closed_sensor_state.state == STATE_ON

        if open_sensor_on and not closed_sensor_on:
            self._attr_native_value = STATE_OPEN
        elif not open_sensor_on and closed_sensor_on:
            self._attr_native_value = STATE_CLOSED
        elif not open_sensor_on and not closed_sensor_on:
            # Check if we're in the opening window
            if self._is_opening():
                self._attr_native_value = STATE_OPENING
            else:
                self._attr_native_value = STATE_UNAVAILABLE
        else:
            # Both sensors on - this shouldn't happen
            self._attr_native_value = STATE_UNAVAILABLE

    def _is_opening(self) -> bool:
        """Check if the garage door is currently opening."""
        toggle_entity_state = self.hass.states.get(self._toggle_entity)
        if not toggle_entity_state or not toggle_entity_state.last_changed:
            return False

        time_since_toggle = dt_util.utcnow() - toggle_entity_state.last_changed
        return time_since_toggle.total_seconds() < self._opening_duration

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information about this garage door."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._attr_unique_id)},
            name=self._name,
            manufacturer="Smart Garage",
            model="Garage Door Sensor",
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        return {
            ATTR_OPEN_SENSOR: self._open_sensor,
            ATTR_CLOSED_SENSOR: self._closed_sensor,
            ATTR_TOGGLE_ENTITY: self._toggle_entity,
            ATTR_OPENING_DURATION: self._opening_duration,
        } 