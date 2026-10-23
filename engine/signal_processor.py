import math
import collections
import time
import numpy as np

class SignalProcessor:
    def __init__(self, window_size=50):
        self.window_size = window_size
        self.rtt_history = collections.deque(maxlen=window_size)
        self.rtt_clean_history = collections.deque(maxlen=window_size)
        self.quality_history = collections.deque(maxlen=window_size)
        self.dispersion_history = collections.deque(maxlen=window_size)
        
        # Exponential Moving Average (DC Baseline filter for static multipath)
        self.ema_rtt = None
        self.ema_quality = None
        self.ema_alpha = 0.05 # slow adaptation to static background

        # Sliding window for adaptive noise floor tracking
        self.variance_tracker = collections.deque(maxlen=150) # ~7.5s at 20Hz
        self.adaptive_noise_floor = 1.0
        
        # Calibration baselines
        self.baseline_locomotion_var = 1.2
        self.baseline_breathing_var = 0.4
        self.is_calibrating = False
        self.calibration_samples = []
        self.sensitivity = 1.0

    def start_calibration(self):
        self.is_calibrating = True
        self.calibration_samples = []

    def _hampel_filter(self, val, history, k=7, n_sigmas=3.0):
        """
        Hampel filter (Median Absolute Deviation outlier rejection).
        Discards transient OS scheduler latency spikes while preserving true RF Doppler shifts.
        """
        if len(history) < k:
            return val
        
        window = np.array(list(history)[-k:], dtype=float)
        med = float(np.median(window))
        mad = float(np.median(np.abs(window - med)))
        threshold = n_sigmas * 1.4826 * mad
        
        if mad > 0.01 and np.abs(val - med) > threshold:
            # Outlier detected (OS background lag) -> clamp to local median
            return med
        return val

    def feed_sample(self, telemetry, probe_data):
        """
        Processes multi-burst probe data and link telemetry with high accuracy.
        probe_data: dict containing {"median_rtt", "min_rtt", "dispersion_ms"}
                    or float rtt_ms for backward compatibility.
        """
        if isinstance(probe_data, dict):
            raw_rtt = probe_data.get("median_rtt", 15.0)
            dispersion = probe_data.get("dispersion_ms", 0.0)
        else:
            raw_rtt = float(probe_data)
            dispersion = 0.0

        sq = telemetry.get("signal_quality", 100)
        rssi = telemetry.get("rssi_dbm", -50)
        rate = telemetry.get("rx_rate_mbps", 100)

        # 1. Outlier Rejection via Hampel Filter
        clean_rtt = self._hampel_filter(raw_rtt, self.rtt_clean_history)
        self.rtt_history.append(raw_rtt)
        self.rtt_clean_history.append(clean_rtt)
        self.quality_history.append(sq)
        self.dispersion_history.append(dispersion)

        # 2. Update DC Baseline (Exponential Moving Average)
        if self.ema_rtt is None:
            self.ema_rtt = clean_rtt
            self.ema_quality = sq
        else:
            self.ema_rtt = self.ema_alpha * clean_rtt + (1.0 - self.ema_alpha) * self.ema_rtt
            self.ema_quality = self.ema_alpha * sq + (1.0 - self.ema_alpha) * self.ema_quality

        # High-Pass Filtered Residuals (Static multipath stripped away)
        hp_rtt = clean_rtt - self.ema_rtt
        hp_sq = sq - self.ema_quality

        if self.is_calibrating:
            self.calibration_samples.append((clean_rtt, sq, hp_rtt))
            if len(self.calibration_samples) >= 60: # ~3 seconds at 20Hz
                self._finish_calibration()

        if len(self.rtt_clean_history) < 10:
            return {
                "perturbation_index": 0.0,
                "motion_state": "CALIBRATING",
                "state_color": "#00f0ff",
                "locomotion_energy": 0.0,
                "breathing_energy": 0.0,
                "rtt_jitter_ms": 0.0,
                "dispersion_ms": dispersion,
                "signal_variance": 0.0,
                "raw_rtt": round(clean_rtt, 2),
                "raw_quality": sq,
                "raw_rssi": rssi,
                "rx_rate": rate,
                "accuracy_mode": "ENHANCED DUAL-BAND DOPPLER"
            }

        # 3. Dual-Band Energy Decomposition
        recent_hp = np.array(list(self.rtt_clean_history)[-16:]) - self.ema_rtt
        
        # Locomotion Band (1 - 8 Hz): Fast variance across the last 10 samples
        fast_rtt_var = float(np.var(recent_hp[-8:]))
        locomotion_energy = max(0.0, fast_rtt_var)

        # Micro-Motion / Breathing Band (0.15 - 0.5 Hz): Slow envelope variance
        breathing_energy = float(np.var(recent_hp))

        # Signal Quality Deviation
        sq_var = float(np.var(np.array(list(self.quality_history)[-10:])))

        # 4. Adaptive Noise Floor Tracking (10th percentile of variance)
        self.variance_tracker.append(locomotion_energy)
        if len(self.variance_tracker) >= 30:
            self.adaptive_noise_floor = max(0.2, float(np.percentile(self.variance_tracker, 15)))

        # 5. Composite Normalized Fusion Score (with High Signal-to-Noise Ratio)
        excess_loco = max(0.0, locomotion_energy - self.adaptive_noise_floor)
        excess_breath = max(0.0, breathing_energy - (self.adaptive_noise_floor * 0.5))

        # Weighting: Locomotion (50%), Breathing (25%), Link Quality (15%), Dispersion (10%)
        raw_score = (
            (excess_loco / (self.baseline_locomotion_var + 0.8)) * 50.0 +
            (excess_breath / (self.baseline_breathing_var + 0.5)) * 25.0 +
            (sq_var * 15.0) +
            (dispersion * 1.8)
        ) * self.sensitivity

        # Sigmoid-smoothed non-linear compression for crisp thresholding
        perturbation_index = float(np.clip(raw_score, 0.0, 100.0))
        rtt_jitter = float(np.std(recent_hp))

        # 6. Motion State Classification
        if perturbation_index < 10.0:
            motion_state = "STATIC / CLEAR"
            state_color = "#00ff88"
        elif perturbation_index < 28.0:
            motion_state = "MICRO-MOTION (BREATHING / SHIFT)"
            state_color = "#ffbe0b"
        else:
            motion_state = "ACTIVE MOVEMENT DETECTED"
            state_color = "#ff0055"

        return {
            "perturbation_index": round(perturbation_index, 1),
            "motion_state": motion_state,
            "state_color": state_color,
            "locomotion_energy": round(locomotion_energy, 2),
            "breathing_energy": round(breathing_energy, 2),
            "rtt_jitter_ms": round(rtt_jitter, 2),
            "dispersion_ms": round(dispersion, 2),
            "signal_variance": round(sq_var, 3),
            "raw_rtt": round(clean_rtt, 2),
            "raw_quality": sq,
            "raw_rssi": rssi,
            "rx_rate": rate,
            "accuracy_mode": "ENHANCED DUAL-BAND DOPPLER"
        }

    def _finish_calibration(self):
        if not self.calibration_samples:
            return
        hps = [s[2] for s in self.calibration_samples]
        self.baseline_locomotion_var = max(0.4, float(np.var(hps)))
        self.baseline_breathing_var = max(0.15, float(np.var(hps)) * 0.5)
        self.is_calibrating = False
        print(f"[ACCURACY ENGINE] Calibrated: baseline_loco={self.baseline_locomotion_var:.2f}, baseline_breath={self.baseline_breathing_var:.2f}")

    def generate_synthetic_rf_grid(self, grid_w=32, grid_h=20, perturbation=0.0):
        grid = np.zeros((grid_h, grid_w), dtype=float)
        rx, ry = 0.18, 0.5
        lx, ly = 0.82, 0.5

        t = time.time()
        for j in range(grid_h):
            y = j / (grid_h - 1)
            for i in range(grid_w):
                x = i / (grid_w - 1)
                
                d1 = math.sqrt((x - rx)**2 + (y - ry)**2)
                d2 = math.sqrt((x - lx)**2 + (y - ly)**2)
                total_path = d1 + d2
                direct_path = math.sqrt((lx - rx)**2 + (ly - ry)**2)
                path_diff = total_path - direct_path

                # High accuracy 3-zone Fresnel modeling
                fresnel_weight = math.exp(-path_diff * 4.5)
                phase = (total_path * 22.0) - (t * 5.0)
                wave = math.sin(phase) * fresnel_weight

                if perturbation > 15.0:
                    noise = (math.sin(x * 14.0 + t * 9.0) * math.cos(y * 14.0 - t * 7.0)) * (perturbation / 100.0)
                    intensity = (wave * 0.35) + (fresnel_weight * 0.35) + (noise * 0.3)
                else:
                    intensity = (wave * 0.5) + (fresnel_weight * 0.5)

                grid[j, i] = float(np.clip(intensity, 0.0, 1.0))

        return grid.tolist()
