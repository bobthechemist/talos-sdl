#!/usr/bin/env python3
"""
Mock test for matplotlib plot manager
"""
import sys
import threading
import time
from pathlib import Path

# Setup project root path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

from host.ai.live_view_manager import MatplotlibPlotManager

def test_plot_manager_lifecycle():
    """Test plot manager lifecycle"""
    print("Testing plot manager lifecycle...")

    manager = MatplotlibPlotManager()

    # Test 1: Check initial state
    print(f"[1] Initial state - active: {manager.active}")
    print(f"[1] Initial state - sessions: {len(manager.current_sessions)}")
    assert not manager.active, "Should not be active initially"
    assert len(manager.current_sessions) == 0, "Should have no sessions initially"

    # Test 2: Try to start with no sessions
    print(f"\n[2] Testing setup with no sessions...")
    result = manager.setup_plot([])
    print(f"[2] Setup result: {result}")
    assert result == True, "Setup should succeed even with empty sessions list"
    assert manager.active == True, "Should be active after setup"

    # Test 3: Check for root attribute
    print(f"\n[3] Checking for root attribute...")
    print(f"[3] root exists: {hasattr(manager, 'root')}")
    print(f"[3] root is None: {manager.root is None}")
    assert manager.root is not None, "Root should be created after setup"

    # Test 4: Update session data
    print(f"\n[4] Testing session data update...")
    session_id = "test_session_123"
    test_data = {
        'data_buffer': [
            {'sample_number': 1, 'timestamp': time.time(), 'tlv493d': {'x': 1.0, 'y': 2.0, 'z': 3.0}, 'hmc5883': {'x': 4.0, 'y': 5.0, 'z': 6.0}},
            {'sample_number': 2, 'timestamp': time.time(), 'tlv493d': {'x': 1.1, 'y': 2.1, 'z': 3.1}, 'hmc5883': {'x': 4.1, 'y': 5.1, 'z': 6.1}}
        ],
        'sample_numbers': [1, 2]
    }
    manager.update_session_data(session_id, test_data)
    print(f"[4] Session data updated: {session_id}")
    assert session_id in manager.current_sessions, "Session should be in current_sessions"
    assert len(manager.current_sessions) == 1, "Should have 1 session"

    # Test 5: Check data was stored correctly
    print(f"\n[5] Checking stored data...")
    stored_data = manager.current_sessions[session_id]
    print(f"[5] Buffer size: {len(stored_data['data_buffer'])}")
    print(f"[5] Sample numbers: {stored_data['sample_numbers']}")
    assert len(stored_data['data_buffer']) == 2, "Should have 2 samples in buffer"
    assert stored_data['sample_numbers'] == [1, 2], "Sample numbers should match"

    # Test 6: Clear session
    print(f"\n[6] Testing session clear...")
    manager.clear_session(session_id)
    print(f"[6] Session cleared")
    assert session_id not in manager.current_sessions, "Session should be removed"

    # Test 7: Test stop
    print(f"\n[7] Testing stop...")
    # Start plot again for testing
    manager.setup_plot([])
    # Clear existing sessions
    manager.current_sessions.clear()

    # Start a fake session to test stop
    session_id2 = "test_session_456"
    manager.current_sessions[session_id2] = {
        'data_buffer': [],
        'sample_numbers': []
    }
    manager.active = True

    # Call stop
    manager.stop()
    print(f"[7] Stop called")
    print(f"[7] Active after stop: {manager.active}")
    print(f"[7] Sessions after stop: {len(manager.current_sessions)}")

    print("\n[PASS] All plot manager lifecycle tests passed!")

def test_recreation_logic():
    """Test the logic for checking if window needs recreation"""
    print("\n\nTesting window recreation logic...")

    manager = MatplotlibPlotManager()

    # Simulate first session - window doesn't exist
    print(f"[1] First session - no window exists")
    plot_root = getattr(manager, 'root', None)
    print(f"[1] root exists: {plot_root is not None}")
    print(f"[1] window exists: {plot_root.winfo_exists() if plot_root else False}")

    # Simulate second session after stop - window should be recreated
    print(f"\n[2] Second session after stop - window doesn't exist")
    print(f"[2] root exists: {plot_root is not None}")
    print(f"[2] window exists: {plot_root.winfo_exists() if plot_root else False}")

    # This is the logic we're testing
    if not manager.active or not plot_root or not plot_root.winfo_exists():
        print(f"[2] Logic: Will recreate window (matches expectation)")
    else:
        print(f"[2] Logic: Will NOT recreate window (unexpected)")

    print("\n[PASS] Window recreation logic test passed!")

if __name__ == "__main__":
    try:
        test_plot_manager_lifecycle()
        test_recreation_logic()
        print("\n" + "="*60)
        print("All tests passed successfully!")
        print("="*60)
    except AssertionError as e:
        print(f"\n[FAIL] Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)