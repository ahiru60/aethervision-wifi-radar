import socket
import time
import subprocess
import re

class GatewayRFProbe:
    def __init__(self, target_ip=None, port=53):
        self.port = port
        self.target_ip = target_ip or self._detect_default_gateway() or "192.168.1.1"
        self.sock = None
        self._init_socket()
        # Standard DNS query packet for high-speed probe
        self.dns_query = b'\xaa\xbb\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x06router\x00\x00\x01\x00\x01'

    def _detect_default_gateway(self):
        try:
            out = subprocess.check_output('route print 0.0.0.0', shell=True).decode()
            m = re.search(r'0\.0\.0\.0\s+0\.0\.0\.0\s+(\d+\.\d+\.\d+\.\d+)', out)
            if m:
                return m.group(1)
        except Exception:
            pass
        return "192.168.1.1"

    def _init_socket(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.settimeout(0.08) # 80ms timeout max
        except Exception as e:
            print(f"[RFProbe] Socket init failed: {e}")

    def probe_flight_latency(self):
        """
        Sends a micro-probe to the router and measures the exact round-trip flight time in milliseconds.
        Reflections and physical movement alter queueing and transmission retry jitter.
        """
        if not self.sock:
            self._init_socket()
        
        t0 = time.perf_counter()
        try:
            self.sock.sendto(self.dns_query, (self.target_ip, self.port))
            data, _ = self.sock.recvfrom(512)
            rtt_ms = (time.perf_counter() - t0) * 1000.0
            return round(rtt_ms, 2)
        except socket.timeout:
            # Dropped frame / high interference
            return 80.0
        except Exception:
            # Fallback TCP quick connect attempt
            return self._probe_tcp_fallback()

    def _probe_tcp_fallback(self):
        t0 = time.perf_counter()
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.08)
            s.connect((self.target_ip, 80))
            s.close()
            return round((time.perf_counter() - t0) * 1000.0, 2)
        except Exception:
            return round((time.perf_counter() - t0) * 1000.0, 2)

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
