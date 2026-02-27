let killsChartInstance = null;
let winChartInstance = null;

function buildReportUrl(start, end) {
  let url = "/api/report";
  const params = [];
  if (start) params.push(`start=${encodeURIComponent(start)}`);
  if (end) params.push(`end=${encodeURIComponent(end)}`);
  if (params.length) url += "?" + params.join("&");
  return url;
}

function buildCsvUrl(start, end) {
  let url = "/api/report/csv";
  const params = [];
  if (start) params.push(`start=${encodeURIComponent(start)}`);
  if (end) params.push(`end=${encodeURIComponent(end)}`);
  if (params.length) url += "?" + params.join("&");
  return url;
}

function setLoading(isLoading) {
  const report = document.getElementById("report");
  if (!report) return;
  if (isLoading) {
    report.innerHTML = `
      <div class="muted" style="display:flex; align-items:center; gap:10px;">
        <div class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></div>
        Loading analytics...
      </div>
    `;
  }
}

function safeDestroy(chart) {
  if (chart && typeof chart.destroy === "function") {
    chart.destroy();
  }
}

function palette(i) {
  const colors = [
    "rgba(34, 255, 136, 0.75)",
    "rgba(0, 229, 255, 0.75)",
    "rgba(124, 92, 255, 0.75)",
    "rgba(255, 215, 0, 0.75)",
    "rgba(239, 68, 68, 0.70)",
    "rgba(96, 214, 154, 0.70)",
    "rgba(147, 197, 253, 0.70)"
  ];
  return colors[i % colors.length];
}

function renderTextReport(data, start, end) {
  const report = document.getElementById("report");
  if (!report) return;

  if (!Array.isArray(data) || data.length === 0) {
    report.innerHTML = `
      <div class="glass-card" style="text-align:center;">
        <div style="font-size:40px; margin-bottom:6px;">📉</div>
        <div style="font-weight:800; color: var(--text-secondary);">No data in this range</div>
        <div class="muted small" style="margin-top:6px;">Try different dates, or upload match records.</div>
      </div>
    `;
    return;
  }

  let best = data[0];
  data.forEach((p) => {
    if ((p.kills || 0) > (best.kills || 0)) best = p;
  });

  const rangeLabel = (start || end)
    ? `<span class="pill">Range: ${start || "…"} → ${end || "…"}</span>`
    : `<span class="pill">Range: All time</span>`;

  const rows = data.map((p, idx) => {
    const matches = p.matches ?? "-";
    const kills = p.kills ?? 0;
    const damage = p.damage ?? 0;
    const avg = p.avg_kills ?? 0;
    const win = p.winrate ?? 0;
    return `
      <tr style="background:#0f1624;">
        <td style="padding:10px; font-weight:800; color: var(--text-secondary);">#${idx + 1}</td>
        <td style="padding:10px; font-weight:800; color: var(--text-primary);">${p.name}</td>
        <td style="padding:10px; text-align:right;">${matches}</td>
        <td style="padding:10px; text-align:right; color: var(--accent-primary); font-weight:800;">${kills}</td>
        <td style="padding:10px; text-align:right;">${damage}</td>
        <td style="padding:10px; text-align:right;">${avg}</td>
        <td style="padding:10px; text-align:right; color: var(--gold); font-weight:800;">${win}%</td>
      </tr>
    `;
  }).join("");

  report.innerHTML = `
    <div class="glass-card" style="border-left:4px solid var(--accent-primary); margin-bottom:12px;">
      <div style="display:flex; justify-content:space-between; gap:10px; flex-wrap:wrap; align-items:center;">
        <div>
          <div class="muted small">Top performer</div>
          <div style="font-weight:900; font-size:1.1rem; color: var(--text-primary);">🔥 ${best.name} (${best.kills || 0} kills)</div>
        </div>
        ${rangeLabel}
      </div>
    </div>

    <div style="overflow-x:auto;">
      <table style="width:100%; border-collapse: separate; border-spacing: 0 8px;">
        <thead>
          <tr style="color: var(--accent-primary); font-weight:800; text-align:left;">
            <th style="padding:10px;">Rank</th>
            <th style="padding:10px;">Player</th>
            <th style="padding:10px; text-align:right;">Matches</th>
            <th style="padding:10px; text-align:right;">Kills</th>
            <th style="padding:10px; text-align:right;">Damage</th>
            <th style="padding:10px; text-align:right;">Avg Kills</th>
            <th style="padding:10px; text-align:right;">Winrate</th>
          </tr>
        </thead>
        <tbody>
          ${rows}
        </tbody>
      </table>
    </div>
  `;
}

async function loadReport(start, end) {
  setLoading(true);

  const url = buildReportUrl(start, end);
  const res = await fetch(url);
  const data = await res.json();

  // sort by kills desc for clearer charts
  const sorted = Array.isArray(data) ? data.slice().sort((a, b) => (b.kills || 0) - (a.kills || 0)) : [];

  const names = sorted.map((p) => p.name);
  const kills = sorted.map((p) => p.kills || 0);
  const winrate = sorted.map((p) => p.winrate || 0);

  // Destroy previous charts (prevents stacking / memory leak)
  safeDestroy(killsChartInstance);
  safeDestroy(winChartInstance);

  const killsCtx = document.getElementById("killsChart");
  const winCtx = document.getElementById("winChart");

  if (killsCtx) {
    killsChartInstance = new Chart(killsCtx, {
      type: "bar",
      data: {
        labels: names,
        datasets: [{
          label: "Total Kills",
          data: kills,
          backgroundColor: "rgba(34, 255, 136, 0.35)",
          borderColor: "rgba(34, 255, 136, 0.9)",
          borderWidth: 1,
          borderRadius: 8
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => ` Kills: ${ctx.parsed.y}`
            }
          }
        },
        scales: {
          x: { ticks: { maxRotation: 0, autoSkip: true } },
          y: { beginAtZero: true, ticks: { precision: 0 } }
        }
      }
    });
  }

  if (winCtx) {
    winChartInstance = new Chart(winCtx, {
      type: "doughnut",
      data: {
        labels: names,
        datasets: [{
          label: "Win Rate",
          data: winrate,
          backgroundColor: winrate.map((_, i) => palette(i)),
          borderColor: "rgba(255,255,255,0.05)",
          borderWidth: 1
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          tooltip: {
            callbacks: {
              label: (ctx) => ` ${ctx.label}: ${ctx.parsed}%`
            }
          }
        },
        cutout: "60%"
      }
    });
  }

  renderTextReport(sorted, start, end);
}

// wire up filter controls if present
const startInput = document.getElementById("filterStart");
const endInput = document.getElementById("filterEnd");
const applyBtn = document.getElementById("applyFilter");
const exportBtn = document.getElementById("exportCsv");

function currentRange() {
  return {
    start: startInput && startInput.value ? startInput.value : "",
    end: endInput && endInput.value ? endInput.value : ""
  };
}

if (applyBtn) {
  applyBtn.addEventListener("click", () => {
    const r = currentRange();
    loadReport(r.start, r.end);
  });
}

if (exportBtn) {
  exportBtn.addEventListener("click", () => {
    const r = currentRange();
    window.location = buildCsvUrl(r.start, r.end);
  });
}

// initial load
loadReport();