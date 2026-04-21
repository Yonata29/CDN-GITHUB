import cv2
import numpy as np
import threading
import time
import base64
from flask import Flask, Response, jsonify, request
from flask_socketio import SocketIO
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'vehicle-counter-secret-2024'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

streams = {}
stream_lock = threading.Lock()

# ══════════════════════════════════════════════════════════════════
#  HTML  (embedded — tidak perlu folder templates)
# ══════════════════════════════════════════════════════════════════
HTML = r"""<!DOCTYPE html>
<html lang="id">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>TrafficEye — Penghitung Kendaraan</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@400;600;800&display=swap" rel="stylesheet">
  <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.min.js"></script>
  <style>
    :root {
      --bg:       #090b10;
      --surface:  #0e1117;
      --panel:    #141720;
      --border:   #1e2433;
      --accent:   #00e5ff;
      --car:      #00ff88;
      --truck:    #4488ff;
      --moto:     #ffcc00;
      --danger:   #ff4466;
      --text:     #c8d0e0;
      --dim:      #5a6480;
      --font-hd:  'Syne', sans-serif;
      --font-mono:'Space Mono', monospace;
    }
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--bg); color: var(--text);
      font-family: var(--font-hd); min-height: 100vh; overflow-x: hidden;
    }
    body::before {
      content: ''; position: fixed; inset: 0;
      background-image:
        repeating-linear-gradient(0deg, transparent, transparent 39px, rgba(0,229,255,.04) 40px),
        repeating-linear-gradient(90deg, transparent, transparent 39px, rgba(0,229,255,.04) 40px);
      pointer-events: none; z-index: 0;
    }
    header {
      position: relative; z-index: 10;
      display: flex; align-items: center; justify-content: space-between;
      padding: 18px 32px; border-bottom: 1px solid var(--border);
      background: rgba(9,11,16,.9); backdrop-filter: blur(12px);
    }
    .logo { display: flex; align-items: center; gap: 12px; }
    .logo-icon {
      width: 38px; height: 38px; background: var(--accent);
      clip-path: polygon(50% 0%,100% 25%,100% 75%,50% 100%,0% 75%,0% 25%);
      display: flex; align-items: center; justify-content: center; font-size: 18px;
    }
    .logo-text { font-size: 22px; font-weight: 800; letter-spacing: -0.5px; }
    .logo-text span { color: var(--accent); }
    .badge {
      font-family: var(--font-mono); font-size: 10px;
      background: rgba(0,229,255,.12); color: var(--accent);
      border: 1px solid rgba(0,229,255,.3); padding: 3px 10px;
      border-radius: 20px; letter-spacing: 2px;
    }
    main {
      position: relative; z-index: 1;
      display: grid; grid-template-columns: 1fr 340px;
      height: calc(100vh - 65px);
    }
    #stream-area {
      display: flex; flex-direction: column;
      border-right: 1px solid var(--border); overflow: hidden;
    }
    .url-form {
      padding: 16px 20px; border-bottom: 1px solid var(--border);
      background: var(--surface); display: flex; gap: 10px; align-items: center;
    }
    .url-form input {
      flex: 1; background: var(--panel); border: 1px solid var(--border);
      color: var(--text); font-family: var(--font-mono); font-size: 12px;
      padding: 10px 14px; border-radius: 6px; outline: none; transition: border-color .2s;
    }
    .url-form input:focus { border-color: var(--accent); }
    .url-form input::placeholder { color: var(--dim); }
    .btn {
      font-family: var(--font-hd); font-weight: 600; font-size: 13px;
      padding: 10px 20px; border: none; border-radius: 6px; cursor: pointer; transition: all .15s;
    }
    .btn-primary { background: var(--accent); color: #000; }
    .btn-primary:hover { filter: brightness(1.15); transform: translateY(-1px); }
    .btn-danger { background: rgba(255,68,102,.15); color: var(--danger); border: 1px solid rgba(255,68,102,.3); }
    .btn-danger:hover { background: rgba(255,68,102,.25); }
    .btn-sm { padding: 6px 12px; font-size: 11px; }
    #streams-container {
      flex: 1; overflow-y: auto; padding: 16px; display: grid; gap: 16px;
      grid-template-columns: repeat(auto-fit, minmax(460px, 1fr)); align-content: start;
    }
    #streams-container::-webkit-scrollbar { width: 4px; }
    #streams-container::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
    .stream-card {
      background: var(--surface); border: 1px solid var(--border);
      border-radius: 10px; overflow: hidden; animation: cardIn .3s ease;
    }
    @keyframes cardIn { from { opacity:0; transform: translateY(12px); } to { opacity:1; transform: none; } }
    .stream-header {
      display: flex; align-items: center; justify-content: space-between;
      padding: 10px 14px; border-bottom: 1px solid var(--border); background: var(--panel);
    }
    .stream-id { font-family: var(--font-mono); font-size: 11px; color: var(--accent); }
    .stream-status { font-size: 11px; font-weight: 600; letter-spacing: 1px; display: flex; align-items: center; gap: 5px; }
    .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--dim); }
    .dot.running { background: var(--car); box-shadow: 0 0 6px var(--car); animation: blink 1.5s infinite; }
    .dot.connecting { background: var(--moto); }
    .dot.error { background: var(--danger); }
    @keyframes blink { 50% { opacity:.4; } }
    .stream-video {
      width: 100%; aspect-ratio: 16/9; background: #000;
      display: flex; align-items: center; justify-content: center;
      position: relative; overflow: hidden;
    }
    .stream-video img { width: 100%; height: 100%; object-fit: contain; }
    .placeholder { display: flex; flex-direction: column; align-items: center; gap: 10px; color: var(--dim); font-size: 13px; }
    .placeholder .icon { font-size: 40px; }
    .fps-badge {
      position: absolute; top: 8px; right: 8px;
      font-family: var(--font-mono); font-size: 10px;
      background: rgba(0,0,0,.7); color: var(--accent); padding: 2px 8px; border-radius: 4px;
    }
    .stream-counts { display: grid; grid-template-columns: repeat(4,1fr); border-top: 1px solid var(--border); }
    .count-cell { padding: 10px 8px; text-align: center; border-right: 1px solid var(--border); }
    .count-cell:last-child { border-right: none; }
    .count-label { font-size: 10px; color: var(--dim); letter-spacing: 1px; text-transform: uppercase; }
    .count-value { font-family: var(--font-mono); font-size: 24px; font-weight: 700; margin-top: 2px; }
    .count-value.total { color: var(--accent); }
    .count-value.car   { color: var(--car); }
    .count-value.truck { color: var(--truck); }
    .count-value.moto  { color: var(--moto); }
    .stream-actions { display: flex; gap: 8px; padding: 10px 14px; border-top: 1px solid var(--border); }
    .line-slider { display: flex; align-items: center; gap: 8px; flex: 1; }
    .line-slider label { font-size: 10px; color: var(--dim); white-space: nowrap; }
    .line-slider input[type=range] { flex: 1; accent-color: var(--accent); }
    #empty-state {
      display: flex; flex-direction: column; align-items: center; justify-content: center;
      gap: 16px; color: var(--dim); grid-column: 1/-1; padding: 60px 0;
    }
    #empty-state .big-icon { font-size: 64px; opacity: .3; }
    #empty-state p { font-size: 14px; line-height: 1.6; text-align: center; max-width: 320px; }
    aside { background: var(--surface); display: flex; flex-direction: column; overflow: hidden; }
    .aside-section { padding: 18px 20px; border-bottom: 1px solid var(--border); }
    .aside-title { font-size: 10px; font-weight: 600; letter-spacing: 2px; color: var(--dim); text-transform: uppercase; margin-bottom: 14px; }
    .global-total {
      font-family: var(--font-mono); font-size: 48px; font-weight: 700;
      color: var(--accent); text-align: center;
      text-shadow: 0 0 30px rgba(0,229,255,.4); line-height: 1;
    }
    .global-sub { text-align: center; font-size: 11px; color: var(--dim); margin-top: 4px; }
    .global-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; margin-top: 14px; }
    .global-item { background: var(--panel); border: 1px solid var(--border); border-radius: 6px; padding: 8px; text-align: center; }
    .global-item .gl { font-size: 9px; color: var(--dim); letter-spacing: 1px; }
    .global-item .gv { font-family: var(--font-mono); font-size: 20px; margin-top: 2px; }
    .gv.car { color: var(--car); }
    .gv.truck { color: var(--truck); }
    .gv.moto { color: var(--moto); }
    #activity-log { flex: 1; overflow-y: auto; padding: 10px 20px; }
    #activity-log::-webkit-scrollbar { width: 3px; }
    #activity-log::-webkit-scrollbar-thumb { background: var(--border); }
    .log-entry {
      display: flex; align-items: center; gap: 10px;
      padding: 6px 0; border-bottom: 1px solid rgba(255,255,255,.04);
      font-size: 12px; animation: logIn .2s ease;
    }
    @keyframes logIn { from { opacity:0; transform: translateX(-6px); } }
    .log-time { font-family: var(--font-mono); color: var(--dim); font-size: 10px; min-width: 56px; }
    .log-badge { font-size: 10px; font-weight: 600; padding: 2px 8px; border-radius: 20px; white-space: nowrap; }
    .lb-car        { background: rgba(0,255,136,.12); color: var(--car);   border: 1px solid rgba(0,255,136,.2); }
    .lb-truck      { background: rgba(68,136,255,.12); color: var(--truck); border: 1px solid rgba(68,136,255,.2); }
    .lb-motorcycle { background: rgba(255,204,0,.12);  color: var(--moto);  border: 1px solid rgba(255,204,0,.2); }
    #mini-chart { width: 100%; height: 60px; }
    #toast {
      position: fixed; bottom: 20px; right: 20px; z-index: 999;
      background: var(--danger); color: #fff;
      padding: 10px 18px; border-radius: 8px; font-size: 13px; font-weight: 600;
      transform: translateY(60px); opacity: 0; transition: all .3s;
    }
    #toast.show { transform: none; opacity: 1; }
    #clock { font-family: var(--font-mono); font-size: 13px; color: var(--dim); }
  </style>
</head>
<body>
<header>
  <div class="logo">
    <div class="logo-icon">&#128247;</div>
    <div><div class="logo-text">Traffic<span>Eye</span></div></div>
  </div>
  <div class="badge">SISTEM PEMANTAU LALU LINTAS</div>
  <div id="clock">--:--:--</div>
</header>

<main>
  <section id="stream-area">
    <div class="url-form">
      <input id="url-input" type="text"
        placeholder="Masukkan URL CCTV (rtsp://, http://, atau path file video)..."/>
      <button class="btn btn-primary" onclick="addStream()">+ Tambah Stream</button>
    </div>
    <div id="streams-container">
      <div id="empty-state">
        <div class="big-icon">&#127909;</div>
        <strong>Belum ada stream aktif</strong>
        <p>Masukkan URL CCTV untuk memulai penghitungan kendaraan secara real-time.</p>
        <p style="font-size:11px;color:#3a4060;">Contoh: rtsp://camera.example.com/stream1<br>atau /path/ke/video.mp4 (untuk testing)</p>
      </div>
    </div>
  </section>

  <aside>
    <div class="aside-section">
      <div class="aside-title">&#128202; Total Global</div>
      <div class="global-total" id="g-total">0</div>
      <div class="global-sub">kendaraan terdeteksi (semua stream)</div>
      <div class="global-grid">
        <div class="global-item"><div class="gl">MOBIL</div><div class="gv car" id="g-car">0</div></div>
        <div class="global-item"><div class="gl">TRUK</div><div class="gv truck" id="g-truck">0</div></div>
        <div class="global-item"><div class="gl">MOTOR</div><div class="gv moto" id="g-moto">0</div></div>
      </div>
    </div>
    <div class="aside-section">
      <div class="aside-title">&#128200; Grafik Aktivitas</div>
      <canvas id="mini-chart"></canvas>
    </div>
    <div class="aside-section" style="border-bottom:none;flex:0 0 auto;">
      <div class="aside-title">&#128663; Log Kendaraan</div>
    </div>
    <div id="activity-log"></div>
  </aside>
</main>

<div id="toast"></div>

<script>
const socket = io();
const streamData = {};
const chartData  = [];

// Clock
function updateClock() {
  document.getElementById('clock').textContent = new Date().toLocaleTimeString('id-ID');
}
setInterval(updateClock, 1000);
updateClock();

// ── Socket events ──────────────────────────────────────────────
socket.on('frame_update', ({ stream_id, frame, counts, fps, history }) => {
  const img = document.getElementById('img-' + stream_id);
  if (img) img.src = 'data:image/jpeg;base64,' + frame;

  ['total','car','truck','motorcycle'].forEach(k => {
    const el = document.getElementById('cnt-' + stream_id + '-' + k);
    if (el) el.textContent = counts[k] || 0;
  });

  const fpsBadge = document.getElementById('fps-' + stream_id);
  if (fpsBadge) fpsBadge.textContent = fps + ' fps';

  const dot = document.getElementById('dot-' + stream_id);
  if (dot) dot.className = 'dot running';
  const stxt = document.getElementById('status-txt-' + stream_id);
  if (stxt) stxt.textContent = 'LIVE';

  const ph = document.getElementById('ph-' + stream_id);
  if (ph) ph.style.display = 'none';
  if (img) img.style.display = 'block';

  streamData[stream_id] = { counts, fps };
  updateGlobals();

  if (history && history.length) {
    const last = history[history.length - 1];
    appendLog(last.time, last.type, stream_id);
  }

  chartData.push(counts.total || 0);
  if (chartData.length > 20) chartData.shift();
  drawChart();
});

socket.on('stream_error', ({ stream_id, error }) => {
  const dot = document.getElementById('dot-' + stream_id);
  if (dot) dot.className = 'dot error';
  const stxt = document.getElementById('status-txt-' + stream_id);
  if (stxt) stxt.textContent = 'ERROR';
  showToast('Gagal: ' + (error || 'Stream error'));
});

// ── Add stream ─────────────────────────────────────────────────
async function addStream() {
  const input = document.getElementById('url-input');
  const url = input.value.trim();
  if (!url) { showToast('Masukkan URL stream terlebih dahulu'); return; }

  const res  = await fetch('/api/streams', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url })
  });
  const data = await res.json();
  if (data.error) { showToast(data.error); return; }

  const es = document.getElementById('empty-state');
  if (es) es.remove();
  createCard(data.id, url);
  input.value = '';
}

function createCard(sid, url) {
  const container = document.getElementById('streams-container');
  const card = document.createElement('div');
  card.className = 'stream-card';
  card.id = 'card-' + sid;
  const label = url.length > 42 ? url.slice(0, 39) + '...' : url;
  card.innerHTML =
    '<div class="stream-header">' +
      '<span class="stream-id">&#128225; ' + label + '</span>' +
      '<span class="stream-status">' +
        '<span class="dot connecting" id="dot-' + sid + '"></span>' +
        '<span id="status-txt-' + sid + '" style="color:var(--dim)">CONNECTING</span>' +
      '</span>' +
    '</div>' +
    '<div class="stream-video">' +
      '<div class="placeholder" id="ph-' + sid + '"><div class="icon">&#9203;</div><span>Menghubungkan ke stream...</span></div>' +
      '<img id="img-' + sid + '" style="display:none;" alt="stream"/>' +
      '<div class="fps-badge" id="fps-' + sid + '">-- fps</div>' +
    '</div>' +
    '<div class="stream-counts">' +
      '<div class="count-cell"><div class="count-label">Total</div><div class="count-value total" id="cnt-' + sid + '-total">0</div></div>' +
      '<div class="count-cell"><div class="count-label">&#128994; Mobil</div><div class="count-value car" id="cnt-' + sid + '-car">0</div></div>' +
      '<div class="count-cell"><div class="count-label">&#128309; Truk</div><div class="count-value truck" id="cnt-' + sid + '-truck">0</div></div>' +
      '<div class="count-cell"><div class="count-label">&#128993; Motor</div><div class="count-value moto" id="cnt-' + sid + '-motorcycle">0</div></div>' +
    '</div>' +
    '<div class="stream-actions">' +
      '<div class="line-slider"><label>&#128207; Garis hitung:</label>' +
        '<input type="range" min="20" max="80" value="55" oninput="setLine(\'' + sid + '\',this.value/100)">' +
      '</div>' +
      '<button class="btn btn-sm" onclick="resetCounts(\'' + sid + '\')" style="background:rgba(0,229,255,.1);color:var(--accent);border:1px solid rgba(0,229,255,.2)">&#8635; Reset</button>' +
      '<button class="btn btn-danger btn-sm" onclick="removeStream(\'' + sid + '\')">&#10005;</button>' +
    '</div>';
  container.appendChild(card);
}

// ── Actions ────────────────────────────────────────────────────
async function removeStream(sid) {
  await fetch('/api/streams/' + sid, { method: 'DELETE' });
  const card = document.getElementById('card-' + sid);
  if (card) card.remove();
  delete streamData[sid];
  updateGlobals();
}

async function resetCounts(sid) {
  await fetch('/api/streams/' + sid + '/reset', { method: 'POST' });
  ['total','car','truck','motorcycle'].forEach(k => {
    const el = document.getElementById('cnt-' + sid + '-' + k);
    if (el) el.textContent = '0';
  });
  if (streamData[sid]) streamData[sid].counts = { total:0, car:0, truck:0, motorcycle:0 };
  updateGlobals();
}

async function setLine(sid, ratio) {
  await fetch('/api/streams/' + sid + '/line', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ratio })
  });
}

// ── Globals ────────────────────────────────────────────────────
function updateGlobals() {
  let total=0, car=0, truck=0, moto=0;
  Object.values(streamData).forEach(d => {
    if (!d.counts) return;
    total += d.counts.total        || 0;
    car   += d.counts.car          || 0;
    truck += d.counts.truck        || 0;
    moto  += d.counts.motorcycle   || 0;
  });
  document.getElementById('g-total').textContent = total;
  document.getElementById('g-car').textContent   = car;
  document.getElementById('g-truck').textContent = truck;
  document.getElementById('g-moto').textContent  = moto;
}

// ── Log ────────────────────────────────────────────────────────
const logEl = document.getElementById('activity-log');
let lastLogKey = '';
function appendLog(t, type, sid) {
  const key = t + '-' + type + '-' + sid;
  if (key === lastLogKey) return;
  lastLogKey = key;
  const labels = { car:'Mobil', truck:'Truk', motorcycle:'Motor' };
  const entry = document.createElement('div');
  entry.className = 'log-entry';
  entry.innerHTML =
    '<span class="log-time">' + t + '</span>' +
    '<span class="log-badge lb-' + type + '">' + (labels[type] || type) + '</span>' +
    '<span style="margin-left:auto;font-size:9px;color:var(--dim)">melintas</span>';
  logEl.prepend(entry);
  while (logEl.children.length > 60) logEl.lastChild.remove();
}

// ── Chart ──────────────────────────────────────────────────────
const chartCanvas = document.getElementById('mini-chart');
const ctx = chartCanvas.getContext('2d');
function drawChart() {
  const W = chartCanvas.offsetWidth || 280;
  const H = 60;
  chartCanvas.width = W; chartCanvas.height = H;
  ctx.clearRect(0, 0, W, H);
  if (chartData.length < 2) return;
  const max  = Math.max(...chartData, 1);
  const step = W / (chartData.length - 1);
  const grad = ctx.createLinearGradient(0, 0, 0, H);
  grad.addColorStop(0, 'rgba(0,229,255,.3)');
  grad.addColorStop(1, 'rgba(0,229,255,0)');
  ctx.beginPath();
  chartData.forEach((v, i) => {
    const x = i * step;
    const y = H - (v / max) * (H - 6) - 3;
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.strokeStyle = '#00e5ff'; ctx.lineWidth = 2; ctx.stroke();
  ctx.lineTo((chartData.length-1)*step, H); ctx.lineTo(0, H);
  ctx.closePath(); ctx.fillStyle = grad; ctx.fill();
}

// ── Toast ──────────────────────────────────────────────────────
function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg; t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 3500);
}

document.getElementById('url-input').addEventListener('keydown', e => {
  if (e.key === 'Enter') addStream();
});
</script>
</body>
</html>"""


# ══════════════════════════════════════════════════════════════════
#  Vehicle Detector
# ══════════════════════════════════════════════════════════════════
class VehicleDetector:
    def __init__(self):
        self.bg_sub = cv2.createBackgroundSubtractorMOG2(
            history=100, varThreshold=40, detectShadows=True)
        self.min_area = 1200
        self.kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

    def classify(self, area):
        if area < 600:
            return 'motorcycle', (255, 200, 0)
        elif area < 5000:
            return 'car', (0, 255, 100)
        else:
            return 'truck', (0, 100, 255)

    def detect(self, frame):
        blur = cv2.GaussianBlur(frame, (5, 5), 0)
        mask = self.bg_sub.apply(blur)
        _, mask = cv2.threshold(mask, 200, 255, cv2.THRESH_BINARY)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  self.kernel, iterations=2)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, self.kernel, iterations=3)
        mask = cv2.dilate(mask, self.kernel, iterations=2)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        detections = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < self.min_area:
                continue
            x, y, w, h = cv2.boundingRect(cnt)
            ar = w / max(h, 1)
            if ar > 5 or ar < 0.2:
                continue
            vtype, color = self.classify(area)
            detections.append({
                'bbox': (x, y, w, h), 'area': area,
                'type': vtype, 'color': color,
                'center': (x + w // 2, y + h // 2)
            })
        return detections


# ══════════════════════════════════════════════════════════════════
#  Centroid Tracker
# ══════════════════════════════════════════════════════════════════
class VehicleTracker:
    def __init__(self):
        self.tracks = {}
        self.next_id = 1
        self.max_gone = 10
        self.max_dist = 100

    def update(self, detections):
        if not detections:
            for tid in list(self.tracks):
                self.tracks[tid]['disappeared'] += 1
                if self.tracks[tid]['disappeared'] > self.max_gone:
                    del self.tracks[tid]
            return self.tracks

        centers = [d['center'] for d in detections]

        if not self.tracks:
            for i, c in enumerate(centers):
                self._register(c, detections[i])
            return self.tracks

        ids   = list(self.tracks)
        t_ctr = [self.tracks[i]['center'] for i in ids]
        used_d, used_t = set(), set()

        for i, tc in enumerate(t_ctr):
            best_d, best_j = float('inf'), -1
            for j, dc in enumerate(centers):
                if j in used_d:
                    continue
                dist = ((tc[0]-dc[0])**2 + (tc[1]-dc[1])**2) ** 0.5
                if dist < best_d:
                    best_d, best_j = dist, j
            if best_j >= 0 and best_d < self.max_dist:
                tid = ids[i]
                self.tracks[tid]['center'] = centers[best_j]
                self.tracks[tid]['disappeared'] = 0
                self.tracks[tid]['type']  = detections[best_j]['type']
                self.tracks[tid]['color'] = detections[best_j]['color']
                self.tracks[tid]['bbox']  = detections[best_j]['bbox']
                self.tracks[tid]['path'].append(centers[best_j])
                if len(self.tracks[tid]['path']) > 30:
                    self.tracks[tid]['path'].pop(0)
                used_d.add(best_j); used_t.add(i)

        for i in range(len(ids)):
            if i not in used_t:
                tid = ids[i]
                self.tracks[tid]['disappeared'] += 1
                if self.tracks[tid]['disappeared'] > self.max_gone:
                    del self.tracks[tid]

        for j in range(len(centers)):
            if j not in used_d:
                self._register(centers[j], detections[j])

        return self.tracks

    def _register(self, center, det):
        self.tracks[self.next_id] = {
            'center': center, 'disappeared': 0, 'counted': False,
            'type': det['type'], 'color': det['color'],
            'bbox': det['bbox'], 'path': [center]
        }
        self.next_id += 1


# ══════════════════════════════════════════════════════════════════
#  Stream Processor
# ══════════════════════════════════════════════════════════════════
class StreamProcessor:
    def __init__(self, stream_id, url):
        self.stream_id = stream_id
        self.url = url
        self.running = False
        self.thread = None
        self.detector = VehicleDetector()
        self.tracker  = VehicleTracker()
        self.counts = {'car': 0, 'truck': 0, 'motorcycle': 0, 'total': 0}
        self.fps = 0
        self.status = 'idle'
        self.error  = None
        self.line_ratio = 0.55
        self.history = []

    def start(self):
        self.running = True
        self.status  = 'connecting'
        self.thread  = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        self.status  = 'idle'

    def _run(self):
        try:
            cap = cv2.VideoCapture(self.url)
            if not cap.isOpened():
                self.status = 'error'
                self.error  = 'Tidak dapat membuka stream. Cek URL.'
                socketio.emit('stream_error', {'stream_id': self.stream_id, 'error': self.error})
                return

            self.status = 'running'
            prev_t = time.time()

            while self.running:
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.5)
                    cap.release()
                    cap = cv2.VideoCapture(self.url)
                    continue

                h, w = frame.shape[:2]
                line_y = int(h * self.line_ratio)

                detections = self.detector.detect(frame)
                tracks     = self.tracker.update(detections)

                for tid, trk in tracks.items():
                    if trk['disappeared'] > 0:
                        continue
                    path = trk['path']
                    if len(path) >= 2 and not trk['counted']:
                        py, cy = path[-2][1], trk['center'][1]
                        if (py < line_y <= cy) or (py > line_y >= cy):
                            trk['counted'] = True
                            vt = trk['type']
                            self.counts[vt] = self.counts.get(vt, 0) + 1
                            self.counts['total'] += 1
                            self.history.append({'time': time.strftime('%H:%M:%S'), 'type': vt})
                            if len(self.history) > 200:
                                self.history.pop(0)

                # ── Draw ──────────────────────────────────────────────────────
                vis = frame.copy()
                cv2.line(vis, (0, line_y), (w, line_y), (0, 220, 255), 2)
                cv2.putText(vis, 'COUNTING LINE', (10, line_y - 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 220, 255), 1)

                for tid, trk in tracks.items():
                    if trk['disappeared'] > 2:
                        continue
                    x, y, bw, bh = trk['bbox']
                    color = trk['color']
                    cv2.rectangle(vis, (x, y), (x+bw, y+bh), color, 2)
                    cv2.putText(vis, f"#{tid} {trk['type']}", (x, y-6),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)
                    pts = trk['path']
                    for k in range(1, len(pts)):
                        cv2.line(vis, pts[k-1], pts[k], color, 1)

                ov = vis.copy()
                cv2.rectangle(ov, (0, 0), (220, 90), (0, 0, 0), -1)
                cv2.addWeighted(ov, 0.5, vis, 0.5, 0, vis)
                cv2.putText(vis, f"Total : {self.counts['total']}", (8, 22),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 2)
                cv2.putText(vis, f"Mobil  : {self.counts['car']}", (8, 44),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,100), 1)
                cv2.putText(vis, f"Truk   : {self.counts['truck']}", (8, 62),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,100,255), 1)
                cv2.putText(vis, f"Motor  : {self.counts['motorcycle']}", (8, 80),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,200,0), 1)

                now = time.time()
                dt  = now - prev_t
                self.fps = round(1.0 / dt, 1) if dt > 0 else 0
                prev_t = now

                _, buf = cv2.imencode('.jpg', vis, [cv2.IMWRITE_JPEG_QUALITY, 65])
                b64 = base64.b64encode(buf).decode('utf-8')

                socketio.emit('frame_update', {
                    'stream_id': self.stream_id,
                    'frame': b64,
                    'counts': self.counts,
                    'fps': self.fps,
                    'history': self.history[-10:]
                })

                time.sleep(0.03)

            cap.release()

        except Exception as e:
            logger.error(f"Stream {self.stream_id} error: {e}")
            self.status = 'error'
            self.error  = str(e)
            socketio.emit('stream_error', {'stream_id': self.stream_id, 'error': str(e)})


# ══════════════════════════════════════════════════════════════════
#  Routes
# ══════════════════════════════════════════════════════════════════
@app.route('/')
def index():
    return Response(HTML, mimetype='text/html')   # ← tidak pakai render_template


@app.route('/api/streams', methods=['GET'])
def get_streams():
    with stream_lock:
        result = [{'id': sid, 'url': sp.url, 'status': sp.status,
                   'counts': sp.counts, 'fps': sp.fps, 'error': sp.error}
                  for sid, sp in streams.items()]
    return jsonify(result)


@app.route('/api/streams', methods=['POST'])
def add_stream():
    data = request.json or {}
    url  = data.get('url', '').strip()
    if not url:
        return jsonify({'error': 'URL diperlukan'}), 400
    sid = f"stream_{int(time.time()*1000)}"
    sp  = StreamProcessor(sid, url)
    with stream_lock:
        streams[sid] = sp
    sp.start()
    return jsonify({'id': sid, 'status': 'connecting'})


@app.route('/api/streams/<sid>', methods=['DELETE'])
def remove_stream(sid):
    with stream_lock:
        if sid in streams:
            streams[sid].stop()
            del streams[sid]
    return jsonify({'ok': True})


@app.route('/api/streams/<sid>/reset', methods=['POST'])
def reset_counts(sid):
    with stream_lock:
        if sid in streams:
            streams[sid].counts  = {'car': 0, 'truck': 0, 'motorcycle': 0, 'total': 0}
            streams[sid].history = []
    return jsonify({'ok': True})


@app.route('/api/streams/<sid>/line', methods=['POST'])
def set_line(sid):
    data  = request.json or {}
    ratio = float(data.get('ratio', 0.55))
    with stream_lock:
        if sid in streams:
            streams[sid].line_ratio = max(0.1, min(0.9, ratio))
            streams[sid].detector   = VehicleDetector()   # reset bg subtractor
    return jsonify({'ok': True})


if __name__ == '__main__':
    print("=" * 50)
    print("  TrafficEye — Penghitung Kendaraan CCTV")
    print("  Buka browser: http://localhost:5000")
    print("=" * 50)
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)
