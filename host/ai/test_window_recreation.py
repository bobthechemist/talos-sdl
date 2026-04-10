#!/usr/bin/env python3
"""
Test script to verify matplotlib window recreation
"""
import sys
from pathlib import Path

# Setup project root path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

from host.ai.live_view_manager import LiveViewManager

def test_window_recreation():
    """Test that window can be recreated"""
    print("Testing window recreation logic...")

    manager = LiveViewManager()

    # First session
    session_id1, message1 = manager.start_session("HMC5883 X")
    if session_id1:
        print(f"[PASS] First session started: {session_id1}")
    else:
        print(f"[FAIL] First session failed: {message1}")

    # Check plot manager state
    print(f"Plot manager active: {manager.plot_manager.active}")
    print(f"Plot manager root exists: {manager.plot_manager.root is not None}")
    print(f"Plot manager window exists: {manager.plot_manager.root.winfo_exists() if manager.plot_manager.root else False}")

    # Stop first session
    if manager.stop_session(session_id1):
        print(f"[PASS] First session stopped")

    # Second session should recreate window
    session_id2, message2 = manager.start_session("HMC5883 X")
    if session_id2:
        print(f"[PASS] Second session started: {session_id2}")
    else:
        print(f"[FAIL] Second session failed: {message2}")

    # Check plot manager state again
    print(f"Plot manager active: {manager.plot_manager.active}")
    print(f"Plot manager root exists: {manager.plot_manager.root is not None}")
    print(f"Plot manager window exists: {manager.plot_manager.root.winfo_exists() if manager.plot_manager.root else False}")

    # Cleanup
    manager.cleanup_all()
    print("[PASS] Cleanup complete")

if __name__ == "__main__":
    test_window_recreation()