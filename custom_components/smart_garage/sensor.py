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
from homeassistant.helpers.event import async_track_state_change_event, async_track_point_in_time
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
        
        # Track motion timing - when motion actually starts (both sensors go off)
        self._motion_start_time = None
        
        # Track motion timeout callback to ensure timeout happens even without sensor changes
        self._motion_timeout_unsub = None
        
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
            "Sensor '%s' added to hass with entity_id: %s", 
            self._name, self.entity_id
        )
        
        # Check if tracked entities exist and log status
        missing_entities = []
        for entity_id in self._entities_to_track:
            entity_state = self.hass.states.get(entity_id)
            if entity_state:
                _LOGGER.debug(
                    "Tracked entity '%s' found: state=%s",
                    entity_id, entity_state.state
                )
            else:
                missing_entities.append(entity_id)
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
        
        # If sensor is unavailable due to missing entities, schedule a retry
        if self._attr_native_value == STATE_UNAVAILABLE and missing_entities:
            _LOGGER.info(
                "Sensor '%s' initially unavailable due to missing entities: %s. "
                "Will retry in a few seconds...", 
                self._name, missing_entities
            )
            await self._delayed_entity_check()
        
        _LOGGER.debug(
            "Initial state for sensor '%s': value=%s, available=%s",
            self._name, self._attr_native_value, self._attr_available
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
        
        # Get current entity states
        open_sensor_state = self.hass.states.get(self._open_sensor)
        closed_sensor_state = self.hass.states.get(self._closed_sensor)
        toggle_entity_state = self.hass.states.get(self._toggle_entity)

        # Check if all required entities exist
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

        # Convert sensor states to boolean
        open_sensor_on = open_sensor_state.state == STATE_ON
        closed_sensor_on = closed_sensor_state.state == STATE_ON
        both_sensors_off = not open_sensor_on and not closed_sensor_on

        # Enhanced motion detection logic to handle noisy sensors
        # Motion can start in several ways:
        # 1. Transition from definite state (open/closed) to both sensors off (normal case)
        # 2. Sensor noise during stable state (e.g., closed sensor briefly goes on->off during opening)
        was_in_definite_state = self._previous_state in [STATE_OPEN, STATE_CLOSED]
        currently_in_definite_state = open_sensor_on or closed_sensor_on
        motion_already_active = self._motion_start_time is not None
        
        # Detect motion start conditions
        motion_start_detected = False
        
        # Standard motion detection: transition from definite state to both sensors off
        if both_sensors_off and was_in_definite_state and not motion_already_active:
            motion_start_detected = True
            _LOGGER.debug(
                "Standard motion start detected for '%s': %s -> both_sensors_off",
                self._name, self._previous_state
            )
        
        # Enhanced detection for noisy sensors during motion:
        # If we were in a stable state and now see the opposite sensor briefly activate,
        # this likely indicates motion has started (e.g., door was closed, now closed sensor flickers)
        elif not motion_already_active and was_in_definite_state:
            # Door was closed, but closed sensor is now flickering (on when it should be off during opening)
            if self._previous_state == STATE_CLOSED and closed_sensor_on:
                motion_start_detected = True
                _LOGGER.debug(
                    "Noisy sensor motion start detected for '%s': door was closed, closed sensor flickering",
                    self._name
                )
            # Door was open, but open sensor is now flickering (on when it should be off during closing)  
            elif self._previous_state == STATE_OPEN and open_sensor_on:
                motion_start_detected = True
                _LOGGER.debug(
                    "Noisy sensor motion start detected for '%s': door was open, open sensor flickering",
                    self._name
                )
        
        # Start motion tracking if detected
        if motion_start_detected:
            self._motion_start_time = dt_util.utcnow()
            _LOGGER.info(
                "Motion started for '%s': previous_state=%s, sensors=(open=%s, closed=%s)",
                self._name, self._previous_state, open_sensor_on, closed_sensor_on
            )
            
            # Schedule motion timeout check (crucial for when sensors don't change)
            self._schedule_motion_timeout()

        # Apply state logic with enhanced motion handling
        new_state = self._determine_garage_state(open_sensor_on, closed_sensor_on, both_sensors_off)
        
        # Enhanced motion clearing logic:
        # Clear motion tracking when reaching final states (open/closed) OR when sensors give definitive readings
        if new_state in [STATE_OPEN, STATE_CLOSED]:
            if self._motion_start_time:
                motion_duration = dt_util.utcnow() - self._motion_start_time
                _LOGGER.info(
                    "Motion completed for '%s': %s -> %s (duration: %.1fs)",
                    self._name, self._previous_state, new_state, motion_duration.total_seconds()
                )
            self._clear_motion_tracking()
        
        # If we're in motion and get a definitive sensor reading that matches expected end state,
        # immediately end motion even if duration hasn't expired
        elif self._motion_start_time and new_state in [STATE_OPEN, STATE_CLOSED]:
            expected_end_state = None
            if self._previous_state == STATE_CLOSED:
                expected_end_state = STATE_OPEN
            elif self._previous_state == STATE_OPEN:
                expected_end_state = STATE_CLOSED
                
            if new_state == expected_end_state:
                motion_duration = dt_util.utcnow() - self._motion_start_time
                _LOGGER.info(
                    "Motion completed early for '%s': definitive sensor reading %s (duration: %.1fs)",
                    self._name, new_state, motion_duration.total_seconds()
                )
                self._clear_motion_tracking()

        self._attr_native_value = new_state
        
        _LOGGER.debug(
            "Sensor '%s' final state: %s (in_motion=%s)", 
            self._name, new_state, self._motion_start_time is not None
        )

    def _determine_garage_state(self, open_sensor_on: bool, closed_sensor_on: bool, both_sensors_off: bool) -> str:
        """
        Determine garage door state using logic that ignores sensor noise during motion.
        
        Args:
            open_sensor_on: True if open sensor is on
            closed_sensor_on: True if closed sensor is on  
            both_sensors_off: True if both sensors are off
            
        Returns:
            The determined state string
        """
        # During motion, we want to ignore noisy sensor readings and maintain motion state
        # until we get a definitive sensor reading or motion duration expires
        in_motion = self._is_in_motion()
        
        # 1. Both sensors on - impossible state (sensor malfunction)
        if open_sensor_on and closed_sensor_on:
            _LOGGER.warning(
                "Both sensors on for '%s' - sensor malfunction detected",
                self._name
            )
            return STATE_UNAVAILABLE
            
        # 2. Definitive states - always trust clear sensor readings
        # Open sensor on = door is definitely open
        elif open_sensor_on:
            # Special case: if we're in motion from open->closed and open sensor briefly activates,
            # this is likely sensor noise - ignore it and maintain closing state
            if in_motion and self._previous_state == STATE_OPEN:
                _LOGGER.debug(
                    "In motion closing for '%s': ignoring brief open sensor activation (sensor noise)",
                    self._name
                )
                return STATE_CLOSING
            # Special case: if we're in motion from closed->open and we see open sensor,
            # this could be the end of motion - allow it through
            return STATE_OPEN
            
        # Closed sensor on = door is definitely closed  
        elif closed_sensor_on:
            # Special case: if we're in motion from closed->open and closed sensor briefly activates,
            # this is likely sensor noise - ignore it and maintain opening state
            if in_motion and self._previous_state == STATE_CLOSED:
                _LOGGER.debug(
                    "In motion opening for '%s': ignoring brief closed sensor activation (sensor noise)",
                    self._name
                )
                return STATE_OPENING
            # Special case: if we're in motion from open->closed and we see closed sensor,
            # this could be the end of motion - allow it through
            return STATE_CLOSED
            
        # 3. Both sensors off - this is where we need to handle motion logic carefully
        elif both_sensors_off:
            
            # If we're currently in motion, maintain the motion state and ignore sensor noise
            if in_motion:
                current_motion_state = None
                if self._previous_state == STATE_OPEN:
                    current_motion_state = STATE_CLOSING
                elif self._previous_state == STATE_CLOSED:
                    current_motion_state = STATE_OPENING
                
                if current_motion_state:
                    _LOGGER.debug(
                        "In motion for '%s': ignoring sensor noise, maintaining %s state",
                        self._name, current_motion_state
                    )
                    return current_motion_state
            
            # Not in motion - handle based on previous state
            # No previous state (first startup) = assume closed
            if not self._previous_state:
                _LOGGER.debug(
                    "Initial state determination for '%s': both sensors off, assuming closed",
                    self._name
                )
                return STATE_CLOSED
                
            # Previous state exists and not in motion = maintain previous definitive state
            # This handles cases where sensors temporarily go off but door hasn't actually moved
            elif self._previous_state in [STATE_OPEN, STATE_CLOSED]:
                _LOGGER.debug(
                    "Both sensors off for '%s', not in motion, maintaining previous state: %s",
                    self._name, self._previous_state
                )
                return self._previous_state
                
            # Previous state was a motion state but motion expired - need to determine final state
            # This is a fallback case that shouldn't normally happen
            else:
                _LOGGER.warning(
                    "Ambiguous state for '%s': both sensors off, motion expired, previous state was %s",
                    self._name, self._previous_state
                )
                return STATE_UNAVAILABLE
                
        # 4. All other cases - truly unavailable
        else:
            _LOGGER.warning(
                "Unexpected sensor combination for '%s': open=%s, closed=%s",
                self._name, open_sensor_on, closed_sensor_on
            )
            return STATE_UNAVAILABLE

    def _is_in_motion(self) -> bool:
        """
        Check if garage door is in motion based on tracked motion start time.
        """
        if not self._motion_start_time:
            return False
            
        time_since_motion_start = dt_util.utcnow() - self._motion_start_time
        seconds_since_motion_start = time_since_motion_start.total_seconds()
        within_duration = seconds_since_motion_start < self._motion_duration
        
        _LOGGER.debug(
            "Motion check for '%s': %.1fs since start, within_duration=%s",
            self._name, seconds_since_motion_start, within_duration
        )
        
        # Clear motion tracking if duration expired
        if not within_duration:
            _LOGGER.debug("Motion duration expired for '%s'", self._name)
            self._clear_motion_tracking()
        
        return within_duration

    def _schedule_motion_timeout(self) -> None:
        """Schedule a callback to check motion timeout after motion_duration seconds."""
        # Cancel any existing timeout
        if self._motion_timeout_unsub:
            self._motion_timeout_unsub()
            self._motion_timeout_unsub = None
        
        # Schedule new timeout check
        timeout_time = dt_util.utcnow() + timedelta(seconds=self._motion_duration)
        self._motion_timeout_unsub = async_track_point_in_time(
            self.hass, self._check_motion_timeout, timeout_time
        )
        
        _LOGGER.debug(
            "Scheduled motion timeout check for '%s' at %s", 
            self._name, timeout_time
        )

    @callback
    def _check_motion_timeout(self, now) -> None:
        """Callback to check if motion has timed out."""
        _LOGGER.debug("Motion timeout callback triggered for '%s'", self._name)
        
        # Force a state update to check current conditions
        self._update_state()
        self.async_write_ha_state()

    def _clear_motion_tracking(self) -> None:
        """Clear motion tracking and cancel any scheduled timeout."""
        self._motion_start_time = None
        
        if self._motion_timeout_unsub:
            self._motion_timeout_unsub()
            self._motion_timeout_unsub = None
            _LOGGER.debug("Cancelled motion timeout for '%s'", self._name)

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
        attributes = {
            ATTR_OPEN_SENSOR: self._open_sensor,
            ATTR_CLOSED_SENSOR: self._closed_sensor,
            ATTR_TOGGLE_ENTITY: self._toggle_entity,
            ATTR_MOTION_DURATION: self._motion_duration,
        }
        # Add motion tracking info for debugging
        if self._motion_start_time:
            time_since_motion = dt_util.utcnow() - self._motion_start_time
            attributes["motion_start_time"] = self._motion_start_time.isoformat()
            attributes["seconds_since_motion_start"] = round(time_since_motion.total_seconds(), 1)
        
        return attributes 

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        self._clear_motion_tracking()
        await super().async_will_remove_from_hass() 

    async def _delayed_entity_check(self) -> None:
        """Check for missing entities with a delay to handle startup timing issues."""
        import asyncio
        
        retry_attempts = 0
        max_retries = 3
        wait_times = [2, 5, 10]  # seconds to wait between attempts
        
        while retry_attempts < max_retries:
            await asyncio.sleep(wait_times[retry_attempts])
            
            # Check if any previously missing entities are now available
            all_entities_available = True
            for entity_id in self._entities_to_track:
                if not self.hass.states.get(entity_id):
                    all_entities_available = False
                    break
            
            if all_entities_available:
                _LOGGER.info(
                    "All required entities now available for sensor '%s', updating state",
                    self._name
                )
                self._update_state()
                self.async_write_ha_state()
                return
            
            retry_attempts += 1
            _LOGGER.debug(
                "Retry %d/%d: Some entities still missing for sensor '%s'",
                retry_attempts, max_retries, self._name
            )
        
        _LOGGER.warning(
            "After %d retry attempts, some entities are still missing for sensor '%s'",
            max_retries, self._name
        ) 