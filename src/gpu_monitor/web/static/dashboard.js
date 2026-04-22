/**
 * GPU Monitor Dashboard
 * Canvas API 직접 구현 (폐쇄망, CDN 불가)
 */

const REFRESH_MS = 5000;
const COLORS = [
    '#3b82f6', '#22c55e', '#eab308', '#ef4444', '#a855f7',
    '#06b6d4', '#f97316', '#ec4899', '#14b8a6', '#6366f1'
];

// ───── State ─────
let historyData = [];

// ───── GPU Card Rendering ─────

function getBarColor(value, thresholds) {
    if (value >= (thresholds?.red || 90)) return 'fill-red';
    if (value >= (thresholds?.yellow || 70)) return 'fill-yellow';
    return 'fill-blue';
}

function renderGpuCards(data) {
    const grid = document.getElementById('gpu-grid');
    const gpus = data.gpus || [];
    const vmStatuses = data.vm_statuses || {};

    // Update header counts
    const upCount = Object.values(vmStatuses).filter(v => v.is_up).length;
    const totalVMs = Object.keys(vmStatuses).length;
    document.getElementById('vm-count').textContent = `VM: ${upCount}/${totalVMs || gpus.length}`;
    document.getElementById('gpu-count').textContent = `GPU: ${gpus.length}`;

    if (gpus.length === 0) {
        grid.innerHTML = '<div class="no-alerts">GPU 데이터 없음. VM 연결을 확인하세요.</div>';
        return;
    }

    // Sort by host, then gpu_id
    gpus.sort((a, b) => {
        if (a.host !== b.host) return a.host.localeCompare(b.host);
        return String(a.gpu_id).localeCompare(String(b.gpu_id));
    });

    grid.innerHTML = gpus.map(gpu => {
        const m = gpu.metrics || {};
        const vmStatus = vmStatuses[gpu.host];
        const isDown = vmStatus && !vmStatus.is_up;

        const tensorActive = (m['DCGM_FI_PROF_PIPE_TENSOR_ACTIVE'] || 0) * 100;
        const dramActive = (m['DCGM_FI_PROF_DRAM_ACTIVE'] || 0) * 100;
        const gpuUtil = m['DCGM_FI_DEV_GPU_UTIL'] || 0;
        const memBW = m['DCGM_FI_DEV_MEM_COPY_UTIL'] || 0;
        const temp = m['DCGM_FI_DEV_GPU_TEMP'] || 0;
        const power = m['DCGM_FI_DEV_POWER_USAGE'] || 0;
        const vramUsed = m['DCGM_FI_DEV_FB_USED'] || 0;
        const vramFree = m['DCGM_FI_DEV_FB_FREE'] || 0;
        const vramTotal = vramUsed + vramFree;
        const vramPct = vramTotal > 0 ? (vramUsed / vramTotal) * 100 : 0;

        return `
        <div class="gpu-card${isDown ? ' down' : ''}">
            <div class="card-header">
                <span class="host-name">
                    <span class="status-dot ${isDown ? 'down' : 'up'}"></span>
                    ${gpu.host}
                </span>
                <span class="gpu-id">GPU ${gpu.gpu_id}</span>
            </div>
            <div class="metric-row">
                <span class="label">Tensor Core</span>
                <span class="value">${tensorActive.toFixed(1)}%</span>
            </div>
            <div class="metric-bar"><div class="fill ${getBarColor(tensorActive)}" style="width:${Math.min(tensorActive, 100)}%"></div></div>
            <div class="metric-row">
                <span class="label">Memory BW</span>
                <span class="value">${dramActive.toFixed(1)}%</span>
            </div>
            <div class="metric-bar"><div class="fill ${getBarColor(dramActive)}" style="width:${Math.min(dramActive, 100)}%"></div></div>
            <div class="metric-row">
                <span class="label">GPU Util</span>
                <span class="value">${gpuUtil.toFixed(1)}%</span>
            </div>
            <div class="metric-bar"><div class="fill ${getBarColor(gpuUtil)}" style="width:${Math.min(gpuUtil, 100)}%"></div></div>
            <div class="metric-row">
                <span class="label">VRAM</span>
                <span class="value">${(vramUsed / 1024).toFixed(1)} / ${(vramTotal / 1024).toFixed(1)} GiB</span>
            </div>
            <div class="metric-bar"><div class="fill fill-purple" style="width:${Math.min(vramPct, 100)}%"></div></div>
            <div class="metric-row">
                <span class="label">Temp</span>
                <span class="value" style="color:${temp >= 80 ? '#ef4444' : temp >= 70 ? '#eab308' : '#22c55e'}">${temp.toFixed(0)}°C</span>
            </div>
            <div class="metric-row">
                <span class="label">Power</span>
                <span class="value">${power.toFixed(0)} W</span>
            </div>
        </div>`;
    }).join('');
}

// ───── Canvas Chart Rendering ─────

function drawLineChart(canvasId, seriesMap, yLabel, yMax) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;

    // High-DPI canvas sizing
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);

    const W = rect.width;
    const H = rect.height;
    const pad = { top: 10, right: 12, bottom: 30, left: 46 };
    const plotW = W - pad.left - pad.right;
    const plotH = H - pad.top - pad.bottom;

    // Clear
    ctx.clearRect(0, 0, W, H);

    // Background
    ctx.fillStyle = '#1e293b';
    ctx.fillRect(0, 0, W, H);

    const seriesNames = Object.keys(seriesMap);
    if (seriesNames.length === 0) {
        ctx.fillStyle = '#94a3b8';
        ctx.font = '13px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('데이터 없음', W / 2, H / 2);
        return;
    }

    // Find time range
    let tMin = Infinity, tMax = -Infinity;
    for (const name of seriesNames) {
        const pts = seriesMap[name];
        for (const p of pts) {
            if (p.t < tMin) tMin = p.t;
            if (p.t > tMax) tMax = p.t;
        }
    }
    if (tMin === tMax) tMax = tMin + 60;

    // Auto y-max
    if (yMax == null) {
        yMax = 0;
        for (const name of seriesNames) {
            for (const p of seriesMap[name]) {
                if (p.v > yMax) yMax = p.v;
            }
        }
        yMax = Math.ceil(yMax * 1.1) || 1;
    }

    // Grid lines
    ctx.strokeStyle = '#334155';
    ctx.lineWidth = 0.5;
    const ySteps = 5;
    for (let i = 0; i <= ySteps; i++) {
        const y = pad.top + plotH - (i / ySteps) * plotH;
        ctx.beginPath();
        ctx.moveTo(pad.left, y);
        ctx.lineTo(pad.left + plotW, y);
        ctx.stroke();

        // Y labels
        ctx.fillStyle = '#94a3b8';
        ctx.font = '10px sans-serif';
        ctx.textAlign = 'right';
        const val = (yMax * i / ySteps);
        ctx.fillText(val.toFixed(val >= 10 ? 0 : 1), pad.left - 4, y + 3);
    }

    // X labels (time)
    ctx.textAlign = 'center';
    const xSteps = 5;
    for (let i = 0; i <= xSteps; i++) {
        const t = tMin + (tMax - tMin) * i / xSteps;
        const x = pad.left + (i / xSteps) * plotW;
        const d = new Date(t * 1000);
        const label = `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}:${d.getSeconds().toString().padStart(2, '0')}`;
        ctx.fillText(label, x, H - pad.bottom + 16);
    }

    // Draw lines
    let colorIdx = 0;
    for (const name of seriesNames) {
        const pts = seriesMap[name];
        if (pts.length < 2) continue;

        const color = COLORS[colorIdx % COLORS.length];
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.5;
        ctx.beginPath();

        for (let i = 0; i < pts.length; i++) {
            const x = pad.left + ((pts[i].t - tMin) / (tMax - tMin)) * plotW;
            const y = pad.top + plotH - (pts[i].v / yMax) * plotH;
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        }
        ctx.stroke();

        // Legend entry
        const legendY = pad.top + 4 + colorIdx * 14;
        const legendX = pad.left + 6;
        ctx.fillStyle = color;
        ctx.fillRect(legendX, legendY, 10, 10);
        ctx.fillStyle = '#f1f5f9';
        ctx.font = '10px sans-serif';
        ctx.textAlign = 'left';
        ctx.fillText(name, legendX + 14, legendY + 9);

        colorIdx++;
    }
}

function renderCharts(historyResp) {
    const data = historyResp.data || [];
    if (data.length === 0) return;

    // Build series for Tensor Core Active
    const tensorSeries = {};
    const membwSeries = {};

    for (const d of data) {
        const key = `${d.host} GPU ${d.gpu_id}`;
        if (d.metric_name === 'DCGM_FI_PROF_PIPE_TENSOR_ACTIVE') {
            if (!tensorSeries[key]) tensorSeries[key] = [];
            tensorSeries[key].push({ t: d.timestamp, v: d.value * 100 });
        }
        if (d.metric_name === 'DCGM_FI_PROF_DRAM_ACTIVE') {
            if (!membwSeries[key]) membwSeries[key] = [];
            membwSeries[key].push({ t: d.timestamp, v: d.value * 100 });
        }
    }

    drawLineChart('chart-tensor', tensorSeries, '%', 100);
    drawLineChart('chart-membw', membwSeries, '%', 100);
}

// ───── Alerts Rendering ─────

function renderAlerts(alertResp) {
    const list = document.getElementById('alert-list');
    const banner = document.getElementById('alert-banner');
    const active = alertResp.active || [];

    if (active.length === 0) {
        list.innerHTML = '<div class="no-alerts">알림 없음</div>';
        banner.classList.remove('active');
        return;
    }

    banner.textContent = `${active.length}개 활성 알림`;
    banner.classList.add('active');

    list.innerHTML = active.map(a => `
        <div class="alert-item">
            <span class="alert-type ${a.type}">${a.type}</span>
            <span>${a.message}</span>
        </div>
    `).join('');
}

// ───── Data Fetching ─────

async function fetchJson(url) {
    try {
        const resp = await fetch(url);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        return await resp.json();
    } catch (e) {
        console.error(`Fetch error (${url}):`, e);
        return null;
    }
}

async function refresh() {
    const [current, history, alerts, recording] = await Promise.all([
        fetchJson('/api/current'),
        fetchJson('/api/history?minutes=5'),
        fetchJson('/api/alerts'),
        fetchJson('/api/recording/status'),
    ]);

    if (current) renderGpuCards(current);
    if (history) renderCharts(history);
    if (alerts) renderAlerts(alerts);

    // Recording status
    const recEl = document.getElementById('recording-status');
    if (recording && recording.recording) {
        recEl.innerHTML = '<span style="color:#ef4444">● REC</span> ' + (recording.label || '');
    } else {
        recEl.textContent = '';
    }

    // Update timestamp
    document.getElementById('last-update').textContent =
        '최근 갱신: ' + new Date().toLocaleTimeString('ko-KR');
}

// ───── Init ─────
refresh();
setInterval(refresh, REFRESH_MS);
