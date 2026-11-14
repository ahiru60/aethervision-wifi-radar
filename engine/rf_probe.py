import socket
import time
import subprocess
import re
import numpy as np

class GatewayRFProbe:
    def __init__(self, target_ip=None, port=None):
        self.target_ip = target_ip or self._detect_default_gateway() or "192.168.1.1"
        self.port = port or self._detect_fast_tcp_port()

    def _detect_default_gateway(self):
        try:
            out = subprocess.check_output('route print 0.0.0.0', shell=True).decode()
            m = re.search(r'0\.0\.0\.0\s+0\.0\.0\.0\s+(\d+\.\d+\.\d+\.\d+)', out)
            if m:
                return m.group(1)
        except Exception:
            pass
        return "192.168.1.1"

    def _detect_fast_tcp_port(self):
        """Find a responsive router port (80, 443, 53) that replies immediately via SYN-ACK or RST."""
        for p in (80, 443, 53):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.15)
            try:
                s.connect((self.target_ip, p))
                s.close()
                return p
            except ConnectionRefusedError:
                # RST still proves immediate L2/L3 round-trip across Wi-Fi
                s.close()
                return p
            except Exception:
                s.close()
        return 80

    def _single_tcp_probe(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.06) # 60ms hard cap
        t0 = time.perf_counter()
        try:
            s.connect((self.target_ip, self.port))
            rtt_ms = (time.perf_counter() - t0) * 1000.0
        except ConnectionRefusedError:
            rtt_ms = (time.perf_counter() - t0) * 1000.0
        except socket.timeout:
            rtt_ms = 60.0
        except Exception:
            rtt_ms = (time.perf_counter() - t0) * 1000.0
        finally:
            try:
                s.close()
            except Exception:
                pass
        return rtt_ms

    def probe_burst_latency(self, burst_count=4):
        """
        Sends a micro-burst train of TCP probes to the router.
        Uses median and interquartile range (IQR) to eliminate single-packet contention spikes.
        """
        rtts = [self._single_tcp_probe() for _ in range(burst_count)]
        rtts_arr = np.array(rtts, dtype=float)

        # Reject timeout outliers if at least one packet succeeded
        valid = rtts_arr[rtts_arr < 55.0]
        if len(valid) == 0:
            valid = rtts_arr

        median_rtt = float(np.median(valid))
        min_rtt = float(np.min(valid))
        # IQR is far more resilient to single-packet spikes than standard deviation
        q75, q25 = np.percentile(valid, [75, 25])
        dispersion = float(q75 - q25)

        return {
            "median_rtt": round(median_rtt, 2),
            "min_rtt": round(min_rtt, 2),
            "dispersion_ms": round(dispersion, 2)
        }

    def probe_flight_latency(self):
        res = self.probe_burst_latency(burst_count=4)
        return res["median_rtt"]

    def close(self):
        pass
