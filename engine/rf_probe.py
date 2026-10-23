import socket
import time
import subprocess
import re
import numpy as np

class GatewayRFProbe:
    def __init__(self, target_ip=None, port=53):
        self.port = port
        self.target_ip = target_ip or self._detect_default_gateway() or "192.168.1.1"
        self.sock = None
        self._init_socket()
        # High-speed DNS query packet
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
            self.sock.settimeout(0.04) # 40ms timeout per probe
        except Exception as e:
            print(f"[RFProbe] Socket init failed: {e}")

    def probe_burst_latency(self, burst_count=3):
        """
        Sends a micro-burst train of 3 back-to-back probes per sampling cycle.
        Returns:
            median_rtt: Robust median flight time (rejects single-packet transmission hiccups)
            jitter_dispersion: Inter-packet dispersion (variance across the train)
            min_rtt: The physical propagation lower bound
        """
        if not self.sock:
            self._init_socket()

        rtts = []
        for _ in range(burst_count):
            t0 = time.perf_counter()
            try:
                self.sock.sendto(self.dns_query, (self.target_ip, self.port))
                data, _ = self.sock.recvfrom(512)
                rtt_ms = (time.perf_counter() - t0) * 1000.0
                rtts.append(rtt_ms)
            except (socket.timeout, Exception):
                rtts.append(40.0)

        rtts_arr = np.array(rtts)
        median_rtt = float(np.median(rtts_arr))
        min_rtt = float(np.min(rtts_arr))
        dispersion = float(np.std(rtts_arr))

        return {
            "median_rtt": round(median_rtt, 2),
            "min_rtt": round(min_rtt, 2),
            "dispersion_ms": round(dispersion, 2)
        }

    # Backward compatible call
    def probe_flight_latency(self):
        res = self.probe_burst_latency(burst_count=3)
        return res["median_rtt"]

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
