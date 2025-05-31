#!/usr/bin/env python3
"""
Test example demonstrating Smart Garage Door integration logic.
This is not a proper unit test, just a demonstration of the state logic.
"""

from datetime import datetime, timedelta


class MockGarageDoorLogic:
    """Mock implementation of garage door state logic for testing."""
    
    def __init__(self, opening_duration=35):
        self.opening_duration = opening_duration
        self.last_toggle_time = None
        
    def set_toggle_time(self, time_ago_seconds=0):
        """Set when the toggle switch was last activated."""
        self.last_toggle_time = datetime.utcnow() - timedelta(seconds=time_ago_seconds)
    
    def get_garage_state(self, open_sensor, closed_sensor):
        """
        Determine garage door state based on sensor inputs.
        
        Args:
            open_sensor: "on", "off", or "unavailable"
            closed_sensor: "on", "off", or "unavailable"
            
        Returns:
            "open", "closed", "opening", or "unavailable"
        """
        # Check for unavailable sensors
        if open_sensor == "unavailable" or closed_sensor == "unavailable":
            return "unavailable"
            
        # Convert to boolean for easier logic
        open_on = open_sensor == "on"
        closed_on = closed_sensor == "on"
        
        if open_on and not closed_on:
            return "open"
        elif not open_on and closed_on:
            return "closed"
        elif not open_on and not closed_on:
            # Check if we're in the opening window
            if self.last_toggle_time:
                time_since_toggle = (datetime.utcnow() - self.last_toggle_time).total_seconds()
                if time_since_toggle < self.opening_duration:
                    return "opening"
            return "unavailable"
        else:
            # Both sensors on - shouldn't happen
            return "unavailable"

    @staticmethod
    def get_toggle_service(entity_id):
        """Determine which service to call based on entity domain."""
        domain = entity_id.split('.')[0]
        if domain == "light":
            return "light", "toggle"
        elif domain == "switch":
            return "switch", "toggle"
        else:
            return None, None


def test_toggle_entity_logic():
    """Test toggle entity domain detection."""
    print("Toggle Entity Service Detection Test")
    print("=" * 40)
    
    test_entities = [
        ("switch.garage_door_1", "switch", "toggle"),
        ("light.shelly_garage_relay", "light", "toggle"),
        ("light.garage_door_opener", "light", "toggle"),
        ("switch.workshop_door", "switch", "toggle"),
        ("binary_sensor.invalid", None, None),
        ("sensor.invalid", None, None),
    ]
    
    for entity_id, expected_domain, expected_service in test_entities:
        domain, service = MockGarageDoorLogic.get_toggle_service(entity_id)
        status = "✓" if (domain, service) == (expected_domain, expected_service) else "✗"
        result = f"{domain}.{service}" if domain and service else "unsupported"
        print(f"{status} {entity_id} → {result}")


def test_garage_logic():
    """Test the garage door state logic."""
    garage = MockGarageDoorLogic(opening_duration=35)
    
    print("\nSmart Garage Door State Logic Test")
    print("=" * 40)
    
    # Test cases
    test_cases = [
        ("on", "off", None, "open"),
        ("off", "on", None, "closed"),
        ("off", "off", 10, "opening"),  # 10 seconds ago
        ("off", "off", 40, "unavailable"),  # 40 seconds ago (past opening duration)
        ("off", "off", None, "unavailable"),  # No toggle time
        ("on", "on", None, "unavailable"),  # Both sensors on
        ("unavailable", "off", None, "unavailable"),
        ("on", "unavailable", None, "unavailable"),
    ]
    
    for i, (open_sensor, closed_sensor, toggle_ago, expected) in enumerate(test_cases, 1):
        if toggle_ago is not None:
            garage.set_toggle_time(toggle_ago)
        else:
            garage.last_toggle_time = None
            
        result = garage.get_garage_state(open_sensor, closed_sensor)
        status = "✓" if result == expected else "✗"
        
        toggle_info = f"toggle {toggle_ago}s ago" if toggle_ago else "no toggle"
        print(f"Test {i}: {status} open={open_sensor}, closed={closed_sensor}, {toggle_info} → {result}")
        
        if result != expected:
            print(f"    Expected: {expected}, Got: {result}")
    
    print("\nCover Action Logic:")
    print("-" * 20)
    
    # Test cover actions
    action_tests = [
        ("closed", "open", True),
        ("open", "open", False),
        ("opening", "open", False),
        ("unavailable", "open", False),
        ("open", "close", True),
        ("closed", "close", False),
        ("opening", "close", False),
        ("unavailable", "close", False),
        ("opening", "stop", True),
        ("closing", "stop", True),
        ("open", "stop", False),
        ("closed", "stop", False),
    ]
    
    for state, action, should_work in action_tests:
        status = "✓" if should_work else "✗"
        result = "allowed" if should_work else "blocked"
        print(f"{status} {action} when {state}: {result}")


if __name__ == "__main__":
    test_toggle_entity_logic()
    test_garage_logic() 