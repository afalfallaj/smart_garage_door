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
    ATTR_MOTION_DURATION,
    STATE_OPENING,
    STATE_CLOSING,
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
    _LOGGER.debug("Setting up Smart Garage sensors from YAML configuration")
    
    if DOMAIN not in hass.data:
        _LOGGER.debug("No Smart Garage data found in hass.data")
        return

    garages = hass.data[DOMAIN].get("garages", [])
    _LOGGER.debug("Found %d garage configurations in YAML", len(garages))
    
    entities = []

    for garage_config in garages:
        _LOGGER.debug("Creating sensor for garage: %s", garage_config.get("name", "unknown"))
        sensor = SmartGarageSensor(hass, garage_config)
        entities.append(sensor)

    _LOGGER.debug("Adding %d sensor entities", len(entities))
    async_add_entities(entities, True)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Smart Garage sensors from config entry."""
    _LOGGER.debug("Setting up Smart Garage sensor from config entry: %s", config_entry.title)
    
    config = config_entry.data
    _LOGGER.debug("Config entry data: %s", config)
    
    sensor = SmartGarageSensor(hass, config)
    _LOGGER.debug("Created sensor entity with unique_id: %s", sensor.unique_id)
    
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
        self._motion_duration = config.get(ATTR_MOTION_DURATION, 35)
        
        # Generate consistent entity IDs between sensor and cover
        entity_id_suffix = self._name.lower().replace(' ', '_')
        self._attr_unique_id = f"{DOMAIN}_{entity_id_suffix}_state"
        self._attr_name = f"{self._name} State"
        # Explicitly set entity_id to ensure consistency
        self.entity_id = f"sensor.{DOMAIN}_{entity_id_suffix}_state"
        self._attr_should_poll = False
        
        # Track previous state for opening/closing logic
        self._previous_state = None
        
        # Track entity states
        self._entities_to_track = [
            self._open_sensor,
            self._closed_sensor,
            self._toggle_entity,
        ]
        
        _LOGGER.debug(
            "Initialized sensor '%s' with config: open_sensor=%s, closed_sensor=%s, "
            "toggle_entity=%s, motion_duration=%s, unique_id=%s, entity_id=%s",
            self._name, self._open_sensor, self._closed_sensor, 
            self._toggle_entity, self._motion_duration, self._attr_unique_id, self.entity_id
        )

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()
        
        _LOGGER.debug(
            "Sensor '%s' added to hass with entity_id: %s (expected: %s)", 
            self._name, self.entity_id, f"sensor.{DOMAIN}_{self._name.lower().replace(' ', '_')}_state"
        )
        
        # Check if tracked entities exist
        for entity_id in self._entities_to_track:
            entity_state = self.hass.states.get(entity_id)
            if entity_state:
                _LOGGER.debug(
                    "Tracked entity '%s' found: state=%s, attributes=%s",
                    entity_id, entity_state.state, entity_state.attributes
                )
            else:
                _LOGGER.warning(
                    "Tracked entity '%s' not found! Available entities: %s",
                    entity_id, 
                    [e for e in self.hass.states.async_entity_ids() 
                     if e.startswith(entity_id.split('.')[0] + '.')][:5]
                )
        
        # Track state changes of related entities
        async_track_state_change_event(
            self.hass, self._entities_to_track, self._handle_state_change
        )
        
        _LOGGER.debug("Set up state tracking for entities: %s", self._entities_to_track)
        
        # Initial state update
        self._update_state()
        
        _LOGGER.debug(
            "Initial state for sensor '%s': value=%s, available=%s",
            self._name, self._attr_native_value, self._attr_available
        )
        
        # Verify the sensor can be found by the cover
        _LOGGER.debug(
            "Verifying sensor can be found: %s exists = %s", 
            self.entity_id, self.hass.states.get(self.entity_id) is not None
        )

    @callback
    def _handle_state_change(self, event) -> None:
        """Handle state changes of tracked entities."""
        _LOGGER.debug(
            "State change event for sensor '%s': entity=%s, new_state=%s", 
            self._name, 
            event.data.get("entity_id") if event and event.data else "unknown",
            event.data.get("new_state").state if event and event.data and event.data.get("new_state") else "unknown"
        )
        
        self._update_state()
        self.async_write_ha_state()
        
        _LOGGER.debug(
            "Updated sensor '%s' state: value=%s, available=%s",
            self._name, self._attr_native_value, self._attr_available
        )

    @callback
    def _update_state(self) -> None:
        """Update the sensor state based on garage door logic."""
        _LOGGER.debug("Updating state for sensor '%s'", self._name)
        
        open_sensor_state = self.hass.states.get(self._open_sensor)
        closed_sensor_state = self.hass.states.get(self._closed_sensor)
        toggle_entity_state = self.hass.states.get(self._toggle_entity)

        _LOGGER.debug(
            "Entity states - open_sensor: %s, closed_sensor: %s, toggle_entity: %s",
            open_sensor_state.state if open_sensor_state else "NOT_FOUND",
            closed_sensor_state.state if closed_sensor_state else "NOT_FOUND",
            toggle_entity_state.state if toggle_entity_state else "NOT_FOUND"
        )

        if not open_sensor_state or not closed_sensor_state or not toggle_entity_state:
            missing_entities = []
            if not open_sensor_state:
                missing_entities.append(self._open_sensor)
            if not closed_sensor_state:
                missing_entities.append(self._closed_sensor)
            if not toggle_entity_state:
                missing_entities.append(self._toggle_entity)
                
            _LOGGER.warning(
                "Missing entities for sensor '%s': %s", 
                self._name, missing_entities
            )
            
            self._attr_native_value = STATE_UNAVAILABLE
            self._attr_available = False
            return

        # Check if sensors are unavailable
        if (open_sensor_state.state == STATE_UNAVAILABLE or 
            closed_sensor_state.state == STATE_UNAVAILABLE):
            _LOGGER.warning(
                "Sensor '%s' has unavailable dependencies: open=%s, closed=%s",
                self._name, open_sensor_state.state, closed_sensor_state.state
            )
            self._attr_native_value = STATE_UNAVAILABLE
            self._attr_available = False
            return

        self._attr_available = True

        # Store current state as previous before updating
        if self._attr_native_value and self._attr_native_value != STATE_UNAVAILABLE:
            self._previous_state = self._attr_native_value

        # Determine state based on sensor readings
        open_sensor_on = open_sensor_state.state == STATE_ON
        closed_sensor_on = closed_sensor_state.state == STATE_ON

        _LOGGER.debug(
            "Sensor logic for '%s': open_on=%s, closed_on=%s, previous_state=%s",
            self._name, open_sensor_on, closed_sensor_on, self._previous_state
        )

        if open_sensor_on and not closed_sensor_on:
            self._attr_native_value = STATE_OPEN
            # Clear motion tracking when reaching a final state
            if hasattr(self, '_motion_start_time'):
                delattr(self, '_motion_start_time')
            _LOGGER.debug("Sensor '%s' determined state: OPEN", self._name)
        elif not open_sensor_on and closed_sensor_on:
            self._attr_native_value = STATE_CLOSED
            # Clear motion tracking when reaching a final state
            if hasattr(self, '_motion_start_time'):
                delattr(self, '_motion_start_time')
            _LOGGER.debug("Sensor '%s' determined state: CLOSED", self._name)
        elif not open_sensor_on and not closed_sensor_on:
            # Both sensors are off - door is likely in motion
            # Track when motion starts for manual triggers
            if self._previous_state in [STATE_OPEN, STATE_CLOSED] and not hasattr(self, '_motion_start_time'):
                self._motion_start_time = dt_util.utcnow()
                _LOGGER.debug("Sensor '%s' started motion tracking", self._name)
            
            # Determine if opening or closing based on previous state
            if self._previous_state == STATE_OPEN:
                # Check if we've been in motion too long
                if self._has_motion_exceeded_duration():
                    self._attr_native_value = STATE_UNAVAILABLE
                    _LOGGER.debug("Sensor '%s' determined state: UNAVAILABLE (closing too long)", self._name)
                else:
                    self._attr_native_value = STATE_CLOSING
                    _LOGGER.debug("Sensor '%s' determined state: CLOSING (was open)", self._name)
            elif self._previous_state == STATE_CLOSED:
                # Check if we've been in motion too long
                if self._has_motion_exceeded_duration():
                    self._attr_native_value = STATE_UNAVAILABLE
                    _LOGGER.debug("Sensor '%s' determined state: UNAVAILABLE (opening too long)", self._name)
                else:
                    self._attr_native_value = STATE_OPENING
                    _LOGGER.debug("Sensor '%s' determined state: OPENING (was closed)", self._name)
            elif self._previous_state in [STATE_OPENING, STATE_CLOSING]:
                # Continue with the same motion state if not exceeded duration
                if self._has_motion_exceeded_duration():
                    self._attr_native_value = STATE_UNAVAILABLE
                    _LOGGER.debug("Sensor '%s' determined state: UNAVAILABLE (motion too long)", self._name)
                else:
                    self._attr_native_value = self._previous_state
                    _LOGGER.debug("Sensor '%s' continuing motion state: %s", self._name, self._previous_state)
            else:
                # No previous state to determine direction
                # Check if our toggle was recently activated to help determine direction
                if self._is_in_motion():
                    self._attr_native_value = STATE_OPENING  # Default to opening
                    _LOGGER.debug("Sensor '%s' determined state: OPENING (no previous state, but recent toggle)", self._name)
                else:
                    self._attr_native_value = STATE_UNAVAILABLE
                    _LOGGER.debug("Sensor '%s' determined state: UNAVAILABLE (no previous state, no recent toggle)", self._name)
        else:
            # Both sensors on - this shouldn't happen
            _LOGGER.warning(
                "Sensor '%s' has invalid state: both sensors are ON", self._name
            )
            self._attr_native_value = STATE_UNAVAILABLE

    def _is_in_motion(self) -> bool:
        """Check if the garage door is currently in motion (opening or closing)."""
        toggle_entity_state = self.hass.states.get(self._toggle_entity)
        if not toggle_entity_state or not toggle_entity_state.last_changed:
            _LOGGER.debug(
                "Cannot determine motion state for '%s': toggle_entity_state=%s, last_changed=%s",
                self._name, 
                toggle_entity_state.state if toggle_entity_state else "NOT_FOUND",
                toggle_entity_state.last_changed if toggle_entity_state else "NOT_FOUND"
            )
            return False

        time_since_toggle = dt_util.utcnow() - toggle_entity_state.last_changed
        seconds_since_toggle = time_since_toggle.total_seconds()
        is_in_motion = seconds_since_toggle < self._motion_duration
        
        _LOGGER.debug(
            "Motion check for '%s': seconds_since_toggle=%.1f, motion_duration=%d, is_in_motion=%s",
            self._name, seconds_since_toggle, self._motion_duration, is_in_motion
        )
        
        return is_in_motion

    def _has_motion_exceeded_duration(self) -> bool:
        """Check if the garage door has been in motion for too long."""
        # For manual triggers, we need to track when the motion state started
        # Since we don't know when manual motion started, we'll use a more conservative approach
        
        # If our toggle was recently activated, use that timing
        toggle_entity_state = self.hass.states.get(self._toggle_entity)
        if toggle_entity_state and toggle_entity_state.last_changed:
            time_since_toggle = dt_util.utcnow() - toggle_entity_state.last_changed
            seconds_since_toggle = time_since_toggle.total_seconds()
            
            # If our toggle was recent and we're past duration, it's exceeded
            if seconds_since_toggle < (self._motion_duration * 2):  # Allow some buffer for manual
                exceeded = seconds_since_toggle > self._motion_duration
                _LOGGER.debug(
                    "Motion duration check for '%s': seconds_since_toggle=%.1f, motion_duration=%d, exceeded=%s",
                    self._name, seconds_since_toggle, self._motion_duration, exceeded
                )
                return exceeded
        
        # For purely manual triggers, we're more conservative
        # Check if we've been in a motion state for too long based on our own state changes
        if hasattr(self, '_motion_start_time'):
            time_in_motion = dt_util.utcnow() - self._motion_start_time
            exceeded = time_in_motion.total_seconds() > self._motion_duration
            _LOGGER.debug(
                "Manual motion duration check for '%s': time_in_motion=%.1f, motion_duration=%d, exceeded=%s",
                self._name, time_in_motion.total_seconds(), self._motion_duration, exceeded
            )
            return exceeded
            
        # If we can't determine timing, don't timeout
        return False

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
            ATTR_MOTION_DURATION: self._motion_duration,
        } 