import threading
import time

class ESP32CSIReader:
    def __init__(self):
        self.available = False
        self.port_name = None
        self.serial_inst = None
        self.last_csi_vector = None
        self.running = False
        self._check_serial_ports()

    def _check_serial_ports(self):
        try:
            import serial.tools.list_ports
            ports = list(serial.tools.list_ports.comports())
            for p in ports:
                # Common USB-UART bridge chips used on ESP32 (CP2102, CH340, FTDI)
                desc = p.description.lower()
                if any(k in desc for k in ["cp210", "ch340", "ch9102", "usb-serial", "uart", "esp32"]):
                    self.port_name = p.device
                    self.available = True
                    print(f"[ESP32] Found potential CSI hardware on {self.port_name}: {p.description}")
                    return
        except ImportError:
            pass
        except Exception:
            pass

    def start_listening(self):
        if not self.available or not self.port_name:
            return
        # Background worker for serial frames if available
        pass

    def get_status(self):
        return {
            "hardware_connected": self.available,
            "port": self.port_name,
            "mode": "ESP32_CSI_RAW" if self.available else "NATIVE_WINDOWS_WLAN"
        }
