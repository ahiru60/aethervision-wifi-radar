import uvicorn
import webbrowser
import time
import threading

def open_browser():
    time.sleep(1.2)
    print("\n[AetherVision] Launching interface at http://localhost:8000 ...")
    webbrowser.open("http://localhost:8000")

if __name__ == "__main__":
    print("=" * 60)
    print("  AETHER-VISION // WI-FI SENSING & RF RADAR")
    print("  Bistatic Microwave Perturbation & 2D Spatial Visualizer")
    print("=" * 60)
    print("[*] Starting backend on http://127.0.0.1:8000")
    
    threading.Thread(target=open_browser, daemon=True).start()
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False, log_level="warning")
