import sys

def check_if_microcontroller() -> bool:
    """
    Determine if the code is running on a microcontroller using CircuitPython.

    Returns:
        bool: True if the code is running on CircuitPython, False otherwise.
    """
    try:
        if sys.implementation.name == 'circuitpython':
            return True
    except Exception as e:
        print(f"An error occurred: {e}")
    return False
