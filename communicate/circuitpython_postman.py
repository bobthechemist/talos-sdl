# communicate/circuitpython_postman.py
#type: ignore
import usb_cdc  # Make sure this is not commented out
from .postman import Postman

class CircuitPythonPostman(Postman):
    """
    Postman implementation for serial communication using data line in CircuitPython.
    usb_cdc.enable(console=True, data=True) belongs in boot.py
    """

    def _open_channel(self):
        """Opens the serial port."""
        return usb_cdc.data

    def _close_channel(self):
        """Closes the serial port."""
        # Nothing to do here

    def _send(self, value):
        """
        Sends data over the serial port.
        
        Parameters:
        value (any): The data to be sent. It will be converted to a string and encoded as bytes.
        """
        message = str(value)
        if not message.endswith('\n'):
            message += '\n'
        # Assuming you want to send a string, encode it to bytes
        data = message.encode('utf-8')  # Ensure the data is encoded as bytes
        self.channel.write(data)

    def _receive(self):
        """
        Receives data from the serial port in a NON-BLOCKING way.
        
        Returns:
        str: The received data as a string, or an empty string if no data is available.
        """
        # --- FIX IS HERE ---
        # First, check if there is any data waiting to be read.
        if self.channel.in_waiting > 0:
            # If there is data, read one line.
            data = self.channel.readline()
            # Decode the bytes to a string, stripping any trailing whitespace.
            return data.decode('utf-8').strip()
        
        # If no data is waiting, return an empty string immediately.
        # This prevents the main loop from blocking.
        return ""
