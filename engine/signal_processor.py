import math
import collections
import time
import numpy as np

class SignalProcessor:
    def __init__(self, window_size=60):
        self.window_size = window_size
        self.rtt_history = collections.deque(maxlen=window_size)
        self.rtt_clean_history = collections.deque(maxlen=window_size)
        self.rssi_history = collections.deque(maxlen=window_size)
        self.dispersion_history = collections.deque(maxlen=window_size)

        # Exponential Moving Average (DC Baseline filter for static multipath)
        self.ema_rtt = None
        self.ema_rssi = None
        self.ema_alpha = 0.08

        # Adaptive noise floor tracking
        self.energy_tracker = collections.deque(maxlen=150)
        self.adaptive_noise_floor = 0.5

        # Auto-calibrate on startup for the first 30 samples (~1.5s)
        self.baseline_locomotion_var = 1.5
        self.baseline_rssi_var = 0.25
        self.baseline_dispersion = 0.5
        self.is_calibrating = True
        self.calibration_samples = []
        self.sensitivity = 1.0

    def start_calibration(self):
        self.is_calibrating = True
        self.calibration_samples = []

    def _hampel_filter(self, val, history, k=9, n_sigmas=2.5):
        """
        Hampel filter (Median Absolute Deviation outlier rejection).
        Discards transient OS scheduler latency spikes while preserving true RF shifts.
        """
        if len(history) < k:
            return val

        window = np.array(list(history)[-k:], dtype=float)
        med = float(np.median(window))
        mad = float(np.median(np.abs(window - med)))
        threshold = max(1.5, n_sigmas * 1.4826 * mad)

        if np.abs(val - med) > threshold:
            return med
        return val

    def feed_sample(self, telemetry, probe_data):
        if isinstance(probe_data, dict):
            raw_rtt = probe_data.get("median_rtt", 2.5)
            dispersion = probe_data.get("dispersion_ms", 0.0)
        else:
            raw_rtt = float(probe_data)
            dispersion = 0.0

        sq = telemetry.get("signal_quality", 100)
        rssi = float(telemetry.get("rssi_dbm", -50))
        rate = telemetry.get("rx_rate_mbps", 100)

        # 1. Outlier rejection on RTT
        clean_rtt = self._hampel_filter(raw_rtt, self.rtt_clean_history)
        self.rtt_history.append(raw_rtt)
        self.rtt_clean_history.append(clean_rtt)
        self.rssi_history.append(rssi)
        self.dispersion_history.append(dispersion)

        # 2. Update DC Baselines
        if self.ema_rtt is None:
            self.ema_rtt = clean_rtt
            self.ema_rssi = rssi
        else:
            self.ema_rtt = self.ema_alpha * clean_rtt + (1.0 - self.ema_alpha) * self.ema_rtt
            self.ema_rssi = self.ema_alpha * rssi + (1.0 - self.ema_alpha) * self.ema_rssi

        hp_rtt = clean_rtt - self.ema_rtt
        hp_rssi = rssi - self.ema_rssi

        if self.is_calibrating:
            self.calibration_samples.append((hp_rtt, hp_rssi, dispersion))
            if len(self.calibration_samples) >= 30:
                self._finish_calibration()
            return {
                "perturbation_index": 0.0,
                "motion_state": "CALIBRATING...",
                "state_color": "#00f0ff",
                "locomotion_energy": 0.0,
                "breathing_energy": 0.0,
                "rtt_jitter_ms": 0.0,
                "dispersion_ms": round(dispersion, 2),
                "signal_variance": 0.0,
                "raw_rtt": round(clean_rtt, 2),
                "raw_quality": sq,
                "raw_rssi": int(rssi),
                "rx_rate": rate,
                "accuracy_mode": "DUAL-BAND DOPPLER + RAW RSSI"
            }

        # 3. Compute short-window and medium-window variances
        recent_rtt = np.array(list(self.rtt_clean_history)[-20:], dtype=float) - self.ema_rtt
        recent_rssi = np.array(list(self.rssi_history)[-20:], dtype=float) - self.ema_rssi
        recent_disp = np.array(list(self.dispersion_history)[-10:], dtype=float)

        # Fast locomotion energy (last 8 samples ~0.4s)
        locomotion_energy = float(np.var(recent_rtt[-8:]))
        # Breathing / slow envelope energy (last 20 samples ~1s)
        breathing_energy = float(np.var(recent_rtt))
        # Real unclamped RSSI dBm variance
        rssi_var = float(np.var(recent_rssi[-12:]))
        avg_disp = float(np.median(recent_disp))

        # 4. Adaptive noise floor tracking
        raw_energy = locomotion_energy + (rssi_var * 3.0)
        self.energy_tracker.append(raw_energy)
        if len(self.energy_tracker) >= 25:
            self.adaptive_noise_floor = max(0.15, float(np.percentile(self.energy_tracker, 20)))

        # 5. Baseline-subtracted excess signal
        excess_rtt = max(0.0, locomotion_energy - max(self.baseline_locomotion_var, self.adaptive_noise_floor))
        excess_rssi = max(0.0, rssi_var - self.baseline_rssi_var)
        excess_disp = max(0.0, avg_disp - self.baseline_dispersion)

        # Weighted physical disturbance score (unbounded)
        combined = (
            (excess_rssi * 18.0) +
            (excess_rtt * 2.5) +
            (excess_disp * 4.0)
        ) * self.sensitivity

        # Smooth asymptotic mapping to 0-100% (prevents instant pegging at 100%)
        perturbation_index = 100.0 * (1.0 - math.exp(-combined / 15.0))
        perturbation_index = float(np.clip(perturbation_index, 0.0, 100.0))

        rtt_jitter = float(np.std(recent_rtt[-12:]))

        # 6. Motion State Classification
        if perturbation_index < 12.0:
            motion_state = "STATIC / CLEAR"
            state_color = "#00ff88"
        elif perturbation_index < 30.0:
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
            "dispersion_ms": round(avg_disp, 2),
            "signal_variance": round(rssi_var, 3),
            "raw_rtt": round(clean_rtt, 2),
            "raw_quality": sq,
            "raw_rssi": int(rssi),
            "rx_rate": rate,
            "accuracy_mode": "DUAL-BAND DOPPLER + RAW RSSI"
        }

    def _finish_calibration(self):
        if not self.calibration_samples:
            return
        # Skip initial 5 warmup samples so socket warmup doesn't inflate baseline
        samples = self.calibration_samples[5:] if len(self.calibration_samples) > 10 else self.calibration_samples
        rtts = [s[0] for s in samples]
        rssis = [s[1] for s in samples]
        disps = [s[2] for s in samples]

        self.baseline_locomotion_var = max(0.25, float(np.var(rtts)) * 1.15)
        self.baseline_rssi_var = max(0.12, float(np.var(rssis)) * 1.1)
        self.baseline_dispersion = max(0.2, float(np.median(disps)) * 1.15)
        self.is_calibrating = False
        print(f"[ACCURACY ENGINE] Calibrated: rtt_var={self.baseline_locomotion_var:.2f}, rssi_var={self.baseline_rssi_var:.2f}, disp={self.baseline_dispersion:.2f}")

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
