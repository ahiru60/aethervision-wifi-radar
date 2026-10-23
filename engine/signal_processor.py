import math
import collections
import time
import numpy as np

class SignalProcessor:
    def __init__(self, window_size=30):
        self.window_size = window_size
        self.rtt_history = collections.deque(maxlen=window_size)
        self.quality_history = collections.deque(maxlen=window_size)
        self.rssi_history = collections.deque(maxlen=window_size)
        self.rate_history = collections.deque(maxlen=window_size)
        
        # Calibration baselines
        self.baseline_rtt_var = 1.5
        self.baseline_quality_var = 0.5
        self.is_calibrating = False
        self.calibration_samples = []
        self.sensitivity = 1.0 # Multiplier (user adjustable)

    def start_calibration(self):
        self.is_calibrating = True
        self.calibration_samples = []

    def feed_sample(self, telemetry, rtt_ms):
        """
        Processes a raw incoming sample and computes the real-time perturbation metrics.
        """
        sq = telemetry.get("signal_quality", 100)
        rssi = telemetry.get("rssi_dbm", -50)
        rate = telemetry.get("rx_rate_mbps", 100)

        self.rtt_history.append(rtt_ms)
        self.quality_history.append(sq)
        self.rssi_history.append(rssi)
        self.rate_history.append(rate)

        if self.is_calibrating:
            self.calibration_samples.append((rtt_ms, sq))
            if len(self.calibration_samples) >= 40: # ~2-3 seconds at 15Hz
                self._finish_calibration()

        # Compute rolling statistics
        if len(self.rtt_history) < 5:
            return {
                "perturbation_index": 0.0,
                "motion_state": "CALIBRATING",
                "rtt_jitter": 0.0,
                "signal_var": 0.0,
                "raw_rtt": rtt_ms,
                "raw_quality": sq,
                "raw_rssi": rssi,
                "rx_rate": rate
            }

        rtt_arr = np.array(self.rtt_history)
        quality_arr = np.array(self.quality_history)

        rtt_var = float(np.var(rtt_arr[-10:])) # fast reaction window
        quality_var = float(np.var(quality_arr[-10:]))
        rtt_jitter = float(np.std(rtt_arr))

        # Relative change against baseline
        norm_rtt_impact = max(0.0, (rtt_var - self.baseline_rtt_var) / (self.baseline_rtt_var + 5.0))
        norm_quality_impact = max(0.0, (quality_var - self.baseline_quality_var) / (self.baseline_quality_var + 1.0))

        # Composite Perturbation Index (0 to 100)
        raw_score = (norm_rtt_impact * 25.0 + norm_quality_impact * 35.0 + (rtt_jitter * 1.5)) * self.sensitivity
        perturbation_index = float(np.clip(raw_score, 0.0, 100.0))

        # Classify motion state
        if perturbation_index < 12.0:
            motion_state = "STATIC / CLEAR"
            state_color = "#00ff88"
        elif perturbation_index < 35.0:
            motion_state = "MICRO-MOTION (BREATHING / SHIFT)"
            state_color = "#ffcc00"
        else:
            motion_state = "ACTIVE MOVEMENT DETECTED"
            state_color = "#ff3366"

        return {
            "perturbation_index": round(perturbation_index, 1),
            "motion_state": motion_state,
            "state_color": state_color,
            "rtt_jitter_ms": round(rtt_jitter, 2),
            "signal_variance": round(quality_var, 3),
            "raw_rtt": round(rtt_ms, 2),
            "raw_quality": sq,
            "raw_rssi": rssi,
            "rx_rate": rate
        }

    def _finish_calibration(self):
        if not self.calibration_samples:
            return
        rtts = [s[0] for s in self.calibration_samples]
        sqs = [s[1] for s in self.calibration_samples]
        self.baseline_rtt_var = max(0.5, float(np.var(rtts)))
        self.baseline_quality_var = max(0.1, float(np.var(sqs)))
        self.is_calibrating = False
        print(f"[PROCESSOR] Calibrated: baseline_rtt_var={self.baseline_rtt_var:.2f}, baseline_quality_var={self.baseline_quality_var:.2f}")

    def generate_synthetic_rf_grid(self, grid_w=32, grid_h=20, perturbation=0.0):
        """
        Synthesizes a 2D spatial RF field between Router (0.2, 0.5) and Laptop (0.8, 0.5).
        Returns a normalized grid representing the Fresnel multipath scattering field.
        """
        grid = np.zeros((grid_h, grid_w), dtype=float)
        
        # Router position (left) and Laptop position (right) in normalized [0, 1] coords
        rx, ry = 0.2, 0.5
        lx, ly = 0.8, 0.5

        t = time.time()
        carrier_freq = 2.4e9
        wavelength = 3e8 / carrier_freq # ~0.125m

        for j in range(grid_h):
            y = j / (grid_h - 1)
            for i in range(grid_w):
                x = i / (grid_w - 1)
                
                # Distance to router and laptop
                d1 = math.sqrt((x - rx)**2 + (y - ry)**2)
                d2 = math.sqrt((x - lx)**2 + (y - ly)**2)
                total_path = d1 + d2
                direct_path = math.sqrt((lx - rx)**2 + (ly - ry)**2)
                
                path_diff = total_path - direct_path
                # Fresnel zone intensity
                fresnel_weight = math.exp(-path_diff * 4.0)
                
                # Standing wave / interference phase pattern
                phase = (total_path * 20.0) - (t * 4.0)
                wave = math.sin(phase) * fresnel_weight
                
                # Inject perturbation noise in line-of-sight & reflection field
                if perturbation > 15.0:
                    noise = (math.sin(x * 12.0 + t * 8.0) * math.cos(y * 12.0 - t * 6.0)) * (perturbation / 100.0)
                    intensity = (wave * 0.4) + (fresnel_weight * 0.3) + (noise * 0.3)
                else:
                    intensity = (wave * 0.5) + (fresnel_weight * 0.5)

                grid[j, i] = float(np.clip(intensity, 0.0, 1.0))

        return grid.tolist()
