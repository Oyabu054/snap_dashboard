// =========================================================
// 欠点モニタリングダッシュボード — フロントエンドロジック
// =========================================================

const COLORS = {
  bg: '#ffffff',
  grid: '#e2e5ea',
  text: '#1c2230',
  muted: '#667085',
  accent: '#d97706',
  accent2: '#0e7490',
  critical: '#b91c1c',
};

const PALETTE = [COLORS.accent, COLORS.accent2, COLORS.critical, '#7c5cd6', '#15803d'];

let liveTimer = null;

const el = (id) => document.getElementById(id);

function toLocalInputValue(date) {
  const pad = (n) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function setDefaultRange(hours = 24) {
  const end = new Date();
  const start = new Date(end.getTime() - hours * 3600 * 1000);
  el('startInput').value = toLocalInputValue(start);
  el('endInput').value = toLocalInputValue(end);
}

function showError(message) {
  const box = el('errorBox');
  if (!message) {
    box.hidden = true;
    box.textContent = '';
    return;
  }
  box.hidden = false;
  box.textContent = message;
}

async function fetchJSON(url) {
  const res = await fetch(url);
  const data = await res.json();
  if (!res.ok || data.error) {
    throw new Error(data.error || `リクエスト失敗: ${url}`);
  }
  return data;
}

async function loadDefectTypes() {
  const container = el('defectTypeList');
  try {
    const { defect_types } = await fetchJSON('/api/defect_types');
    if (!defect_types.length) {
      container.innerHTML = '<span class="muted">種類が見つかりません</span>';
      return;
    }
    container.innerHTML = defect_types.map((t, i) => `
      <label>
        <input type="checkbox" value="${t}" checked data-color="${PALETTE[i % PALETTE.length]}">
        ${t}
      </label>
    `).join('');
  } catch (e) {
    container.innerHTML = '<span class="muted">読み込みに失敗しました</span>';
    showError(e.message);
  }
}

function getSelectedTypes() {
  return Array.from(document.querySelectorAll('#defectTypeList input:checked')).map((c) => c.value);
}

function typeColorMap() {
  const map = {};
  document.querySelectorAll('#defectTypeList input').forEach((c) => {
    map[c.value] = c.dataset.color;
  });
  return map;
}

function baseLayout(extra = {}) {
  return Object.assign({
    paper_bgcolor: COLORS.bg,
    plot_bgcolor: COLORS.bg,
    font: { color: COLORS.text, family: 'IBM Plex Sans JP, sans-serif', size: 11 },
    margin: { l: 50, r: 20, t: 10, b: 40 },
    xaxis: { gridcolor: COLORS.grid, zerolinecolor: COLORS.grid, color: COLORS.muted },
    yaxis: { gridcolor: COLORS.grid, zerolinecolor: COLORS.grid, color: COLORS.muted },
    showlegend: true,
    legend: { orientation: 'h', y: -0.25, font: { color: COLORS.muted, size: 10 } },
    hovermode: 'closest',
    hoverlabel: { bgcolor: '#ffffff', bordercolor: COLORS.grid, font: { color: COLORS.text, size: 11 } },
  }, extra);
}

// 継続時間データが無い/極端に短い欠点も見えるようにする最小表示幅(分)
const MIN_VISIBLE_DURATION_MINUTES = 0.15;

function buildDurationSegments(rows) {
  // 各欠点を (発生時刻)→(発生時刻+継続時間) の線分として描画するためのデータを組み立てる。
  // 線分の間にnullを挟むことで、Plotly上で個々の欠点として独立して表示される。
  const x = [];
  const y = [];
  const customdata = [];

  rows.forEach((r) => {
    const startMs = new Date(r.timestamp).getTime();
    const durationMin = Math.max(r.duration_minutes || 0, MIN_VISIBLE_DURATION_MINUTES);
    const endMs = startMs + durationMin * 60000;
    const label = r.duration_minutes != null ? `${r.duration_minutes.toFixed(1)}分` : '—';

    x.push(new Date(startMs).toISOString(), new Date(endMs).toISOString(), null);
    y.push(r.position, r.position, null);
    customdata.push(label, label, null);
  });

  return { x, y, customdata };
}

async function loadDefectMap(start, end, types) {
  const paramsDefects = new URLSearchParams({ start, end });
  types.forEach((t) => paramsDefects.append('type', t));
  const paramsProduct = new URLSearchParams({ start, end });

  const [{ data: defects }, { data: productPos }] = await Promise.all([
    fetchJSON(`/api/defects?${paramsDefects}`),
    fetchJSON(`/api/product_position?${paramsProduct}`),
  ]);
  const colors = typeColorMap();

  const traces = types.map((t) => {
    const rows = defects.filter((d) => d.defect_type === t);
    const seg = buildDurationSegments(rows);
    return {
      x: seg.x,
      y: seg.y,
      customdata: seg.customdata,
      mode: 'lines+markers',
      type: 'scatter',
      name: t,
      line: { color: colors[t] || COLORS.accent, width: 6 },
      marker: { color: colors[t] || COLORS.accent, size: 5 },
      hovertemplate: `<b>${t}</b><br>発生時刻: %{x|%m/%d %H:%M:%S}<br>位置: %{y:.1f}<br>継続時間: %{customdata}<extra></extra>`,
    };
  });

  // 製品位置(Gross幅・Net幅)は欠点種類フィルターに関係なく常時表示(線のみ、塗りつぶしなし)
  const GROSS_COLOR = '#94a3b8';
  const NET_COLOR = '#475569';

  traces.push({
    x: productPos.map((p) => p.timestamp),
    y: productPos.map((p) => p.gross_end),
    mode: 'lines', type: 'scatter', name: '製品位置(Gross)', legendgroup: 'gross',
    line: { color: GROSS_COLOR, width: 1 }, hoverinfo: 'skip',
  });
  traces.push({
    x: productPos.map((p) => p.timestamp),
    y: productPos.map((p) => p.gross_start),
    mode: 'lines', type: 'scatter', name: '製品位置(Gross)', legendgroup: 'gross',
    line: { color: GROSS_COLOR, width: 1 }, hoverinfo: 'skip', showlegend: false,
  });
  traces.push({
    x: productPos.map((p) => p.timestamp),
    y: productPos.map((p) => p.net_end),
    mode: 'lines', type: 'scatter', name: '製品位置(Net)', legendgroup: 'net',
    line: { color: NET_COLOR, width: 1.3, dash: 'dot' }, hoverinfo: 'skip',
  });
  traces.push({
    x: productPos.map((p) => p.timestamp),
    y: productPos.map((p) => p.net_start),
    mode: 'lines', type: 'scatter', name: '製品位置(Net)', legendgroup: 'net',
    line: { color: NET_COLOR, width: 1.3, dash: 'dot' }, hoverinfo: 'skip', showlegend: false,
  });

  const posMax = window.POSITION_MAX || 210;
  Plotly.react('defectMap', traces, baseLayout({
    yaxis: {
      title: '位置',
      range: [0, posMax],
      gridcolor: COLORS.grid, color: COLORS.muted,
    },
    annotations: [
      { xref: 'paper', yref: 'y', x: -0.065, y: posMax, xanchor: 'right',
        text: '左', showarrow: false, font: { color: COLORS.muted, size: 11 } },
      { xref: 'paper', yref: 'y', x: -0.065, y: 0, xanchor: 'right',
        text: '右', showarrow: false, font: { color: COLORS.muted, size: 11 } },
    ],
  }), { responsive: true, displayModeBar: false });
}

async function loadTrend(start, end, types) {
  const params = new URLSearchParams({ start, end });
  types.forEach((t) => params.append('type', t));
  const { data } = await fetchJSON(`/api/trend?${params}`);

  const trace = {
    x: data.map((d) => d.hour),
    y: data.map((d) => d.occurrence_minutes),
    customdata: data.map((d) => d.count),
    type: 'bar',
    marker: { color: COLORS.accent },
    name: '発生分数',
    hovertemplate: '%{x}<br>発生分数: %{y:.1f}分<br>件数: %{customdata}<extra></extra>',
  };

  Plotly.react('trendChart', [trace], baseLayout({
    yaxis: { title: '発生分数 (分/時間)', gridcolor: COLORS.grid, color: COLORS.muted },
    showlegend: false,
  }), { responsive: true, displayModeBar: false });
}

async function loadPhotos(start, end) {
  const container = el('photoList');
  const params = new URLSearchParams({ start, end });
  try {
    const { data } = await fetchJSON(`/api/photos?${params}`);
    if (!data.length) {
      container.innerHTML = '<span class="muted">該当する写真がありません</span>';
      return;
    }
    container.innerHTML = data.map((p) => `
      <div class="photo-card">
        <img src="${p.thumbnail_url}" alt="${p.name}" loading="lazy"
             onerror="this.style.visibility='hidden'">
        <div class="photo-card__meta">
          <div class="photo-card__time">${p.timestamp.replace('T', ' ').slice(0, 16)}</div>
          <div class="photo-card__name">${p.name}</div>
        </div>
      </div>
    `).join('');
  } catch (e) {
    container.innerHTML = '<span class="muted">写真の取得に失敗しました</span>';
    // Box側のエラーはグラフ表示を妨げないよう、ここでは致命的エラーにしない
    console.error(e);
  }
}

async function applyFilter() {
  showError(null);
  const startLocal = el('startInput').value;
  const endLocal = el('endInput').value;
  if (!startLocal || !endLocal) {
    showError('開始日時と終了日時を指定してください');
    return;
  }
  const start = new Date(startLocal).toISOString();
  const end = new Date(endLocal).toISOString();
  const types = getSelectedTypes();

  const btn = el('applyFilter');
  btn.disabled = true;
  btn.textContent = '読み込み中…';
  try {
    await Promise.all([
      loadDefectMap(start, end, types),
      loadTrend(start, end, types),
      loadPhotos(start, end),
    ]);
    el('lastUpdated').textContent = `最終更新 ${new Date().toLocaleTimeString('ja-JP')}`;
  } catch (e) {
    showError(e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = '適用';
  }
}

function setupLiveToggle() {
  el('liveToggle').addEventListener('change', (e) => {
    if (e.target.checked) {
      liveTimer = setInterval(() => {
        el('endInput').value = toLocalInputValue(new Date());
        applyFilter();
      }, 30000);
    } else {
      clearInterval(liveTimer);
      liveTimer = null;
    }
  });
}

function setupQuickRange() {
  document.querySelectorAll('.btn-quick').forEach((btn) => {
    btn.addEventListener('click', () => {
      setDefaultRange(Number(btn.dataset.hours));
      applyFilter();
    });
  });
}

async function init() {
  setDefaultRange(24);
  await loadDefectTypes();
  el('applyFilter').addEventListener('click', applyFilter);
  setupLiveToggle();
  setupQuickRange();
  applyFilter();
}

document.addEventListener('DOMContentLoaded', init);
