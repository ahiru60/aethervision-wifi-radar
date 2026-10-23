# AETHER-VISION // Wi-Fi Sensing & RF Radar Imaging

A real-time Wi-Fi sensing and microwave radar visualizer designed to run on Windows without modifying, hacking, or risking your home router firmware.

---

## ⚡ How It Works

1. **Zero-Touch Router Integration:**
   * Your router (`DEEZNTUS` at `192.168.1.1`) remains completely untouched and continues providing normal internet.
   * It acts as a continuous 2.4 GHz microwave radio transmitter beacon.

2. **Native Windows Physical Layer Telemetry:**
   * Uses Windows `wlanapi.dll` via `ctypes` to read real-time link telemetry, RSSI, and signal quality directly from your Wi-Fi card (`Realtek 802.11ac`).
   * High-frequency micro-probes track packet flight latency (RTT) and jitter variations in sub-millisecond resolution.

3. **Multipath Perturbation Engine:**
   * When a person walks or moves between the laptop and the router, microwave reflections scatter, creating phase shifts, amplitude dips, and jitter spikes.
   * The signal processor computes a composite **Perturbation Index (0–100%)** and classifies motion into:
     - `STATIC / CLEAR`
     - `MICRO-MOTION (BREATHING / SHIFT)`
     - `ACTIVE MOVEMENT DETECTED`

4. **2D Spatial RF Imaging Canvas:**
   * Visualizes the Fresnel reflection zone and RF interference field between the Router (TX) and Laptop (RX).
   * Renders real-time wave perturbations, dynamic microwave beam jitter, and target scatter echoes.

5. **Hardware Upgrade Port (Plug-and-Play):**
   * If you plug an inexpensive **ESP32 microcontroller (~$4)** into your laptop's USB port, the app auto-detects it and can ingest raw 64-subcarrier OFDM CSI (Channel State Information) vectors for high-resolution imaging.

---

## 🚀 How to Run

From this directory, simply run:

```powershell
python run.py
```

This will automatically launch the dashboard in your browser at:
👉 **`http://localhost:8000`**

---

## 🎮 How to Use the App

1. **Calibrate Baseline:**
   * When you start the app, stand still or step out of the direct line of sight for 3 seconds and click **"CALIBRATE QUIET ROOM"**.
   * The engine sets an adaptive noise floor baseline for your current room layout.
2. **Test Movement:**
   * Walk between your laptop and your router. Watch the **Perturbation Index** spike and the radar beam glitch with dynamic scatter echoes!
   * Try sitting still and taking deep breaths to observe the micro-motion sensitivity.
3. **Adjust Sensitivity:**
   * Use the slider in the sidebar to increase or decrease sensitivity (0.5x to 3.0x).
4. **Audio Alarm:**
   * Toggle **"AUDIO INTRUSION CHIME"** to get a subtle radar sound whenever movement crosses the threshold.
