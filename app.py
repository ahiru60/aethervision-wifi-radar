import asyncio
import json
import os
import time
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from engine.wifi_scanner import WindowsWlanScanner
from engine.rf_probe import GatewayRFProbe
from engine.signal_processor import SignalProcessor
from engine.esp32_serial import ESP32CSIReader

app = FastAPI(title="Wi-Fi Sensing & RF Radar Imaging")

# Disable caching for real-time frontend assets
@app.middleware("http")
async def add_no_cache_header(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# Serve static dashboard files
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Shared Engine Instances
wlan_scanner = WindowsWlanScanner()
rf_probe = GatewayRFProbe()
signal_processor = SignalProcessor()
esp32_reader = ESP32CSIReader()

# WebSocket client manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        if not self.active_connections:
            return
        msg_text = json.dumps(message)
        for connection in list(self.active_connections):
            try:
                await connection.send_text(msg_text)
            except Exception:
                self.disconnect(connection)

manager = ConnectionManager()
latest_payload = {}

async def telemetry_background_worker():
    """
    Continuous 10-15 Hz sampling loop.
    Extracts physical Wi-Fi fluctuations and broadcasts to all clients.
    """
    global latest_payload
    print("[SERVER] Telemetry background worker started.")
    
    while True:
        try:
            # 1. Grab Wi-Fi Link Telemetry from Windows WLAN API
            telem = wlan_scanner.get_connection_telemetry()
            if not telem:
                telem = {
                    "ssid": "Scanning...",
                    "bssid": "00:00:00:00:00:00",
                    "signal_quality": 50,
                    "rssi_dbm": -75,
                    "rx_rate_mbps": 0.0,
                    "tx_rate_mbps": 0.0,
                    "adapter": "WLAN Adapter"
                }

            # 2. Probe High-Resolution Packet Flight Latency Burst (3 probes per sample)
            loop = asyncio.get_event_loop()
            probe_data = await loop.run_in_executor(None, rf_probe.probe_burst_latency, 3)

            # 3. Process dual-band Doppler and perturbation index
            sensing = signal_processor.feed_sample(telem, probe_data)

            # 4. Generate 2D spatial RF interference grid (24x15)
            rf_grid = signal_processor.generate_synthetic_rf_grid(
                grid_w=24,
                grid_h=15,
                perturbation=sensing["perturbation_index"]
            )

            # 5. Build full payload
            latest_payload = {
                "timestamp": round(time.time(), 3),
                "telemetry": telem,
                "sensing": sensing,
                "rf_field": rf_grid,
                "hardware": esp32_reader.get_status(),
                "router_gateway": rf_probe.target_ip
            }

            # 6. Broadcast over WebSocket
            await manager.broadcast(latest_payload)

        except Exception as e:
            print(f"[Worker Error] {e}")

        # High-precision 20 Hz sampling rate (~50ms interval)
        await asyncio.sleep(0.05)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(telemetry_background_worker())

@app.get("/")
async def get_index():
    return FileResponse(os.path.join(static_dir, "index.html"))

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Send initial snapshot immediately
        if latest_payload:
            await websocket.send_text(json.dumps(latest_payload))
        while True:
            # Keep-alive / incoming command receiver
            data = await websocket.receive_text()
            cmd = json.loads(data)
            if cmd.get("action") == "calibrate":
                signal_processor.start_calibration()
                await websocket.send_text(json.dumps({"status": "CALIBRATING_STARTED"}))
            elif cmd.get("action") == "set_sensitivity":
                val = float(cmd.get("value", 1.0))
                signal_processor.sensitivity = val
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)

class SensitivityModel(BaseModel):
    value: float

@app.post("/api/calibrate")
async def trigger_calibrate():
    signal_processor.start_calibration()
    return {"status": "ok", "message": "Calibrating room baseline for 3 seconds..."}

@app.post("/api/sensitivity")
async def set_sensitivity(payload: SensitivityModel):
    signal_processor.sensitivity = max(0.1, min(5.0, payload.value))
    return {"status": "ok", "sensitivity": signal_processor.sensitivity}

@app.get("/api/telemetry")
async def get_telemetry():
    return latest_payload
