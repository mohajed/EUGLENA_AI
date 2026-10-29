import serial
import json
import time
from typing import Optional, Dict, Callable

class LightController:
    """
    Controller for Serial LED Driver.
    Protocol: JSON {"r":0-255, "g":..., "b":..., "w":..., "ir":...}
    """
    def __init__(self, log_cb: Optional[Callable[[str], None]] = None):
        self.ser: Optional[serial.Serial] = None
        self.log_cb = log_cb
        self.state = {
            "r": 0,
            "g": 0,
            "b": 0,
            "w": 0,
            "ir": 0
        }
        self.is_connected = False
        self.port = ""

    def log(self, msg: str):
        if self.log_cb:
            self.log_cb(msg)
        else:
            print(msg)

    def connect(self, port: str, baudrate: int = 115200) -> bool:
        """Connect to the serial port."""
        try:
            self.ser = serial.Serial(port, baudrate, timeout=1)
            self.port = port
            self.is_connected = True
            time.sleep(1) # Wait for connection to stabilize
            self.log(f"[LightController] Connected to {port}")
            return True
        except Exception as e:
            self.log(f"[LightController] Failed to connect to {port}: {e}")
            self.is_connected = False
            return False

    def close(self):
        """Close the serial connection."""
        if self.ser and self.ser.is_open:
            self.ser.close()
        self.is_connected = False

    def set_value(self, channel: str, value: int):
        """
        Set value for a specific channel and send update.
        Channel: 'r', 'g', 'b', 'w', 'ir' (mapped from 'i')
        """
        channel = channel.lower()
        if channel == 'i': channel = 'ir'
        
        if channel in self.state:
            self.state[channel] = max(0, min(1024, int(value)))
            self._send_update()

    def _send_update(self):
        """Send current state as JSON."""
        if not self.is_connected or not self.ser:
            return

        try:
            payload = json.dumps(self.state) + "\n"
            self.ser.write(payload.encode('utf-8'))
        except Exception as e:
            self.log(f"[LightController] Error sending data: {e}")

    def get_state(self) -> Dict[str, int]:
        return self.state.copy()
