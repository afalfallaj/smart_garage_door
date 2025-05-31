"""Constants for the Smart Garage integration."""

DOMAIN = "smart_garage"

# Default motion duration in seconds
DEFAULT_MOTION_DURATION = 35

# Entity attributes
ATTR_OPEN_SENSOR = "open_sensor"
ATTR_CLOSED_SENSOR = "closed_sensor"
ATTR_TOGGLE_ENTITY = "toggle_entity"
ATTR_MOTION_DURATION = "motion_duration"

# States
STATE_OPENING = "opening"
STATE_CLOSING = "closing"
STATE_OPEN = "open"
STATE_CLOSED = "closed"
STATE_UNAVAILABLE = "unavailable"

# Icons
ICON_GARAGE = "mdi:garage"
ICON_GARAGE_OPEN = "mdi:garage-open"
ICON_GARAGE_ALERT = "mdi:garage-alert"

# Supported toggle entity domains
TOGGLE_DOMAINS = ["switch", "light"]

# Configuration flow steps
STEP_USER = "user"
STEP_GARAGE = "garage" 