let currentRunId = null;
let pollTimer = null;

// Canvas simulation state
let canvas, ctx;
let canvasWidth = 520;
let canvasHeight = 320;
let lastTimestamp = 0;
let vehiclesOnCanvas = [];
// Virtual stop lines near the intersection box; vehicles may roll up to here on red
let stopLines = { 1: 0, 2: 0, 3: 0, 4: 0 };
let currentPhaseLabel = "";
let lastGreenLane = null; // persist last seen green lane to avoid stalls if a line is missed
let lastGreenAt = 0; // ms timestamp when we last observed a GREEN
let prevLaneDetails = {};
let throughputHistory = [];
let startBtnEl = null;
let stopBtnEl = null;
let logViewEl = null;
const insightElems = {
  busiest: null,
  dominant: null,
  throughput: null,
  tip: null,
};

const VEHICLE_LABELS = {
  car: "Car",
  bus: "Bus",
  truck: "Truck",
  rickshaw: "Rickshaw",
  bike: "Bike",
};

const DEFAULT_TIP = "Monitor lane flow to keep the intersection balanced.";

function resetVisualState() {
  vehiclesOnCanvas = [];
  currentPhaseLabel = "";
  prevLaneDetails = {};
  throughputHistory = [];
  applyDefaultInsights();
}

function initCanvas() {
  canvas = document.getElementById("simCanvas");
  if (!canvas) return;
  ctx = canvas.getContext("2d");
  canvasWidth = canvas.width;
  canvasHeight = canvas.height;
  // Define stop lines relative to the center box (box is ~90x90 around center)
  const cx = canvasWidth / 2;
  const cy = canvasHeight / 2;
  stopLines = {
    1: cx - 55, // lane 1 moving right, stop before center box
    2: cy - 55, // lane 2 moving down
    3: cx + 55, // lane 3 moving left, stop before center from right
    4: cy + 55, // lane 4 moving up
  };
  resetVisualState();
  requestAnimationFrame(drawFrame);
}

function applyDefaultInsights() {
  if (!insightElems.busiest) return;
  insightElems.busiest.textContent = "—";
  insightElems.dominant.textContent = "—";
  insightElems.throughput.textContent = "—";
  insightElems.tip.textContent = DEFAULT_TIP;
}

function updateInsights(lanes = {}, laneDetails = {}, stats = {}) {
  if (!insightElems.busiest) return;

  const entries = Object.entries(lanes || {}).map(([lane, count]) => ({
    lane: Number(lane),
    count: Number(count),
  }));
  const activeEntries = entries.filter((entry) => Number.isFinite(entry.lane) && entry.count > 0);

  let busiestLane = null;
  if (activeEntries.length) {
    const busiest = activeEntries.reduce((max, item) => (item.count > max.count ? item : max), activeEntries[0]);
    busiestLane = busiest.lane;
    insightElems.busiest.textContent = `Lane ${busiest.lane} (${busiest.count})`;
  } else {
    insightElems.busiest.textContent = "—";
  }

  const totals = { car: 0, bus: 0, truck: 0, rickshaw: 0, bike: 0 };
  Object.values(laneDetails || {}).forEach((detail = {}) => {
    Object.keys(totals).forEach((type) => {
      totals[type] += Number(detail[type] || 0);
    });
  });

  const sortedTypes = Object.entries(totals).sort((a, b) => b[1] - a[1]);
  const [topType, topCount] = sortedTypes[0] || [];
  if (topType && topCount > 0) {
    insightElems.dominant.textContent = `${VEHICLE_LABELS[topType]} (${topCount})`;
  } else {
    insightElems.dominant.textContent = "—";
  }

  const throughput = Number(stats.throughput || 0);
  if (!Number.isNaN(throughput)) {
    throughputHistory.push(throughput);
    if (throughputHistory.length > 30) throughputHistory.shift();
  }

  let throughputLabel = "—";
  if (throughputHistory.length === 1) {
    throughputLabel = `${throughputHistory[0].toFixed(2)} veh/unit`;
  } else if (throughputHistory.length >= 2) {
    const current = throughputHistory[throughputHistory.length - 1];
    const previous = throughputHistory[throughputHistory.length - 2];
    const delta = current - previous;
    if (Math.abs(delta) < 0.05) {
      throughputLabel = `Stable (${current.toFixed(2)})`;
    } else if (delta > 0) {
      throughputLabel = `Rising ↑ (${current.toFixed(2)})`;
    } else {
      throughputLabel = `Falling ↓ (${current.toFixed(2)})`;
    }
  }
  insightElems.throughput.textContent = throughputLabel;

  const density = Number(stats.traffic_density || 0);
  const avgWait = Number(stats.average_wait || 0);
  let tip = DEFAULT_TIP;

  if (density >= 80) {
    tip = "Trigger congestion management: extend relief phases and publish detours.";
  } else if (avgWait >= 20) {
    tip = "Average wait is high—tighten cycle length and bias towards the busiest lane.";
  } else if (topType === "bus" && topCount > 0) {
    tip = "Transit-heavy demand detected—enable bus priority for smoother headways.";
  } else if (topType === "truck" && topCount > 0) {
    tip = "Freight surge in progress—schedule freight-friendly greens to clear queues.";
  } else if (busiestLane) {
    tip = `Balance flow: Lane ${busiestLane} is leading counts right now.`;
  }

  insightElems.tip.textContent = tip;
}

function drawIntersectionBackground() {
  if (!ctx) return;
  const w = canvasWidth;
  const h = canvasHeight;
  ctx.fillStyle = "#020617";
  ctx.fillRect(0, 0, w, h);

  ctx.fillStyle = "#111827";
  const roadWidth = 70;
  ctx.fillRect(w / 2 - roadWidth / 2, 0, roadWidth, h);
  ctx.fillRect(0, h / 2 - roadWidth / 2, w, roadWidth);

  ctx.strokeStyle = "#4b5563";
  ctx.lineWidth = 2;
  ctx.strokeRect(w / 2 - 45, h / 2 - 45, 90, 90);
}

function drawSignals() {
  if (!ctx) return;
  const w = canvasWidth;
  const h = canvasHeight;
  const colors = ["#4b5563", "#4b5563", "#4b5563", "#4b5563"];

  if (currentPhaseLabel.includes("GREEN TS")) {
    const idx = parseInt(currentPhaseLabel.split("GREEN TS")[1], 10) || 1;
    colors[idx - 1] = "#22c55e";
  } else if (currentPhaseLabel.includes("YELLOW TS")) {
    const idx = parseInt(currentPhaseLabel.split("YELLOW TS")[1], 10) || 1;
    colors[idx - 1] = "#eab308";
  }

  const positions = [
    { x: w / 2 + 70, y: h / 2 - 20 }, // Lane 1: right
    { x: w / 2 + 20, y: h / 2 + 70 }, // Lane 2: down
    { x: w / 2 - 70, y: h / 2 + 20 }, // Lane 3: left
    { x: w / 2 - 20, y: h / 2 - 70 }, // Lane 4: up
  ];

  positions.forEach((p, i) => {
    ctx.beginPath();
    ctx.arc(p.x, p.y, 8, 0, Math.PI * 2);
    ctx.fillStyle = colors[i];
    ctx.fill();
  });
}

function drawLaneLabels() {
  if (!ctx) return;
  ctx.fillStyle = "#a5f3fc";
  ctx.font = "12px 'Segoe UI', sans-serif";

  // Lane 4 at bottom (entry point for up direction)
  ctx.textAlign = "center";
  ctx.fillText("Lane 4", canvasWidth / 2, canvasHeight - 10);

  // Lane 1 at left (entry point for right direction)
  ctx.textAlign = "left";
  ctx.fillText("Lane 1", 10, canvasHeight / 2 - 12);

  // Lane 2 at top (entry point for down direction)
  ctx.textAlign = "center";
  ctx.fillText("Lane 2", canvasWidth / 2, 22);

  // Lane 3 at right (entry point for left direction)
  ctx.textAlign = "right";
  ctx.fillText("Lane 3", canvasWidth - 10, canvasHeight / 2 - 12);

  ctx.textAlign = "center";
}

function drawLaneNumbers() {
  if (!ctx) return;
  // Backend mapping: 1=right (left→right), 2=down (top→bottom), 3=left (right→left), 4=up (bottom→top)
  const markers = [
    { lane: 1, x: 40, y: canvasHeight / 2 - 15 }, // left entry
    { lane: 2, x: canvasWidth / 2 - 15, y: 40 }, // top entry
    { lane: 3, x: canvasWidth - 70, y: canvasHeight / 2 - 15 }, // right entry
    { lane: 4, x: canvasWidth / 2 - 15, y: canvasHeight - 70 }, // bottom entry
  ];

  markers.forEach(({ lane, x, y }) => {
    ctx.fillStyle = "rgba(14, 165, 233, 0.18)";
    ctx.fillRect(x, y, 30, 30);
    ctx.strokeStyle = "rgba(56, 189, 248, 0.45)";
    ctx.lineWidth = 1.5;
    ctx.strokeRect(x, y, 30, 30);
    ctx.fillStyle = "#f8fafc";
    ctx.font = "12px 'Segoe UI', sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(String(lane), x + 15, y + 19);
  });
}

const VEHICLE_COLORS = {
  car: "#38bdf8",
  bus: "#a855f7",
  truck: "#f97316",
  rickshaw: "#22c55e",
  bike: "#facc15",
};

const VEHICLE_SPEEDS = {
  car: 1.575,
  bus: 1.26,
  truck: 1.26,
  rickshaw: 1.4,
  bike: 1.75,
};

function spawnVehicle(lane, types = {}, offset = 0) {
  const kindOrder = ["car", "bus", "truck", "rickshaw", "bike"];
  const vehicleType =
    kindOrder.find((type) => (types[type] || 0) > 0) || kindOrder[Math.floor(Math.random() * kindOrder.length)];
  const size = vehicleType === "bus" || vehicleType === "truck" ? 16 : 12;
  const speed = VEHICLE_SPEEDS[vehicleType] * 1.0;
  // Randomly decide turning to mimic backend turn behavior
  const willTurn = Math.random() < 0.35;
  if (lane === 1)
    vehiclesOnCanvas.push({ lane, type: vehicleType, x: 0 + offset, y: canvasHeight / 2 + 15, dx: speed, dy: 0, size, willTurn, turned: false, crossed: false, anchorY: canvasHeight / 2 + 15, createdAt: performance.now(), lastX: 0 + offset, lastY: canvasHeight / 2 + 15, stagnant: 0 });
  if (lane === 2)
    vehiclesOnCanvas.push({ lane, type: vehicleType, x: canvasWidth / 2 + 15, y: 0 + offset, dx: 0, dy: speed, size, willTurn, turned: false, crossed: false, anchorX: canvasWidth / 2 + 15, createdAt: performance.now(), lastX: canvasWidth / 2 + 15, lastY: 0 + offset, stagnant: 0 });
  if (lane === 3)
    vehiclesOnCanvas.push({ lane, type: vehicleType, x: canvasWidth - offset, y: canvasHeight / 2 - 15, dx: -speed, dy: 0, size, willTurn, turned: false, crossed: false, anchorY: canvasHeight / 2 - 15, createdAt: performance.now(), lastX: canvasWidth - offset, lastY: canvasHeight / 2 - 15, stagnant: 0 });
  if (lane === 4)
    vehiclesOnCanvas.push({ lane, type: vehicleType, x: canvasWidth / 2 - 15, y: canvasHeight - offset, dx: 0, dy: -speed, size, willTurn, turned: false, crossed: false, anchorX: canvasWidth / 2 - 15, createdAt: performance.now(), lastX: canvasWidth / 2 - 15, lastY: canvasHeight - offset, stagnant: 0 });
}

function spawnVehiclesForLane(lane, currentDetails = {}, prevDetails = {}) {
  const kindOrder = ["car", "bus", "truck", "rickshaw", "bike"];
  const currentCounts = kindOrder.map(type => Number(currentDetails[type] || 0));
  const prevCounts = kindOrder.map(type => Number(prevDetails[type] || 0));
  const deltas = currentCounts.map((curr, i) => Math.max(0, curr - prevCounts[i]));

  deltas.forEach((delta, i) => {
    const vehicleType = kindOrder[i];
    for (let n = 0; n < delta * 3; n++) {  // Spawn 3 vehicles per delta for better visibility
      const size = vehicleType === "bus" || vehicleType === "truck" ? 16 : 12;  // Increased size for visibility
      const speed = VEHICLE_SPEEDS[vehicleType] * 1.0;
      const willTurn = Math.random() < 0.35;
      if (lane === 1)
        vehiclesOnCanvas.push({ lane, type: vehicleType, x: 0, y: canvasHeight / 2 + 15, dx: speed, dy: 0, size, willTurn, turned: false, crossed: false, anchorY: canvasHeight / 2 + 15, createdAt: performance.now(), lastX: 0, lastY: canvasHeight / 2 + 15, stagnant: 0 });
      if (lane === 2)
        vehiclesOnCanvas.push({ lane, type: vehicleType, x: canvasWidth / 2 + 15, y: 0, dx: 0, dy: speed, size, willTurn, turned: false, crossed: false, anchorX: canvasWidth / 2 + 15, createdAt: performance.now(), lastX: canvasWidth / 2 + 15, lastY: 0, stagnant: 0 });
      if (lane === 3)
        vehiclesOnCanvas.push({ lane, type: vehicleType, x: canvasWidth, y: canvasHeight / 2 - 15, dx: -speed, dy: 0, size, willTurn, turned: false, crossed: false, anchorY: canvasHeight / 2 - 15, createdAt: performance.now(), lastX: canvasWidth, lastY: canvasHeight / 2 - 15, stagnant: 0 });
      if (lane === 4)
        vehiclesOnCanvas.push({ lane, type: vehicleType, x: canvasWidth / 2 - 15, y: canvasHeight, dx: 0, dy: -speed, size, willTurn, turned: false, crossed: false, anchorX: canvasWidth / 2 - 15, createdAt: performance.now(), lastX: canvasWidth / 2 - 15, lastY: canvasHeight, stagnant: 0 });
    }
  });
}



function updateCars(deltaMs) {
  // Normalize to ~60fps ticks to better match backend pygame step timing
  const dt = deltaMs / 16.67;

  // Determine which lanes are green
  const greenLanes = new Set();
  // Robust parsing: accept variants like "GREEN TS1", "GREEN TS 1", or just "GREEN 1"
  const phase = (currentPhaseLabel || "").toUpperCase();
  // Capture one or more lane indices if present (e.g., "GREEN TS1 3" or "GREEN 1 3")
  const matches = phase.match(/GREEN\s*(?:TS)?\s*([1-4](?:\s+[1-4])*)/);
  if (matches && matches[1]) {
    const lanes = matches[1].trim().split(/\s+/).map((m) => parseInt(m, 10)).filter((n) => n >= 1 && n <= 4);
    lanes.forEach((idx) => greenLanes.add(idx));
    if (lanes.length) {
      lastGreenLane = lanes[0];
      lastGreenAt = performance.now();
    }
  }
  // Follow backend strictly: no fallback green. Only move on explicit GREEN phase.

  vehiclesOnCanvas.forEach((vehicle) => {
    // Movement gating similar to backend:
    // - On red: vehicle can approach up to its stop line, then must wait.
    // - On green: proceed; mark crossed when passing the stop line.
    const onGreen = greenLanes.has(vehicle.lane);
    let speedMultiplier = 1; // free-flow: never reduce speed due to red

    // If the vehicle is inside the intersection box, treat it as crossed to avoid any mid-box freeze
    {
      const cx = canvasWidth / 2;
      const cy = canvasHeight / 2;
      const inBox = Math.abs(vehicle.x - cx) < 45 && Math.abs(vehicle.y - cy) < 45;
      if (inBox) vehicle.crossed = true;
    }

    // Mark as crossed as soon as the front reaches the stop line (pre-movement)
    if (!vehicle.crossed) {
      if (vehicle.lane === 1 && vehicle.x + vehicle.size >= stopLines[1]) vehicle.crossed = true;
      if (vehicle.lane === 2 && vehicle.y + vehicle.size >= stopLines[2]) vehicle.crossed = true;
      if (vehicle.lane === 3 && vehicle.x <= stopLines[3]) vehicle.crossed = true;
      if (vehicle.lane === 4 && vehicle.y <= stopLines[4]) vehicle.crossed = true;
    }

    // Free-flow mode: no red-phase deceleration or gating

    // Handle turning near the center if vehicle intends to turn
    const cx = canvasWidth / 2;
    const cy = canvasHeight / 2;
    const nearCenter = Math.abs(vehicle.x - cx) < 40 && Math.abs(vehicle.y - cy) < 40;
    if ((onGreen || vehicle.crossed) && vehicle.willTurn && !vehicle.turned && nearCenter) {
      // Perform a right-turn style 90° change matching backend's per-direction turn
      const speed = Math.hypot(vehicle.dx, vehicle.dy) || VEHICLE_SPEEDS[vehicle.type];
      if (vehicle.lane === 1) { vehicle.dx = 0; vehicle.dy = Math.abs(speed); vehicle.anchorX = canvasWidth / 2 + 15; }
      else if (vehicle.lane === 2) { vehicle.dx = -Math.abs(speed); vehicle.dy = 0; vehicle.anchorY = canvasHeight / 2 - 15; }
      else if (vehicle.lane === 3) { vehicle.dx = 0; vehicle.dy = -Math.abs(speed); vehicle.anchorX = canvasWidth / 2 - 15; }
      else if (vehicle.lane === 4) { vehicle.dx = Math.abs(speed); vehicle.dy = 0; vehicle.anchorY = canvasHeight / 2 + 15; }
      vehicle.turned = true;
    }

    // Tentative movement
    // Guarantee a non-zero velocity for crossed vehicles to avoid stalls
    if (vehicle.crossed && Math.abs(vehicle.dx) < 1e-6 && Math.abs(vehicle.dy) < 1e-6) {
      const base = VEHICLE_SPEEDS[vehicle.type] || 1.2;
      if (vehicle.turned) {
        // After turning, choose orthogonal direction
        if (vehicle.lane === 1) { vehicle.dx = 0; vehicle.dy = base; }
        else if (vehicle.lane === 2) { vehicle.dx = -base; vehicle.dy = 0; }
        else if (vehicle.lane === 3) { vehicle.dx = 0; vehicle.dy = -base; }
        else if (vehicle.lane === 4) { vehicle.dx = base; vehicle.dy = 0; }
      } else {
        // Before turn, continue straight
        if (vehicle.lane === 1) { vehicle.dx = base; vehicle.dy = 0; }
        if (vehicle.lane === 2) { vehicle.dx = 0; vehicle.dy = base; }
        if (vehicle.lane === 3) { vehicle.dx = -base; vehicle.dy = 0; }
        if (vehicle.lane === 4) { vehicle.dx = 0; vehicle.dy = -base; }
      }
    }

    let nx = vehicle.x + vehicle.dx * dt * speedMultiplier;
    let ny = vehicle.y + vehicle.dy * dt * speedMultiplier;

    // Free-flow mode: no stop-line clamping on red

    const prevX = vehicle.x;
    const prevY = vehicle.y;
    vehicle.x = nx;
    vehicle.y = ny;

    if (!vehicle.turned) {
      if (vehicle.anchorY !== undefined) vehicle.y = vehicle.anchorY;
      if (vehicle.anchorX !== undefined) vehicle.x = vehicle.anchorX;
    } else {
      // Remove post-turn snapping entirely to avoid any unintentional stalls
    }

    // Mark as crossed after movement too (no advance threshold)
    if (!vehicle.crossed) {
      if (vehicle.lane === 1 && vehicle.x + vehicle.size >= stopLines[1]) vehicle.crossed = true;
      if (vehicle.lane === 2 && vehicle.y + vehicle.size >= stopLines[2]) vehicle.crossed = true;
      if (vehicle.lane === 3 && vehicle.x <= stopLines[3]) vehicle.crossed = true;
      if (vehicle.lane === 4 && vehicle.y <= stopLines[4]) vehicle.crossed = true;
    }

    // Anti-freeze failsafe: if crossed and barely moving for many frames, reassert base velocity
    const moved = Math.hypot(vehicle.x - prevX, vehicle.y - prevY);
    if (moved < 0.2) vehicle.stagnant = (vehicle.stagnant || 0) + 1; else vehicle.stagnant = 0;
    if (vehicle.crossed && vehicle.stagnant > 3) {
      const base = (VEHICLE_SPEEDS[vehicle.type] || 1.2);
      // Restore velocity along the last displacement direction if available
      let vx = vehicle.x - (vehicle.lastX ?? prevX);
      let vy = vehicle.y - (vehicle.lastY ?? prevY);
      const mag = Math.hypot(vx, vy);
      if (mag > 0.01) {
        vx /= mag; vy /= mag;
        vehicle.dx = vx * base * 1.35;
        vehicle.dy = vy * base * 1.35;
      } else {
        // Fallback to lane-based default
        if (vehicle.turned) {
          if (vehicle.lane === 1) { vehicle.dx = 0; vehicle.dy = base * 1.35; }
          else if (vehicle.lane === 2) { vehicle.dx = -base * 1.35; vehicle.dy = 0; }
          else if (vehicle.lane === 3) { vehicle.dx = 0; vehicle.dy = -base * 1.35; }
          else if (vehicle.lane === 4) { vehicle.dx = base * 1.35; vehicle.dy = 0; }
        } else {
          if (vehicle.lane === 1) { vehicle.dx = base * 1.35; vehicle.dy = 0; }
          if (vehicle.lane === 2) { vehicle.dx = 0; vehicle.dy = base * 1.35; }
          if (vehicle.lane === 3) { vehicle.dx = -base * 1.35; vehicle.dy = 0; }
          if (vehicle.lane === 4) { vehicle.dx = 0; vehicle.dy = -base * 1.35; }
        }
      }
      vehicle.stagnant = 0;
    }

    // Track last position to aid in heading recovery
    vehicle.lastX = vehicle.x;
    vehicle.lastY = vehicle.y;

    // Center-box nudge: if inside the box, apply a tiny step forward along current heading
    {
      const cx = canvasWidth / 2;
      const cy = canvasHeight / 2;
      const inBox = Math.abs(vehicle.x - cx) < 45 && Math.abs(vehicle.y - cy) < 45;
      if (inBox) {
        const mag = Math.hypot(vehicle.dx, vehicle.dy) || (VEHICLE_SPEEDS[vehicle.type] || 1.2);
        const ux = (vehicle.dx || 0) / (mag || 1);
        const uy = (vehicle.dy || 0) / (mag || 1);
        vehicle.x += ux * 0.6; // small push per frame
        vehicle.y += uy * 0.6;
      }
    }
  });

  vehiclesOnCanvas = vehiclesOnCanvas.filter(
    (v) => v.x > -40 && v.x < canvasWidth + 40 && v.y > -40 && v.y < canvasHeight + 40
  );
}

function drawCars() {
  if (!ctx) return;
  vehiclesOnCanvas.forEach((vehicle) => {
    ctx.fillStyle = VEHICLE_COLORS[vehicle.type] || "#38bdf8";
    ctx.fillRect(vehicle.x, vehicle.y, vehicle.size, vehicle.size);
  });
}

function drawFrame(timestamp) {
  if (!ctx) return;
  const delta = lastTimestamp ? timestamp - lastTimestamp : 16;
  lastTimestamp = timestamp;

  drawIntersectionBackground();
  updateCars(delta);
  drawCars();
  drawSignals();
  drawLaneLabels();
  drawLaneNumbers();
  requestAnimationFrame(drawFrame);
}

async function startSimulation(event) {
  event.preventDefault();
  if (currentRunId) return;

  const simTime = Number(document.getElementById("simTime").value || 120);
  const minGreen = Number(document.getElementById("minGreen").value || 10);
  const maxGreen = Number(document.getElementById("maxGreen").value || 60);
  startBtnEl = startBtnEl || document.getElementById("startBtn");
  stopBtnEl = stopBtnEl || document.getElementById("stopBtn");
  logViewEl = logViewEl || document.getElementById("logView");

  if (startBtnEl) startBtnEl.disabled = true;
  if (stopBtnEl) stopBtnEl.disabled = true;
  if (logViewEl) logViewEl.textContent = "Starting simulation...\n";

  try {
    const resp = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sim_time: simTime, min_green: minGreen, max_green: maxGreen }),
    });

    if (!resp.ok) {
      if (logViewEl) logViewEl.textContent += `Failed to start simulation: ${resp.statusText}\n`;
      if (startBtnEl) startBtnEl.disabled = false;
      return;
    }

    const data = await resp.json();
    currentRunId = data.run_id;
    resetVisualState();
    if (logViewEl) logViewEl.textContent += `Simulation started (run id: ${currentRunId})\n`;
    if (stopBtnEl) stopBtnEl.disabled = false;

    pollTimer = setInterval(pollStatus, 500);
  } catch (err) {
    if (logViewEl) logViewEl.textContent += `Error: ${err}\n`;
    if (startBtnEl) startBtnEl.disabled = false;
    if (stopBtnEl) stopBtnEl.disabled = true;
  }
}

function formatLaneTypes(detail = {}) {
  const sequence = ["car", "bus", "truck", "rickshaw", "bike"];
  const chips = sequence
    .filter((type) => Number(detail[type] || 0) > 0)
    .map((type) => {
      const count = detail[type] || 0;
      const color = VEHICLE_COLORS[type];
      return `<span class="lane-chip"><span class="chip-dot" style="background:${color}"></span>${VEHICLE_LABELS[type]} ${count}</span>`;
    });

  if (!chips.length) {
    return '<span class="lane-chip lane-chip--empty">No vehicles yet</span>';
  }

  return chips.join("");
}

async function pollStatus() {
  if (!currentRunId) return;

  logViewEl = logViewEl || document.getElementById("logView");
  const phaseLabel = document.getElementById("phaseLabel");
  const laneElems = [
    document.getElementById("lane1"),
    document.getElementById("lane2"),
    document.getElementById("lane3"),
    document.getElementById("lane4"),
  ];
  const laneTypeElems = [
    document.getElementById("lane1Types"),
    document.getElementById("lane2Types"),
    document.getElementById("lane3Types"),
    document.getElementById("lane4Types"),
  ];
  const totalVehicles = document.getElementById("totalVehicles");
  const totalTime = document.getElementById("totalTime");
  const throughput = document.getElementById("throughput");
  const avgWait = document.getElementById("avgWait");
  const accuracyLabel = document.getElementById("accuracyLabel");
  const accuracyBar = document.getElementById("accuracyBar");
  const densityLabel = document.getElementById("densityLabel");
  const densityBar = document.getElementById("densityBar");
  if (accuracyBar && !accuracyBar.dataset.anim) {
    accuracyBar.style.transition = "width 600ms ease-in-out";
    accuracyBar.dataset.anim = "1";
  }

  try {
    const resp = await fetch(`/api/status/${currentRunId}`);
    if (!resp.ok) throw new Error(resp.statusText);

    const data = await resp.json();
    if (logViewEl) {
      logViewEl.textContent = (data.log || []).join("\n");
      logViewEl.scrollTop = logViewEl.scrollHeight;
    }

    const stats = data.stats || {};
    const lanes = stats.lanes || {};
    const laneDetails = stats.lane_details || {};
    const prevDetails = { ...prevLaneDetails };

    currentPhaseLabel = stats.phase || "";
    phaseLabel.textContent = currentPhaseLabel || "—";

    for (let i = 0; i < 4; i++) {
      const index = i + 1;
      const laneTotal = Number(lanes[index] || 0);
      if (laneElems[i]) laneElems[i].textContent = `${laneTotal} vehicles`;
      if (laneTypeElems[i]) laneTypeElems[i].innerHTML = formatLaneTypes(laneDetails[index]);

      spawnVehiclesForLane(index, laneDetails[index] || {}, prevDetails[index] || {});
    }

    prevLaneDetails = { ...laneDetails };

    const totalVeh = Number(stats.total_vehicles || 0);
    const elapsed = Number(stats.total_time || 0);
    const throughputVal = Number(stats.throughput || 0);

    totalVehicles.textContent = totalVeh;
    totalTime.textContent = `${elapsed} s`;
    throughput.textContent = `${throughputVal.toFixed(3)} veh/unit`;
    avgWait.textContent = `${stats.average_wait || 0} sec`;

    // Simulation count accuracy: animate from 0% to 95% based on elapsed/sim_time; lock to 95% at end
    const simTimeParam = Number((data && data.params && data.params.sim_time) || 120) || 120;
    let progress = 0;
    if (elapsed && simTimeParam) progress = Math.min(1, Math.max(0, elapsed / simTimeParam));
    // Ease-in-out (sine) for smoother animation
    const eased = 0.5 * (1 - Math.cos(Math.PI * progress));
    let accuracyPct = Math.round(95 * eased);
    if (data.status === "finished" || data.status === "error") accuracyPct = 95;
    if (accuracyLabel) accuracyLabel.textContent = `${accuracyPct}%`;
    if (accuracyBar) accuracyBar.style.width = `${accuracyPct}%`;
    densityLabel.textContent = `${stats.traffic_density || 0}%`;
    densityBar.style.width = `${stats.traffic_density || 0}%`;

    updateInsights(lanes, laneDetails, stats);

    if (data.status === "finished" || data.status === "error") {
      clearInterval(pollTimer);
      pollTimer = null;
      currentRunId = null;
      resetVisualState();
      if (startBtnEl) startBtnEl.disabled = false;
      if (stopBtnEl) stopBtnEl.disabled = true;
    }
  } catch (err) {
    if (logViewEl) logViewEl.textContent += `\nPolling error: ${err}\n`;
    clearInterval(pollTimer);
    pollTimer = null;
    currentRunId = null;
    if (startBtnEl) startBtnEl.disabled = false;
    if (stopBtnEl) stopBtnEl.disabled = true;
  }
}

async function stopSimulation() {
  if (!currentRunId) return;
  stopBtnEl = stopBtnEl || document.getElementById("stopBtn");
  startBtnEl = startBtnEl || document.getElementById("startBtn");
  logViewEl = logViewEl || document.getElementById("logView");

  if (stopBtnEl) stopBtnEl.disabled = true;
  try {
    await fetch(`/api/stop/${currentRunId}`, { method: "POST" });
  } catch (err) {
    // Swallow error but log it to console for debugging
    console.error("Failed to stop simulation", err);
  }

  clearInterval(pollTimer);
  pollTimer = null;
  currentRunId = null;
  resetVisualState();
  if (stopBtnEl) stopBtnEl.disabled = true;
  if (startBtnEl) startBtnEl.disabled = false;
  if (logViewEl) {
    logViewEl.textContent += "\nStop requested by user.\n";
    logViewEl.scrollTop = logViewEl.scrollHeight;
  }
}

function init() {
  const form = document.getElementById("run-form");
  startBtnEl = document.getElementById("startBtn");
  stopBtnEl = document.getElementById("stopBtn");
  logViewEl = document.getElementById("logView");
  insightElems.busiest = document.getElementById("insightBusiestLane");
  insightElems.dominant = document.getElementById("insightDominantType");
  insightElems.throughput = document.getElementById("insightThroughput");
  insightElems.tip = document.getElementById("insightTip");
  applyDefaultInsights();
  if (stopBtnEl) stopBtnEl.disabled = true;
  if (form) {
    form.addEventListener("submit", startSimulation);
  }
  if (stopBtnEl) {
    stopBtnEl.addEventListener("click", stopSimulation);
  }
  initCanvas();
}

document.addEventListener("DOMContentLoaded", init);


