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

// 欠点種類ごとの識別色(固定順・カラーユニバーサルデザイン検証済み)
const PALETTE = ['#2a78d6', '#008300', '#e87ba4', '#eda100', '#1baf7a', '#eb6834', '#4a3aa7', '#e34948'];

// X軸(日時)の表示フォーマット・目盛り密度(共通)
const TIME_TICKFORMAT = '%-m/%-d %H:%M';
const TIME_NTICKS = 20;

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
        <span class="color-swatch" style="background:${PALETTE[i % PALETTE.length]}"></span>
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

function setupTypeSelectButtons() {
  el('selectAllTypes').addEventListener('click', () => {
    document.querySelectorAll('#defectTypeList input[type="checkbox"]').forEach((c) => { c.checked = true; });
  });
  el('deselectAllTypes').addEventListener('click', () => {
    document.querySelectorAll('#defectTypeList input[type="checkbox"]').forEach((c) => { c.checked = false; });
  });
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
    xaxis: {
      tickformat: TIME_TICKFORMAT, nticks: TIME_NTICKS,
      gridcolor: COLORS.grid, zerolinecolor: COLORS.grid, color: COLORS.muted,
    },
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

function renderDefectMap(defects, productPos, types, range) {
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
      // 欠点種類の凡例は左のチェックボックス(色スウォッチ付き)が兼ねるため、
      // 種類数が増えてもグラフ側の凡例が横に溢れて見切れないようにここでは非表示にする
      showlegend: false,
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
    mode: 'lines', type: 'scatter', name: 'Gross幅', legendgroup: 'gross',
    line: { color: GROSS_COLOR, width: 1 }, hoverinfo: 'skip',
  });
  traces.push({
    x: productPos.map((p) => p.timestamp),
    y: productPos.map((p) => p.gross_start),
    mode: 'lines', type: 'scatter', name: 'Gross幅', legendgroup: 'gross',
    line: { color: GROSS_COLOR, width: 1 }, hoverinfo: 'skip', showlegend: false,
  });
  traces.push({
    x: productPos.map((p) => p.timestamp),
    y: productPos.map((p) => p.net_end),
    mode: 'lines', type: 'scatter', name: 'Net幅', legendgroup: 'net',
    line: { color: NET_COLOR, width: 1.3, dash: 'dot' }, hoverinfo: 'skip',
  });
  traces.push({
    x: productPos.map((p) => p.timestamp),
    y: productPos.map((p) => p.net_start),
    mode: 'lines', type: 'scatter', name: 'Net幅', legendgroup: 'net',
    line: { color: NET_COLOR, width: 1.3, dash: 'dot' }, hoverinfo: 'skip', showlegend: false,
  });

  const posMax = window.POSITION_MAX || 210;
  Plotly.react('defectMap', traces, baseLayout({
    xaxis: {
      tickformat: TIME_TICKFORMAT, nticks: TIME_NTICKS, range,
      gridcolor: COLORS.grid, zerolinecolor: COLORS.grid, color: COLORS.muted,
    },
    yaxis: {
      title: '位置',
      range: [0, posMax],
      gridcolor: COLORS.grid, color: COLORS.muted,
    },
    showlegend: false,
    annotations: [
      { xref: 'paper', yref: 'y', x: -0.065, y: posMax, xanchor: 'right',
        text: '左', showarrow: false, font: { color: COLORS.muted, size: 11 } },
      { xref: 'paper', yref: 'y', x: -0.065, y: 0, xanchor: 'right',
        text: '右', showarrow: false, font: { color: COLORS.muted, size: 11 } },
    ],
  }), { responsive: true, displayModeBar: false });
}

function buildHourlyTrendByType(defects) {
  // 各欠点の発生時刻を1時間単位に切り捨ててバケット化し、種類ごとに発生分数(継続時間の合計)を集計する
  const buckets = {}; // { hourISO: { defectType: occurrenceMinutes } }

  defects.forEach((d) => {
    const dt = new Date(d.timestamp);
    dt.setMinutes(0, 0, 0);
    const hourKey = dt.toISOString();
    const typeMap = buckets[hourKey] || (buckets[hourKey] = {});
    const minutes = d.duration_minutes || 0;
    typeMap[d.defect_type] = (typeMap[d.defect_type] || 0) + minutes;
  });

  return { hours: Object.keys(buckets).sort(), buckets };
}

// Plotlyは棒の幅をデータ点同士の間隔から自動推定するため、表示期間が短く
// バーの本数が少ないと「1時間」から幅がズレて見える。明示的に1時間分で固定する。
const ONE_HOUR_MS = 60 * 60 * 1000;

function renderTrend(defects, types, range) {
  const { hours, buckets } = buildHourlyTrendByType(defects);
  const colors = typeColorMap();

  const traces = types.map((t) => ({
    x: hours,
    y: hours.map((h) => (buckets[h] && buckets[h][t]) || 0),
    type: 'bar',
    width: ONE_HOUR_MS,
    name: t,
    // 欠点種類の凡例は左のチェックボックス(色スウォッチ付き)が兼ねるため非表示
    showlegend: false,
    marker: { color: colors[t] || COLORS.accent },
    hovertemplate: `<b>${t}</b><br>%{x|${TIME_TICKFORMAT}}<br>発生分数: %{y:.1f}分<extra></extra>`,
  }));

  Plotly.react('trendChart', traces, baseLayout({
    barmode: 'stack',
    showlegend: false,
    // 上段の欠点マップとX軸(時間)の目盛り位置がずれないよう、同じ表示範囲を明示指定する
    xaxis: {
      tickformat: TIME_TICKFORMAT, nticks: TIME_NTICKS, range,
      gridcolor: COLORS.grid, zerolinecolor: COLORS.grid, color: COLORS.muted,
    },
    yaxis: { title: '発生分数 (分/時間)', gridcolor: COLORS.grid, color: COLORS.muted },
  }), { responsive: true, displayModeBar: false });
}

// =========================================================
// 期間絞り込みスクロールバー(左パネル)
// 取得済みデータの再取得はせず、両チャートのx軸表示範囲だけをズームする
// =========================================================
const PERIOD_SLIDER_STEPS = 1000;
let periodSliderRange = null; // { startMs, endMs } 現在適用中の全期間

function formatSliderDate(date) {
  const pad = (n) => String(n).padStart(2, '0');
  return `${date.getMonth() + 1}/${date.getDate()} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function sliderStepToDate(step) {
  const { startMs, endMs } = periodSliderRange;
  return new Date(startMs + ((endMs - startMs) * step) / PERIOD_SLIDER_STEPS);
}

function updatePeriodSliderUI() {
  const minInput = el('periodSliderMin');
  const maxInput = el('periodSliderMax');
  const lo = Math.min(Number(minInput.value), Number(maxInput.value));
  const hi = Math.max(Number(minInput.value), Number(maxInput.value));

  el('periodSliderFill').style.left = `${(lo / PERIOD_SLIDER_STEPS) * 100}%`;
  el('periodSliderFill').style.width = `${((hi - lo) / PERIOD_SLIDER_STEPS) * 100}%`;
  el('periodSliderValues').textContent = `${formatSliderDate(sliderStepToDate(lo))} 〜 ${formatSliderDate(sliderStepToDate(hi))}`;
}

function applyPeriodSliderZoom() {
  updatePeriodSliderUI();
  const minInput = el('periodSliderMin');
  const maxInput = el('periodSliderMax');
  const lo = Math.min(Number(minInput.value), Number(maxInput.value));
  const hi = Math.max(Number(minInput.value), Number(maxInput.value));
  const range = [sliderStepToDate(lo).toISOString(), sliderStepToDate(hi).toISOString()];
  Plotly.relayout('defectMap', { 'xaxis.range': range });
  Plotly.relayout('trendChart', { 'xaxis.range': range });
}

function resetPeriodSlider(startMs, endMs) {
  periodSliderRange = { startMs, endMs };
  el('periodSliderMin').value = 0;
  el('periodSliderMax').value = PERIOD_SLIDER_STEPS;
  updatePeriodSliderUI();
}

// 両ハンドルが交差しないよう最低間隔(全体の2%)を確保しつつズームを反映する
const PERIOD_SLIDER_MIN_GAP = PERIOD_SLIDER_STEPS * 0.02;

function setupPeriodSlider() {
  const minInput = el('periodSliderMin');
  const maxInput = el('periodSliderMax');
  minInput.addEventListener('input', () => {
    if (Number(minInput.value) > Number(maxInput.value) - PERIOD_SLIDER_MIN_GAP) {
      minInput.value = Number(maxInput.value) - PERIOD_SLIDER_MIN_GAP;
    }
    applyPeriodSliderZoom();
  });
  maxInput.addEventListener('input', () => {
    if (Number(maxInput.value) < Number(minInput.value) + PERIOD_SLIDER_MIN_GAP) {
      maxInput.value = Number(minInput.value) + PERIOD_SLIDER_MIN_GAP;
    }
    applyPeriodSliderZoom();
  });
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
    const paramsDefects = new URLSearchParams({ start, end });
    types.forEach((t) => paramsDefects.append('type', t));
    const paramsProduct = new URLSearchParams({ start, end });

    const [{ data: defects }, { data: productPos }] = await Promise.all([
      fetchJSON(`/api/defects?${paramsDefects}`),
      fetchJSON(`/api/product_position?${paramsProduct}`),
    ]);

    const range = [start, end];
    renderDefectMap(defects, productPos, types, range);
    renderTrend(defects, types, range);
    resetPeriodSlider(new Date(start).getTime(), new Date(end).getTime());

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
  setupPeriodSlider();
  setupTypeSelectButtons();
  applyFilter();
}

document.addEventListener('DOMContentLoaded', init);
