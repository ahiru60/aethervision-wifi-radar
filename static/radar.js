// AetherVision // High-Precision Wi-Fi RF Sensing & Radar Visualizer

const radarCanvas = document.getElementById('radarCanvas');
const radarCtx = radarCanvas.getContext('2d');
const timelineCanvas = document.getElementById('timelineCanvas');
const timelineCtx = timelineCanvas.getContext('2d');

// 3D Scene Instance
let scene3D = null;
let currentViewMode = '3D'; // '3D' or '2D'

// State Histories
const MAX_HISTORY = 140;
const historyPerturb = new Array(MAX_HISTORY).fill(0);
const historyRtt = new Array(MAX_HISTORY).fill(15);
const historyLoco = new Array(MAX_HISTORY).fill(0);

let latestTelemetry = null;
let latestSensing = null;
let latestGrid = null;
let radarSweepAngle = 0;
let audioContext = null;
let lastAudioBeep = 0;

// Setup high-DPI canvases
function resizeCanvases() {
  const dpr = window.devicePixelRatio || 1;
  [radarCanvas, timelineCanvas].forEach(c => {
    if (!c) return;
    const rect = c.getBoundingClientRect();
    if (rect.width > 0 && rect.height > 0) {
      c.width = rect.width * dpr;
      c.height = rect.height * dpr;
      const ctx = c.getContext('2d');
      ctx.setTransform(1, 0, 0, 1, 0, 0); // Reset transform before scaling
      ctx.scale(dpr, dpr);
    }
  });
  if (scene3D) scene3D.onResize();
}
window.addEventListener('resize', resizeCanvases);

// Web Audio synthesizer for intrusion alert
function playChime(freq = 660) {
  const chk = document.getElementById('chkAudio');
  if (!chk || !chk.checked) return;
  const now = Date.now();
  if (now - lastAudioBeep < 800) return; // Debounce
  lastAudioBeep = now;

  try {
    if (!audioContext) {
      audioContext = new (window.AudioContext || window.webkitAudioContext)();
    }
    const osc = audioContext.createOscillator();
    const gain = audioContext.createGain();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(freq, audioContext.currentTime);
    osc.frequency.exponentialRampToValueAtTime(freq * 1.5, audioContext.currentTime + 0.12);
    gain.gain.setValueAtTime(0.1, audioContext.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, audioContext.currentTime + 0.18);
    osc.connect(gain);
    gain.connect(audioContext.destination);
    osc.start();
    osc.stop(audioContext.currentTime + 0.2);
  } catch (e) {
    console.warn("Audio chime error:", e);
  }
}

// Connect to Real-Time Telemetry WebSocket
let socket = null;
function initWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws`;
  socket = new WebSocket(wsUrl);

  socket.onopen = () => {
    const ind = document.getElementById('live-indicator');
    ind.classList.add('live');
    ind.innerHTML = '<span class="dot"></span> LIVE // 20 HZ';
  };

  socket.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.telemetry) latestTelemetry = data.telemetry;
      if (data.sensing) {
        latestSensing = data.sensing;
        updateUI(data.sensing, data.telemetry, data.router_gateway);
        
        // Feed into 3D Volumetric Scene
        if (scene3D) {
          scene3D.updateData(data.sensing, data.telemetry);
        }

        // Push to oscilloscope history
        historyPerturb.shift();
        historyPerturb.push(data.sensing.perturbation_index);
        
        historyRtt.shift();
        historyRtt.push(data.sensing.raw_rtt);

        historyLoco.shift();
        historyLoco.push(data.sensing.locomotion_energy || 0);

        if (data.sensing.perturbation_index > 35.0) {
          playChime(780);
        }
      }
      if (data.rf_field) latestGrid = data.rf_field;
    } catch (err) {
      console.error("Payload error:", err);
    }
  };

  socket.onclose = () => {
    const ind = document.getElementById('live-indicator');
    ind.classList.remove('live');
    ind.innerHTML = '<span class="dot"></span> RECONNECTING...';
    setTimeout(initWebSocket, 2000);
  };
}

// Update DOM Telemetry Elements
function updateUI(sensing, telem, gateway) {
  if (telem) {
    document.getElementById('net-ssid').textContent = telem.ssid || 'CONNECTED';
    document.getElementById('metricQuality').textContent = `${telem.signal_quality}%`;
    document.getElementById('metricRssi').textContent = `${telem.rssi_dbm} dBm`;
    document.getElementById('metricRx').textContent = `${telem.rx_rate_mbps} Mbps`;
    document.getElementById('metricTx').textContent = `Tx: ${telem.tx_rate_mbps} Mbps`;
  }
  if (gateway) {
    document.getElementById('net-gw').textContent = gateway;
  }

  if (sensing) {
    const score = sensing.perturbation_index;
    document.getElementById('perturbScore').textContent = `${score}%`;
    const bar = document.getElementById('perturbBar');
    bar.style.width = `${Math.min(100, score)}%`;

    document.getElementById('metricRtt').textContent = `${sensing.raw_rtt} ms`;
    document.getElementById('metricJitter').textContent = `Jitter: ±${sensing.rtt_jitter_ms} ms (Disp: ${sensing.dispersion_ms || 0}ms)`;
    
    // Show locomotion & breathing energy
    const loco = sensing.locomotion_energy !== undefined ? sensing.locomotion_energy : 0;
    const breath = sensing.breathing_energy !== undefined ? sensing.breathing_energy : 0;
    document.getElementById('metricVar').textContent = `L:${loco} B:${breath}`;

    // State banner update
    const banner = document.getElementById('stateBanner');
    const title = document.getElementById('stateTitle');
    const sub = document.getElementById('stateSub');
    title.textContent = sensing.motion_state;
    title.style.color = sensing.state_color;

    if (score < 10.0) {
      banner.style.borderColor = 'rgba(0, 255, 136, 0.4)';
      banner.style.background = 'rgba(0, 255, 136, 0.06)';
      sub.textContent = 'Room ambient reflections steady. No spatial Doppler shift.';
    } else if (score < 28.0) {
      banner.style.borderColor = 'rgba(255, 190, 11, 0.4)';
      banner.style.background = 'rgba(255, 190, 11, 0.08)';
      sub.textContent = `Micro-motion detected (Breathing Energy: ${breath}). Ambient noise rejected.`;
    } else {
      banner.style.borderColor = 'rgba(255, 0, 85, 0.5)';
      banner.style.background = 'rgba(255, 0, 85, 0.12)';
      sub.textContent = `ACTIVE INTRUSION: Locomotion Energy: ${loco} | Multipath phase disrupted.`;
    }
  }
}

// 2D Spatial RF Radar Canvas Loop (active in 2D mode)
function renderRadar() {
  if (currentViewMode === '2D') {
    const rect = radarCanvas.getBoundingClientRect();
    const w = rect.width;
    const h = rect.height;

    radarCtx.clearRect(0, 0, w, h);

    // 1. Draw Background Grid & Range Rings
    radarCtx.strokeStyle = 'rgba(0, 240, 255, 0.08)';
    radarCtx.lineWidth = 1;
    const cx = w / 2;
    const cy = h / 2;

    for (let r = 40; r < Math.max(w, h); r += 50) {
      radarCtx.beginPath();
      radarCtx.arc(cx, cy, r, 0, Math.PI * 2);
      radarCtx.stroke();
    }

    radarCtx.beginPath();
    radarCtx.moveTo(0, cy); radarCtx.lineTo(w, cy);
    radarCtx.moveTo(cx, 0); radarCtx.lineTo(cx, h);
    radarCtx.stroke();

    // 2. Draw 2D Synthetic RF Fresnel Heatmap
    if (latestGrid && latestGrid.length > 0) {
      const rows = latestGrid.length;
      const cols = latestGrid[0].length;
      const cellW = w / cols;
      const cellH = h / rows;

      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          const val = latestGrid[r][c];
          if (val > 0.15) {
            radarCtx.fillStyle = getHeatmapColor(val, latestSensing ? latestSensing.perturbation_index : 0);
            radarCtx.fillRect(c * cellW, r * cellH, cellW + 1, cellH + 1);
          }
        }
      }
    }

    // 3. Node Positions: Router (TX) and Laptop (RX)
    const txX = w * 0.18;
    const txY = cy;
    const rxX = w * 0.82;
    const rxY = cy;

    const perturb = latestSensing ? latestSensing.perturbation_index : 0;
    radarCtx.beginPath();
    radarCtx.moveTo(txX, txY);

    const steps = 30;
    for (let i = 1; i < steps; i++) {
      const t = i / steps;
      const curX = txX + (rxX - txX) * t;
      const noise = perturb > 15 
        ? Math.sin(t * 20 + Date.now() * 0.015) * (perturb * 0.45) 
        : Math.sin(t * 10 + Date.now() * 0.005) * 2;
      radarCtx.lineTo(curX, cy + noise);
    }
    radarCtx.lineTo(rxX, rxY);

    radarCtx.strokeStyle = perturb > 28 ? 'rgba(255, 0, 85, 0.8)' : 'rgba(0, 240, 255, 0.6)';
    radarCtx.lineWidth = perturb > 28 ? 3 : 1.5;
    radarCtx.shadowColor = perturb > 28 ? '#ff0055' : '#00f0ff';
    radarCtx.shadowBlur = perturb > 28 ? 15 : 6;
    radarCtx.stroke();
    radarCtx.shadowBlur = 0;

    // 4. Draw TX / RX Icons
    const now = Date.now() * 0.003;
    drawTransmitterNode(txX, txY, '#ff0055', 'TX: ROUTER (192.168.1.1)', now);
    drawReceiverNode(rxX, rxY, '#00f0ff', 'RX: LAPTOP (PROBE)', now);

    // 5. Draw Target Scattering Ghost if Motion is Detected
    if (perturb > 22.0) {
      const ghostX = txX + (rxX - txX) * 0.48 + Math.sin(Date.now() * 0.005) * 25;
      const ghostY = cy + Math.cos(Date.now() * 0.004) * 35;
      drawTargetEcho(ghostX, ghostY, perturb);
    }

    // 6. Tactical Radar Sweep Line
    radarSweepAngle += 0.025;
    const sweepLen = Math.max(w, h);
    radarCtx.save();
    radarCtx.translate(cx, cy);
    radarCtx.rotate(radarSweepAngle);
    
    const sweepGrad = radarCtx.createLinearGradient(0, 0, sweepLen, 0);
    sweepGrad.addColorStop(0, 'rgba(0, 240, 255, 0.3)');
    sweepGrad.addColorStop(1, 'transparent');
    radarCtx.fillStyle = sweepGrad;
    radarCtx.beginPath();
    radarCtx.moveTo(0, 0);
    radarCtx.arc(0, 0, sweepLen, -0.25, 0);
    radarCtx.closePath();
    radarCtx.fill();
    radarCtx.restore();
  }

  requestAnimationFrame(renderRadar);
}

function getHeatmapColor(val, perturb) {
  if (perturb > 28) {
    const alpha = (val * 0.55).toFixed(2);
    return `rgba(255, 0, 120, ${alpha})`;
  } else {
    const alpha = (val * 0.4).toFixed(2);
    return `rgba(0, 240, 255, ${alpha})`;
  }
}

function drawTransmitterNode(x, y, color, label, t) {
  radarCtx.save();
  for (let i = 0; i < 3; i++) {
    const r = ((t * 25 + i * 20) % 60);
    const alpha = Math.max(0, 1 - r / 60);
    radarCtx.strokeStyle = color;
    radarCtx.globalAlpha = alpha * 0.5;
    radarCtx.beginPath();
    radarCtx.arc(x, y, r, 0, Math.PI * 2);
    radarCtx.stroke();
  }
  radarCtx.globalAlpha = 1.0;
  radarCtx.fillStyle = color;
  radarCtx.shadowColor = color;
  radarCtx.shadowBlur = 10;
  radarCtx.beginPath();
  radarCtx.arc(x, y, 7, 0, Math.PI * 2);
  radarCtx.fill();
  radarCtx.shadowBlur = 0;
  radarCtx.fillStyle = '#cbd5e1';
  radarCtx.font = '10px "JetBrains Mono", monospace';
  radarCtx.fillText(label, x - 50, y + 25);
  radarCtx.restore();
}

function drawReceiverNode(x, y, color, label, t) {
  radarCtx.save();
  const r = 20 - ((t * 20) % 20);
  radarCtx.strokeStyle = color;
  radarCtx.globalAlpha = 0.6;
  radarCtx.beginPath();
  radarCtx.arc(x, y, r, 0, Math.PI * 2);
  radarCtx.stroke();
  radarCtx.globalAlpha = 1.0;
  radarCtx.fillStyle = color;
  radarCtx.shadowColor = color;
  radarCtx.shadowBlur = 10;
  radarCtx.beginPath();
  radarCtx.arc(x, y, 7, 0, Math.PI * 2);
  radarCtx.fill();
  radarCtx.shadowBlur = 0;
  radarCtx.fillStyle = '#cbd5e1';
  radarCtx.font = '10px "JetBrains Mono", monospace';
  radarCtx.fillText(label, x - 40, y + 25);
  radarCtx.restore();
}

function drawTargetEcho(x, y, perturb) {
  radarCtx.save();
  const radius = 12 + (perturb * 0.2);
  radarCtx.strokeStyle = '#ffbe0b';
  radarCtx.lineWidth = 2;
  radarCtx.shadowColor = '#ffbe0b';
  radarCtx.shadowBlur = 15;
  radarCtx.beginPath();
  radarCtx.arc(x, y, radius, 0, Math.PI * 2);
  radarCtx.stroke();
  radarCtx.beginPath();
  radarCtx.moveTo(x - radius - 5, y); radarCtx.lineTo(x + radius + 5, y);
  radarCtx.moveTo(x, y - radius - 5); radarCtx.lineTo(x, y + radius + 5);
  radarCtx.stroke();
  radarCtx.fillStyle = '#ffbe0b';
  radarCtx.font = '10px "JetBrains Mono", monospace';
  radarCtx.fillText(`RF ECHO [Δ ${Math.round(perturb)}%]`, x + 15, y - 10);
  radarCtx.restore();
}

// Bottom Oscilloscope Timeline Loop
function renderTimeline() {
  const rect = timelineCanvas.getBoundingClientRect();
  const w = rect.width;
  const h = rect.height;

  timelineCtx.clearRect(0, 0, w, h);

  // Background grid lines
  timelineCtx.strokeStyle = 'rgba(255, 255, 255, 0.04)';
  timelineCtx.lineWidth = 1;
  for (let y = 20; y < h; y += 30) {
    timelineCtx.beginPath();
    timelineCtx.moveTo(0, y);
    timelineCtx.lineTo(w, y);
    timelineCtx.stroke();
  }

  const step = w / (MAX_HISTORY - 1);

  // 1. Draw Perturbation Fill Envelope (Cyan)
  timelineCtx.beginPath();
  timelineCtx.moveTo(0, h);
  for (let i = 0; i < MAX_HISTORY; i++) {
    const val = historyPerturb[i];
    const y = h - (val / 100.0) * (h - 15);
    timelineCtx.lineTo(i * step, y);
  }
  timelineCtx.lineTo(w, h);
  timelineCtx.closePath();

  const fillGrad = timelineCtx.createLinearGradient(0, 0, 0, h);
  fillGrad.addColorStop(0, 'rgba(0, 240, 255, 0.35)');
  fillGrad.addColorStop(1, 'rgba(0, 240, 255, 0.0)');
  timelineCtx.fillStyle = fillGrad;
  timelineCtx.fill();

  // Perturbation Outline
  timelineCtx.beginPath();
  for (let i = 0; i < MAX_HISTORY; i++) {
    const val = historyPerturb[i];
    const y = h - (val / 100.0) * (h - 15);
    if (i === 0) timelineCtx.moveTo(0, y);
    else timelineCtx.lineTo(i * step, y);
  }
  timelineCtx.strokeStyle = '#00f0ff';
  timelineCtx.lineWidth = 2;
  timelineCtx.stroke();

  // 2. Draw RTT Latency Jitter Line (Amber)
  timelineCtx.beginPath();
  const maxRtt = 100.0;
  for (let i = 0; i < MAX_HISTORY; i++) {
    const rtt = Math.min(maxRtt, historyRtt[i]);
    const y = h - (rtt / maxRtt) * (h - 20);
    if (i === 0) timelineCtx.moveTo(0, y);
    else timelineCtx.lineTo(i * step, y);
  }
  timelineCtx.strokeStyle = '#ffbe0b';
  timelineCtx.lineWidth = 1.5;
  timelineCtx.stroke();

  requestAnimationFrame(renderTimeline);
}

// View Mode Switching (3D Holographic vs 2D Tactical)
function setViewMode(mode) {
  currentViewMode = mode;
  const btn3D = document.getElementById('btnView3D');
  const btn2D = document.getElementById('btnView2D');
  const v3D = document.getElementById('viewport3D');
  const c2D = document.getElementById('radarCanvas');
  const cross2D = document.getElementById('crosshairs2D');
  const range2D = document.getElementById('rangeMarkers2D');
  const camPresets = document.getElementById('camPresets');
  const orbitHint = document.getElementById('orbitHint');

  if (mode === '3D') {
    btn3D.classList.add('active');
    btn2D.classList.remove('active');
    v3D.style.display = 'block';
    c2D.style.display = 'none';
    if (cross2D) cross2D.style.display = 'none';
    if (range2D) range2D.style.display = 'none';
    if (camPresets) camPresets.style.display = 'flex';
    if (orbitHint) orbitHint.style.display = 'block';
    if (scene3D) scene3D.onResize();
  } else {
    btn2D.classList.add('active');
    btn3D.classList.remove('active');
    v3D.style.display = 'none';
    c2D.style.display = 'block';
    if (cross2D) cross2D.style.display = 'block';
    if (range2D) range2D.style.display = 'flex';
    if (camPresets) camPresets.style.display = 'none';
    if (orbitHint) orbitHint.style.display = 'none';
    resizeCanvases();
  }
}

// User Action Handlers
document.getElementById('btnView3D').addEventListener('click', () => setViewMode('3D'));
document.getElementById('btnView2D').addEventListener('click', () => setViewMode('2D'));

// Camera Presets
document.querySelectorAll('.cam-btn').forEach(btn => {
  btn.addEventListener('click', (e) => {
    document.querySelectorAll('.cam-btn').forEach(b => b.classList.remove('active'));
    e.target.classList.add('active');
    const preset = e.target.getAttribute('data-preset');
    if (scene3D) scene3D.setCameraPreset(preset);
  });
});

document.getElementById('btnCalibrate').addEventListener('click', () => {
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ action: 'calibrate' }));
    const banner = document.getElementById('stateBanner');
    const title = document.getElementById('stateTitle');
    const sub = document.getElementById('stateSub');
    title.textContent = 'CALIBRATING BASELINE...';
    title.style.color = '#00f0ff';
    sub.textContent = 'Stand still or step out for 3 seconds while baseline settles...';
  }
});

const sensSlider = document.getElementById('sensitivitySlider');
sensSlider.addEventListener('input', (e) => {
  const val = parseFloat(e.target.value);
  document.getElementById('sensVal').textContent = `${val.toFixed(1)}x`;
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ action: 'set_sensitivity', value: val }));
  }
});

// Initialization
window.addEventListener('DOMContentLoaded', () => {
  const v3DContainer = document.getElementById('viewport3D');
  if (window.RFScene3D && v3DContainer) {
    try {
      scene3D = new window.RFScene3D(v3DContainer);
    } catch (e) {
      console.warn("Could not start 3D WebGL scene, falling back to 2D tactical radar:", e);
      setViewMode('2D');
    }
  } else {
    setViewMode('2D');
  }

  resizeCanvases();
  initWebSocket();
  requestAnimationFrame(renderRadar);
  requestAnimationFrame(renderTimeline);
});
