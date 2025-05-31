"""Cover platform for Smart Garage integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import SERVICE_TOGGLE, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

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
    ICON_GARAGE,
    ICON_GARAGE_OPEN,
    ICON_GARAGE_ALERT,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistant,
    config: dict[str, Any],
    async_add_entities: AddEntitiesCallback,
    discovery_info: dict[str, Any] | None = None,
) -> None:
    """Set up the Smart Garage covers from YAML configuration."""
    _LOGGER.debug("Setting up Smart Garage covers from YAML configuration")
    
    if DOMAIN not in hass.data:
        _LOGGER.debug("No Smart Garage data found in hass.data")
        return

    garages = hass.data[DOMAIN].get("garages", [])
    _LOGGER.debug("Found %d garage configurations in YAML", len(garages))
    
    entities = []

    for garage_config in garages:
        _LOGGER.debug("Creating cover for garage: %s", garage_config.get("name", "unknown"))
        cover = SmartGarageCover(hass, garage_config)
        entities.append(cover)

    _LOGGER.debug("Adding %d cover entities", len(entities))
    async_add_entities(entities, True)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Smart Garage covers from config entry."""
    _LOGGER.debug("Setting up Smart Garage cover from config entry: %s", config_entry.title)
    
    config = config_entry.data
    _LOGGER.debug("Config entry data: %s", config)
    
    cover = SmartGarageCover(hass, config)
    _LOGGER.debug("Created cover entity with unique_id: %s", cover.unique_id)
    
    async_add_entities([cover], True)


class SmartGarageCover(CoverEntity):
    """Representation of a Smart Garage Door cover."""

    def __init__(self, hass: HomeAssistant, config: dict[str, Any]) -> None:
        """Initialize the cover."""
        self.hass = hass
        self._config = config
        self._name = config["name"]
        self._open_sensor = config[ATTR_OPEN_SENSOR]
        self._closed_sensor = config[ATTR_CLOSED_SENSOR]
        self._toggle_entity = config[ATTR_TOGGLE_ENTITY]
        self._motion_duration = config.get(ATTR_MOTION_DURATION, 35)
        
        # Determine the domain and service to use for toggling
        self._toggle_domain = self._toggle_entity.split('.')[0] if self._toggle_entity else "switch"
        
        # Generate the sensor entity ID that corresponds to this cover
        sensor_id_suffix = self._name.lower().replace(' ', '_')
        self._sensor_entity_id = f"sensor.{DOMAIN}_{sensor_id_suffix}_state"
        
        self._attr_unique_id = f"{DOMAIN}_{sensor_id_suffix}_cover"
        self._attr_name = self._name
        self._attr_device_class = CoverDeviceClass.GARAGE
        self._attr_should_poll = False
        self._attr_supported_features = (
            CoverEntityFeature.OPEN
            | CoverEntityFeature.CLOSE
            | CoverEntityFeature.STOP
        )

        # Track the sensor state
        self._sensor_state = STATE_UNAVAILABLE
        
        _LOGGER.debug(
            "Initialized cover '%s' with config: open_sensor=%s, closed_sensor=%s, "
            "toggle_entity=%s, toggle_domain=%s, sensor_entity_id=%s",
            self._name, self._open_sensor, self._closed_sensor, 
            self._toggle_entity, self._toggle_domain, self._sensor_entity_id
        )

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()
        
        _LOGGER.debug("Cover '%s' added to hass, setting up state tracking", self._name)
        
        # Track state changes of the corresponding sensor
        async_track_state_change_event(
            self.hass, [self._sensor_entity_id], self._handle_sensor_state_change
        )
        
        _LOGGER.debug("Set up state tracking for sensor: %s", self._sensor_entity_id)
        
        # Initial state update with retry mechanism
        await self._delayed_initial_update()
        
        _LOGGER.debug(
            "Initial state for cover '%s': sensor_state=%s, available=%s",
            self._name, self._sensor_state, self._attr_available
        )

    async def _delayed_initial_update(self) -> None:
        """Initial state update with retry for sensor availability."""
        import asyncio
        
        # Try immediate update first
        self._update_from_sensor()
        
        if self._sensor_state == STATE_UNAVAILABLE:
            # Wait a bit for sensor to be fully registered and try again
            _LOGGER.debug("Sensor not found immediately, waiting 1 second and retrying...")
            await asyncio.sleep(1)
            self._update_from_sensor()
            
            if self._sensor_state == STATE_UNAVAILABLE:
                # One more try after another second
                _LOGGER.debug("Sensor still not found, waiting 2 more seconds and retrying...")
                await asyncio.sleep(2)
                self._update_from_sensor()
                
                if self._sensor_state == STATE_UNAVAILABLE:
                    _LOGGER.error(
                        "Sensor '%s' still not found after 3 seconds! "
                        "Available sensors: %s", 
                        self._sensor_entity_id,
                        [entity_id for entity_id in self.hass.states.async_entity_ids() 
                         if entity_id.startswith('sensor.')][:20]
                    )

    @callback
    def _handle_sensor_state_change(self, event) -> None:
        """Handle state changes of the sensor."""
        _LOGGER.debug(
            "Sensor state change event for cover '%s': %s", 
            self._name, event.data if event else "no event data"
        )
        
        self._update_from_sensor()
        self.async_write_ha_state()
        
        _LOGGER.debug(
            "Updated cover '%s' state: sensor_state=%s, available=%s",
            self._name, self._sensor_state, self._attr_available
        )

    @callback
    def _update_from_sensor(self) -> None:
        """Update cover state from sensor state."""
        sensor_state = self.hass.states.get(self._sensor_entity_id)
        
        _LOGGER.debug(
            "Updating cover '%s' from sensor '%s'", 
            self._name, self._sensor_entity_id
        )
        
        if sensor_state:
            _LOGGER.debug(
                "Sensor state found: state=%s, attributes=%s, last_changed=%s",
                sensor_state.state, sensor_state.attributes, sensor_state.last_changed
            )
            
            self._sensor_state = sensor_state.state
            self._attr_available = sensor_state.state != STATE_UNAVAILABLE
            
            _LOGGER.debug(
                "Updated cover '%s': sensor_state=%s, available=%s",
                self._name, self._sensor_state, self._attr_available
            )
        else:
            _LOGGER.warning(
                "Sensor '%s' not found for cover '%s'! Available sensors: %s",
                self._sensor_entity_id, self._name, 
                [entity_id for entity_id in self.hass.states.async_entity_ids() 
                 if entity_id.startswith('sensor.')][:10]  # Show first 10 sensors
            )
            
            self._sensor_state = STATE_UNAVAILABLE
            self._attr_available = False

    @property
    def is_closed(self) -> bool | None:
        """Return true if cover is closed, else False."""
        result = None
        if self._sensor_state == STATE_CLOSED:
            result = True
        elif self._sensor_state == STATE_OPEN:
            result = False
            
        _LOGGER.debug(
            "Cover '%s' is_closed: sensor_state=%s, result=%s",
            self._name, self._sensor_state, result
        )
        return result

    @property
    def is_opening(self) -> bool:
        """Return true if cover is opening."""
        result = self._sensor_state == STATE_OPENING
        _LOGGER.debug(
            "Cover '%s' is_opening: sensor_state=%s, result=%s",
            self._name, self._sensor_state, result
        )
        return result

    @property
    def is_closing(self) -> bool:
        """Return true if cover is closing."""
        result = self._sensor_state == STATE_CLOSING
        _LOGGER.debug(
            "Cover '%s' is_closing: sensor_state=%s, result=%s",
            self._name, self._sensor_state, result
        )
        return result

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend."""
        if self._sensor_state in [STATE_OPENING, STATE_CLOSING]:
            return ICON_GARAGE_ALERT
        elif self._sensor_state == STATE_OPEN:
            return ICON_GARAGE_OPEN
        else:
            return ICON_GARAGE

    async def _call_toggle_service(self) -> None:
        """Toggle the garage door entity (switch or light)."""
        if not self._toggle_entity:
            _LOGGER.error("No toggle entity configured for %s", self._name)
            return

        # Call the appropriate service based on the entity domain
        if self._toggle_domain == "light":
            service = "toggle"
            domain = "light"
        else:  # Default to switch
            service = SERVICE_TOGGLE
            domain = "switch"

        _LOGGER.debug(
            "Calling %s.%s for entity %s (garage: %s)",
            domain, service, self._toggle_entity, self._name
        )

        try:
            await self.hass.services.async_call(
                domain,
                service,
                {"entity_id": self._toggle_entity},
                blocking=True,
            )
            _LOGGER.debug("Successfully called %s.%s for %s", domain, service, self._toggle_entity)
        except Exception as ex:
            _LOGGER.error(
                "Failed to call %s.%s for %s: %s", 
                domain, service, self._toggle_entity, ex
            )

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        _LOGGER.debug(
            "Open cover requested for '%s': current_state=%s", 
            self._name, self._sensor_state
        )
        
        # Only open if sensor state is "closed"
        if self._sensor_state != STATE_CLOSED:
            _LOGGER.warning(
                "Cannot open %s: current state is %s, expected %s",
                self._name, self._sensor_state, STATE_CLOSED
            )
            return

        await self._call_toggle_service()

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        _LOGGER.debug(
            "Close cover requested for '%s': current_state=%s", 
            self._name, self._sensor_state
        )
        
        # Only close if sensor state is "open"
        if self._sensor_state != STATE_OPEN:
            _LOGGER.warning(
                "Cannot close %s: current state is %s, expected %s",
                self._name, self._sensor_state, STATE_OPEN
            )
            return

        await self._call_toggle_service()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        _LOGGER.debug(
            "Stop cover requested for '%s': current_state=%s", 
            self._name, self._sensor_state
        )
        
        # Only stop if cover is opening or closing
        if self._sensor_state not in [STATE_OPENING, STATE_CLOSING]:
            _LOGGER.warning(
                "Cannot stop %s: current state is %s, expected opening or closing",
                self._name, self._sensor_state
            )
            return

        await self._call_toggle_service()

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information about this garage door."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._attr_unique_id)},
            name=self._name,
            manufacturer="Smart Garage",
            model="Garage Door Cover",
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        return {
            ATTR_OPEN_SENSOR: self._open_sensor,
            ATTR_CLOSED_SENSOR: self._closed_sensor,
            ATTR_TOGGLE_ENTITY: self._toggle_entity,
            ATTR_MOTION_DURATION: self._motion_duration,
            "toggle_domain": self._toggle_domain,
            "sensor_entity_id": self._sensor_entity_id,
            "sensor_state": self._sensor_state,
        } 