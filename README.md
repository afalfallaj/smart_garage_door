# Smart Garage Door - Home Assistant Custom Component

A Home Assistant custom component that creates smart garage door entities from binary sensors (open/closed) and toggle switches/lights. This integration automatically manages garage door states including "opening" detection and provides proper cover entities for control.

## Features

- **Multiple Garage Doors**: Add as many garage doors as needed
- **Smart State Detection**: Automatically detects open, closed, opening, and unavailable states
- **Template Sensors**: Creates intelligent sensors that track garage door state
- **Template Covers**: Provides proper garage door cover entities with open/close/stop functionality
- **Switch & Light Support**: Works with both switch and light entities (perfect for Shelly devices)
- **UI Configuration**: Easy setup through Home Assistant's user interface
- **YAML Configuration**: Also supports traditional YAML configuration
- **Safety Logic**: Only allows operations when the garage door is in the correct state
- **HACS Compatible**: Easy installation through Home Assistant Community Store

## Installation

### HACS Installation (Recommended)

1. Open HACS in your Home Assistant instance
2. Go to "Integrations"
3. Click the three dots in the top right corner
4. Select "Custom repositories"
5. Add this repository URL and select "Integration" as the category
6. Click "Add"
7. Search for "Smart Garage Door" and install it
8. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/smart_garage` folder to your Home Assistant `custom_components` directory
2. Restart Home Assistant

## Configuration

### UI Configuration (Recommended)

1. Go to **Settings** → **Devices & Services** → **Integrations**
2. Click **+ Add Integration**
3. Search for "Smart Garage Door"
4. Follow the setup wizard:
   - Enter a name for your garage door
   - Select your open sensor (binary_sensor)
   - Select your closed sensor (binary_sensor)
   - Select your toggle entity (switch or light)
   - Set the opening duration (default: 35 seconds)
5. Click **Submit**

Repeat this process for each garage door you want to add.

### YAML Configuration

Add the following to your `configuration.yaml` file:

```yaml
smart_garage:
  garages:
    # Using a switch entity (traditional)
    - name: "Main Garage"
      open_sensor: binary_sensor.main_garage_open
      closed_sensor: binary_sensor.main_garage_closed
      toggle_entity: switch.main_garage_opener
      opening_duration: 35  # Optional, defaults to 35 seconds

    # Using a light entity (common with Shelly devices)
    - name: "Side Garage"
      open_sensor: binary_sensor.side_garage_open_sensor
      closed_sensor: binary_sensor.side_garage_closed_sensor
      toggle_entity: light.shelly_side_garage_relay
      opening_duration: 45  # Takes 45 seconds to open/close

    # Shelly device example
    - name: "Basement Garage"
      open_sensor: binary_sensor.shelly_door_sensor_1_input
      closed_sensor: binary_sensor.shelly_door_sensor_2_input  
      toggle_entity: light.shelly_1_channel_1  # Shelly relay exposed as light
      opening_duration: 40
```

### Configuration Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `name` | Yes | - | Friendly name for the garage door |
| `open_sensor` | Yes | - | Entity ID of the binary sensor that detects when the door is fully open |
| `closed_sensor` | Yes | - | Entity ID of the binary sensor that detects when the door is fully closed |
| `toggle_entity` | Yes | - | Entity ID of the switch or light that controls the garage door opener |
| `opening_duration` | No | 35 | Time in seconds to consider the door as "opening" after toggle |

### Supported Toggle Entities

The integration automatically detects the entity type and calls the appropriate service:

- **Switch entities** (`switch.*`): Calls `switch.toggle`
- **Light entities** (`light.*`): Calls `light.toggle`

This makes it perfect for Shelly devices that expose their relay outputs as light entities.

## Created Entities

For each configured garage door, the integration creates:

### Sensor Entities
- `sensor.smart_garage_[name]_state` - Shows the current state (open, closed, opening, unavailable)

### Cover Entities
- `cover.[name]` - Garage door cover entity with open/close/stop functionality

## State Logic

The integration uses the following logic to determine garage door states:

| Open Sensor | Closed Sensor | Time Since Toggle | State |
|-------------|---------------|-------------------|-------|
| ON | OFF | - | `open` |
| OFF | ON | - | `closed` |
| OFF | OFF | < opening_duration | `opening` |
| OFF | OFF | ≥ opening_duration | `unavailable` |
| ON | ON | - | `unavailable` |
| unavailable | - | - | `unavailable` |
| - | unavailable | - | `unavailable` |

## Usage Examples

### Automation Examples

```yaml
# Notify when garage door is left open
automation:
  - alias: "Garage Door Left Open"
    trigger:
      - platform: state
        entity_id: cover.main_garage
        to: "open"
        for:
          minutes: 10
    action:
      - service: notify.mobile_app
        data:
          message: "Garage door has been open for 10 minutes"

# Auto-close garage door at night
automation:
  - alias: "Close Garage at Night"
    trigger:
      - platform: time
        at: "22:00:00"
    condition:
      - condition: state
        entity_id: cover.main_garage
        state: "open"
    action:
      - service: cover.close_cover
        target:
          entity_id: cover.main_garage
```

### Script Examples

```yaml
# Emergency stop all garage doors
script:
  emergency_stop_garages:
    alias: "Emergency Stop All Garages"
    sequence:
      - service: cover.stop_cover
        target:
          entity_id:
            - cover.main_garage
            - cover.side_garage
            - cover.basement_garage
```

### Dashboard Card Example

```yaml
type: entities
entities:
  - entity: cover.main_garage
    name: Main Garage Door
  - entity: sensor.smart_garage_main_garage_state
    name: Main Garage State
  - entity: cover.side_garage
    name: Side Garage Door (Shelly Light)
  - entity: sensor.smart_garage_side_garage_state
    name: Side Garage State
```

## Shelly Device Integration

This integration works perfectly with Shelly devices:

```yaml
smart_garage:
  garages:
    - name: "Main Garage"
      open_sensor: binary_sensor.shelly_door_sensor_open
      closed_sensor: binary_sensor.shelly_door_sensor_closed
      toggle_entity: light.shelly_1_channel_1  # Shelly relay as light
      opening_duration: 35
```

## Safety Features

- **State Validation**: Cover operations only work when the garage door is in the appropriate state
- **Entity Type Detection**: Automatically uses the correct service for switch or light entities
- **Availability Checking**: Entities become unavailable if sensors are unavailable
- **UI Configuration**: User-friendly setup through Home Assistant interface
- **Logging**: Comprehensive logging for troubleshooting
- **Non-destructive**: Uses existing entities without modifying them

## Troubleshooting

### Enable Debug Logging

To troubleshoot issues (especially when covers show as "unavailable"), enable debug logging by adding this to your `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.smart_garage: debug
```

After adding this, restart Home Assistant and check the logs at **Settings** → **System** → **Logs** or in your Home Assistant log file.

### Debug Log Analysis

When covers show as "unavailable", look for these key log messages:

1. **Integration Setup**:
   ```
   Setting up Smart Garage from config entry: [Garage Name]
   ```

2. **Sensor Creation**:
   ```
   Created sensor entity with unique_id: smart_garage_[name]_state
   ```

3. **Entity Validation**:
   ```
   Tracked entity '[entity_id]' not found! Available entities: [list]
   ```

4. **Cover Dependency**:
   ```
   Sensor 'sensor.smart_garage_[name]_state' not found for cover '[name]'!
   ```

### Common Issues

1. **Entities not created**: Verify entity IDs in configuration exist and are correct
   - Check logs for "Tracked entity '[entity_id]' not found!"
   - Verify sensors exist in **Developer Tools** → **States**

2. **Cover shows "unavailable"**: Usually means the corresponding sensor isn't found
   - Look for: "Sensor 'sensor.smart_garage_[name]_state' not found for cover"
   - Verify the sensor entity was created successfully

3. **State stuck on "opening"**: Check if toggle entity ID is correct and state changes are detected
   - Look for toggle entity state changes in debug logs
   - Verify opening_duration setting is appropriate

4. **Toggle not working**: Verify the toggle entity domain (switch or light) is supported
   - Check logs for "Failed to call [domain].toggle for [entity]"
   - Ensure entity exists and is controllable

5. **UI configuration not available**: Restart Home Assistant after installation

### Debug Information to Collect

When reporting issues, please include:

1. **Configuration**: Your exact garage configuration (anonymize entity IDs if needed)
2. **Entity Status**: Check if your sensors and toggle entities exist in **Developer Tools** → **States**
3. **Debug Logs**: Relevant log entries with debug logging enabled
4. **Home Assistant Version**: Your HA version and when the issue started

### Log Example

Here's what successful setup should look like in debug logs:

```
[custom_components.smart_garage] Setting up Smart Garage from config entry: Main Garage
[custom_components.smart_garage.sensor] Created sensor entity with unique_id: smart_garage_main_garage_state
[custom_components.smart_garage.cover] Created cover entity with unique_id: smart_garage_main_garage_cover
[custom_components.smart_garage.sensor] Tracked entity 'binary_sensor.garage_open' found: state=off
[custom_components.smart_garage.sensor] Initial state for sensor 'Main Garage': value=closed, available=True
[custom_components.smart_garage.cover] Initial state for cover 'Main Garage': sensor_state=closed, available=True
```

## Requirements

- Home Assistant 2023.8.0 or newer
- Binary sensors for garage door open/closed detection
- Switch or light entity for garage door control

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

- Create an issue on GitHub for bugs or feature requests
- Check the Home Assistant Community forum for general questions
- Review the debug logs for troubleshooting information 