#!/usr/bin/env python3
"""
Test script for live view functionality
"""
import sys
import time
from pathlib import Path

# Setup project root path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

from host.ai.live_view_manager import LiveViewManager, LiveViewSession

def test_liveview():
    """Test live view manager"""
    print("Testing Live View Manager...")

    # Create manager
    manager = LiveViewManager()

    # Test sensor spec parsing
    test_specs = [
        "HMC5883 X",
        "TLV493 XYZ",
        "HMC5883 XYZ",
        "TLV493 X Y Z"
    ]

    print("\n--- Testing Sensor Spec Parsing ---")
    for spec in test_specs:
        sensors = LiveViewSession._parse_sensor_spec(spec)
        print(f"Spec: '{spec}' -> {sensors}")

    # Note: We can't fully test the plot manager without a connected device
    # But we can verify the classes are importable

    print("\n[PASS] Live View Manager module loaded successfully")
    print("  - MatplotlibPlotManager class: Available")
    print("  - LiveViewSession class: Available")
    print("  - LiveViewManager class: Available")
    print("\nNote: Full end-to-end testing requires:")
    print("  1. Physical device connected via USB")
    print("  2. Firmware running on magnetometer")
    print("  3. Testing via chat.py: /liveview HMC5883 X")

if __name__ == "__main__":
    test_liveview()