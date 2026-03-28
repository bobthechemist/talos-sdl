import serial
from .postman import Postman

class SerialPostman(Postman):
    """
    Postman implementation for serial communication in standard Python.
    """

    def _open_channel(self):
        """Opens the serial port."""
        try:
            port = self.params.get("port")
            baudrate = self.params.get("baudrate", 115200)  # Default baudrate
            timeout = self.params.get("timeout", 1)  # Default timeout
            ser = serial.Serial(port, baudrate, timeout=timeout)
            return ser
        except serial.SerialException as e:
            raise IOError(f"Could not open serial port {self.params.get('port')}: {e}")

    def _close_channel(self):
        """Closes the serial port."""
        self.channel.close()

    def _send(self, value):
        """
        Sends data over the serial port.

        Parameters:
        value (any): The data to be sent. It will be converted to a string and encoded to bytes.
        """
        message = str(value)
        if not message.endswith('\n'):
            message += '\n'
        # Assuming you want to send a string, encode it to bytes
        data = message.encode('utf-8')  # Ensure the data is encoded as bytes
        self.channel.write(data)

    def _receive(self):
        """
        Receives data from the serial port.

        Returns:
        str: The received data as a string, stripped of any trailing whitespace.
        """
        # Read a line of data (terminated by newline character)
        data = self.channel.readline()
        # Decode the bytes to a string, stripping any trailing whitespace
        return data.decode('utf-8').strip()
