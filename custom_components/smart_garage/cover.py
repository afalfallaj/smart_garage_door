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
    ATTR_OPENING_DURATION,
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
    if DOMAIN not in hass.data:
        return

    garages = hass.data[DOMAIN].get("garages", [])
    entities = []

    for garage_config in garages:
        cover = SmartGarageCover(hass, garage_config)
        entities.append(cover)

    async_add_entities(entities, True)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Smart Garage covers from config entry."""
    config = config_entry.data
    cover = SmartGarageCover(hass, config)
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
        self._opening_duration = config.get(ATTR_OPENING_DURATION, 35)
        
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

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()
        
        # Track state changes of the corresponding sensor
        async_track_state_change_event(
            self.hass, [self._sensor_entity_id], self._handle_sensor_state_change
        )
        
        # Initial state update
        self._update_from_sensor()

    @callback
    def _handle_sensor_state_change(self, event) -> None:
        """Handle state changes of the sensor."""
        self._update_from_sensor()
        self.async_write_ha_state()

    @callback
    def _update_from_sensor(self) -> None:
        """Update cover state from sensor state."""
        sensor_state = self.hass.states.get(self._sensor_entity_id)
        
        if sensor_state:
            self._sensor_state = sensor_state.state
            self._attr_available = sensor_state.state != STATE_UNAVAILABLE
        else:
            self._sensor_state = STATE_UNAVAILABLE
            self._attr_available = False

    @property
    def is_closed(self) -> bool | None:
        """Return true if cover is closed, else False."""
        if self._sensor_state == STATE_CLOSED:
            return True
        elif self._sensor_state == STATE_OPEN:
            return False
        return None

    @property
    def is_opening(self) -> bool:
        """Return true if cover is opening."""
        return self._sensor_state == STATE_OPENING

    @property
    def is_closing(self) -> bool:
        """Return true if cover is closing."""
        return self._sensor_state == STATE_CLOSING

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

        await self.hass.services.async_call(
            domain,
            service,
            {"entity_id": self._toggle_entity},
            blocking=True,
        )

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
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
            ATTR_OPENING_DURATION: self._opening_duration,
            "toggle_domain": self._toggle_domain,
            "sensor_entity_id": self._sensor_entity_id,
            "sensor_state": self._sensor_state,
        } 