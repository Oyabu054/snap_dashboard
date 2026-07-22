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

// LOBB位置(線)・失透(点)の色。既存パレットとの衝突なしをdataviz skillで検証済み
const LOBB_COLOR = '#1e3a8a';
const DEVITRIFICATION_COLOR = '#65a30d';

// スナップ・欠点種類リスト(#defectTypeList)のうち、PIの実際の欠点種類ではなく
// マップの表示/非表示だけを切り替える参照要素(LOBB位置・失透)のラベル
const REFERENCE_MAP_ELEMENTS = [
  { label: 'LOBB', color: LOBB_COLOR },
  { label: '失透', color: DEVITRIFICATION_COLOR },
];

// X軸(日時)の表示フォーマット・目盛り密度(共通)
const TIME_TICKFORMAT = '%-m/%-d %H:%M';
const TIME_NTICKS = 20;

// X軸(時刻)のdtick(目盛り間隔)候補(ミリ秒)。Plotlyの自動tick計算(nticks指定)に
// 任せると、右側に複数の追加y軸を持つトレンド側と、追加軸を持たないマップ側とで
// 選ばれるdtickが微妙に食い違うことがあり、表示期間を伸ばすほど2つのグラフの
// X軸目盛り位置が縦方向にズレて見える不具合があった。両チャートで完全に同じ
// dtick/tick0を明示指定することで、期間の長さによらず必ず一致させる
const TICK_CANDIDATES_MS = [
  60e3, 5 * 60e3, 10 * 60e3, 15 * 60e3, 30 * 60e3,
  3600e3, 2 * 3600e3, 3 * 3600e3, 6 * 3600e3, 12 * 3600e3,
  24 * 3600e3, 2 * 24 * 3600e3, 3 * 24 * 3600e3, 7 * 24 * 3600e3,
  14 * 24 * 3600e3, 30 * 24 * 3600e3,
];

function computeTimeAxisTicks(startStr, endStr) {
  const spanMs = new Date(endStr).getTime() - new Date(startStr).getTime();
  const target = spanMs / TIME_NTICKS;
  const dtick = TICK_CANDIDATES_MS.find((c) => c >= target) || TICK_CANDIDATES_MS[TICK_CANDIDATES_MS.length - 1];
  return { dtick, tick0: startStr };
}

// =========================================================
// トレンドグラフの重ね描画系列(発生分数の棒グラフに加えて右側に別軸で重ねる系列)。
// PI AF側に属性が追加されるたびにここへ1件足せば、フィルターUI・データ取得・
// 軸/トレース描画すべてに反映される(既存8色パレット+この配列の色は
// dataviz skillのvalidate_palette.jsでCVD安全性を確認済み・衝突なし)。
// pad/capMax: 軸レンジは表示期間内の実データの最小/最大値を四捨五入し、
// そこからpad分だけ外側にパディングする(capMaxがあれば上限をそこでキャップ)
// =========================================================
const OVERLAY_SERIES = [
  {
    key: 'cstRotation', label: 'CST回転数', unit: 'rpm', color: '#0891b2', dash: undefined,
    valueFormat: '.1f', endpoint: '/api/cst_rotation_trend', pad: 3, capMax: 26,
  },
  {
    key: 'thickness', label: '厚み', unit: 'mm', color: '#a16207', dash: 'dash',
    valueFormat: '.2f', endpoint: '/api/thickness_trend', pad: 1, capMax: null,
  },
  {
    key: 'vacuumPressure', label: '絶対真空圧', unit: 'mmHg', color: '#be185d', dash: 'dot',
    valueFormat: '.1f', endpoint: '/api/vacuum_pressure_trend', pad: 3, capMax: null,
  },
];

// 軸レンジは「適用」操作時のみ再計算し、リアルタイム更新中は固定する(ユーザー指示)。
// キー: OVERLAY_SERIESのkey、値: [min, max]
let overlayAxisRanges = {};

function roundedAxisRange(values, pad, capMax) {
  if (!values.length) return null;
  const minV = Math.round(Math.min(...values));
  const maxV = Math.round(Math.max(...values));
  const hi = capMax != null ? Math.min(maxV + pad, capMax) : maxV + pad;
  return [minV - pad, hi];
}

// トレンドグラフ右側の追加軸1本あたりの余白見込み(px)。スナップマップ側は
// この軸を使わないが、両チャートのプロット領域幅を揃えて縦方向のX軸(時刻)位置を
// 一致させるため、活性化している系列数に応じて両チャートに同じ右余白を指定する
const RIGHT_MARGIN_BASE = 20;
const RIGHT_MARGIN_PER_AXIS = 45;

function computeRightMargin(activeSeriesCount) {
  return RIGHT_MARGIN_BASE + RIGHT_MARGIN_PER_AXIS * activeSeriesCount;
}

// 重ね描画系列(CST回転数・厚み・絶対真空圧など)の凡例を、Plotly自身のグラフ下の凡例
// ではなく、時間帯別トレンドのタイトル横に表示する(ユーザー指示)
function updateTrendLegend(activeSeries) {
  el('trendLegend').innerHTML = activeSeries.map((s) => `
    <span class="trend-legend__item">
      <span class="color-swatch" style="background:${s.color}"></span>${s.label}
    </span>
  `).join('');
}

function renderOverlaySeriesCheckboxes() {
  const container = el('overlaySeriesList');
  container.innerHTML = OVERLAY_SERIES.map((s) => `
    <label>
      <input type="checkbox" value="${s.key}" checked>
      <span class="color-swatch" style="background:${s.color}"></span>
      ${s.label}
    </label>
  `).join('');
}

function getSelectedOverlaySeriesKeys() {
  return Array.from(document.querySelectorAll('#overlaySeriesList input:checked')).map((c) => c.value);
}

let liveTimer = null;

// 下段トレンドグラフの表示モード。'defects'=既存の発生分数トレンド、'lobb'=LOBB発生個数トレンド
// (スナップの発生分数とは内容が全く異なるため、重ねずグラフを丸ごと切り替える)
let trendMode = 'defects';

// 直前の「適用」操作で確定した全期間 [start, end]。マップ/トレンドいずれかを
// ダブルクリックでズームリセットした際に、この範囲へ戻すために保持する
let currentFullRange = null;

const el = (id) => document.getElementById(id);

function toLocalInputValue(date) {
  const pad = (n) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

// Dateオブジェクトをタイムゾーン情報のないローカル時刻の文字列にする(toISOString()は
// UTCに変換してしまい、PlotlyがそれをUTCとして解釈して9時間ズレて表示されるため使わない。
// APIから返ってくる発生時刻もタイムゾーン情報のないローカル時刻文字列なので、
// Plotlyに渡すすべての日時をこの形式で統一する)
function toLocalISOString(date) {
  const pad = (n, len = 2) => String(n).padStart(len, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
    + `T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}.${pad(date.getMilliseconds(), 3)}`;
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

function referenceMapElementCheckboxesHTML() {
  // LOBB位置・失透: PIの欠点種類ではなく、マップの表示/非表示だけを切り替える参照要素。
  // data-kind="reference" で実際の欠点種類と区別する
  return REFERENCE_MAP_ELEMENTS.map(({ label, color }) => `
    <label>
      <input type="checkbox" value="${label}" checked data-color="${color}" data-kind="reference">
      <span class="color-swatch" style="background:${color}"></span>
      ${label}
    </label>
  `).join('');
}

async function loadDefectTypes() {
  const container = el('defectTypeList');
  try {
    const { defect_types } = await fetchJSON('/api/defect_types');
    const defectTypeHTML = defect_types.map((t, i) => `
      <label>
        <input type="checkbox" value="${t}" checked data-color="${PALETTE[i % PALETTE.length]}">
        <span class="color-swatch" style="background:${PALETTE[i % PALETTE.length]}"></span>
        ${t}
      </label>
    `).join('');
    container.innerHTML = defectTypeHTML + referenceMapElementCheckboxesHTML();
  } catch (e) {
    // 欠点種類の取得に失敗しても、LOBB位置・失透のチェックボックスは表示する
    container.innerHTML = referenceMapElementCheckboxesHTML();
    showError(e.message);
  }
}

function getSelectedTypes() {
  // LOBB位置・失透(data-kind="reference")はPIの欠点種類ではないため、
  // /api/defectsへのtypeフィルターや欠点マップ/トレンドの種類別トレース生成には含めない
  return Array.from(document.querySelectorAll('#defectTypeList input:checked:not([data-kind="reference"])'))
    .map((c) => c.value);
}

function isReferenceMapElementSelected(label) {
  const checkbox = document.querySelector(`#defectTypeList input[data-kind="reference"][value="${label}"]`);
  return checkbox ? checkbox.checked : false;
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
    // r(右余白)は呼び出し側(applyFilter)がcomputeRightMargin()で活性化中の
    // 重ね描画系列数から計算し、両チャートに同じ値を明示指定して上書きする
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

    x.push(toLocalISOString(new Date(startMs)), toLocalISOString(new Date(endMs)), null);
    y.push(r.position, r.position, null);
    customdata.push(label, label, null);
  });

  return { x, y, customdata };
}

function renderDefectMap(defects, productPos, devitrification, lobbPoints, types, range, margin, showLobb, showDevitrification, tickConfig) {
  const colors = typeColorMap();

  const traces = types.map((t) => {
    const rows = defects.filter((d) => d.defect_type === t);
    const seg = buildDurationSegments(rows);
    return {
      x: seg.x,
      y: seg.y,
      customdata: seg.customdata,
      mode: 'lines+markers',
      type: 'scattergl',
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
    mode: 'lines', type: 'scattergl', name: 'Gross幅', legendgroup: 'gross',
    line: { color: GROSS_COLOR, width: 1 },
    hovertemplate: `<b>Gross終了位置</b><br>%{x|${TIME_TICKFORMAT}}<br>位置: %{y:.1f}<extra></extra>`,
  });
  traces.push({
    x: productPos.map((p) => p.timestamp),
    y: productPos.map((p) => p.gross_start),
    mode: 'lines', type: 'scattergl', name: 'Gross幅', legendgroup: 'gross',
    line: { color: GROSS_COLOR, width: 1 }, showlegend: false,
    hovertemplate: `<b>Gross開始位置</b><br>%{x|${TIME_TICKFORMAT}}<br>位置: %{y:.1f}<extra></extra>`,
  });
  traces.push({
    x: productPos.map((p) => p.timestamp),
    y: productPos.map((p) => p.net_end),
    mode: 'lines', type: 'scattergl', name: 'Net幅', legendgroup: 'net',
    line: { color: NET_COLOR, width: 1.3, dash: 'dot' },
    hovertemplate: `<b>Net終了位置</b><br>%{x|${TIME_TICKFORMAT}}<br>位置: %{y:.1f}<extra></extra>`,
  });
  traces.push({
    x: productPos.map((p) => p.timestamp),
    y: productPos.map((p) => p.net_start),
    mode: 'lines', type: 'scattergl', name: 'Net幅', legendgroup: 'net',
    line: { color: NET_COLOR, width: 1.3, dash: 'dot' }, showlegend: false,
    hovertemplate: `<b>Net開始位置</b><br>%{x|${TIME_TICKFORMAT}}<br>位置: %{y:.1f}<extra></extra>`,
  });

  // LOBB・失透(いずれも点、L側/R側を区別しない失透は1系列にまとめている)は、左パネルの
  // 「スナップ・欠点種類」リストのチェック状態(showLobb/showDevitrification)で
  // 表示/非表示を切り替える(Gross/Netと違い常時表示ではない)。
  // どちらもGross/Netのように連続サンプリングされる値ではなく、実機確認では
  // 非常にまばらなデータのため、線ではなく点として独立に取得・描画する
  if (showLobb) {
    traces.push({
      x: lobbPoints.map((p) => p.timestamp),
      y: lobbPoints.map((p) => p.position),
      mode: 'markers', type: 'scattergl', name: 'LOBB',
      marker: { color: LOBB_COLOR, size: 7 },
      hovertemplate: `<b>LOBB</b><br>%{x|${TIME_TICKFORMAT}}<br>位置: %{y:.1f}<extra></extra>`,
    });
  }
  if (showDevitrification) {
    traces.push({
      x: devitrification.map((d) => d.timestamp),
      y: devitrification.map((d) => d.position),
      mode: 'markers', type: 'scattergl', name: '失透',
      marker: { color: DEVITRIFICATION_COLOR, size: 6 },
      hovertemplate: `<b>失透</b><br>%{x|${TIME_TICKFORMAT}}<br>位置: %{y:.1f}<extra></extra>`,
    });
  }

  const posMax = window.POSITION_MAX || 210;
  return Plotly.react('defectMap', traces, baseLayout({
    margin,
    xaxis: {
      tickformat: TIME_TICKFORMAT, dtick: tickConfig.dtick, tick0: tickConfig.tick0, range,
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
    const hourKey = toLocalISOString(dt);
    const typeMap = buckets[hourKey] || (buckets[hourKey] = {});
    const minutes = d.duration_minutes || 0;
    typeMap[d.defect_type] = (typeMap[d.defect_type] || 0) + minutes;
  });

  return { hours: Object.keys(buckets).sort(), buckets };
}

// Plotlyは棒の幅をデータ点同士の間隔から自動推定するため、表示期間が短く
// バーの本数が少ないと「1時間」から幅がズレて見える。明示的に1時間分で固定する。
const ONE_HOUR_MS = 60 * 60 * 1000;

function renderTrend(defects, types, range, activeSeries, seriesData, recalcAxisRange, rightMargin, tickConfig) {
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

  const overlayYaxis = {};
  activeSeries.forEach((s, i) => {
    const values = seriesData[s.key].map((d) => d.value);

    // 軸レンジは「適用」操作時のみ再計算し、リアルタイム更新中(recalcAxisRange=false)は
    // 前回の確定値を使い回す。データが空の回は前回値をそのまま維持する
    if (recalcAxisRange) {
      overlayAxisRanges[s.key] = roundedAxisRange(values, s.pad, s.capMax) || overlayAxisRanges[s.key];
    }

    const axisNum = i + 2; // 主軸(発生分数)がy1なので、重ね系列はy2から
    traces.push({
      x: seriesData[s.key].map((d) => d.timestamp),
      y: seriesData[s.key].map((d) => d.value),
      type: 'scattergl',
      mode: 'lines',
      name: s.label,
      yaxis: `y${axisNum}`,
      line: { color: s.color, width: 2, dash: s.dash },
      hovertemplate: `<b>${s.label}</b><br>%{x|${TIME_TICKFORMAT}}<br>%{y:${s.valueFormat}} ${s.unit}<extra></extra>`,
    });

    overlayYaxis[`yaxis${axisNum}`] = {
      title: `${s.label} (${s.unit})`,
      overlaying: 'y',
      side: 'right',
      range: overlayAxisRanges[s.key] || undefined,
      showgrid: false, zeroline: false, color: s.color,
      // 2本目以降の追加軸はプロット領域の外側へ自動でずらして重なりを防ぐ
      ...(i > 0 ? { anchor: 'free', autoshift: true } : {}),
    };
  });

  return Plotly.react('trendChart', traces, baseLayout({
    barmode: 'stack',
    margin: { l: 50, r: rightMargin, t: 10, b: 40 },
    // 重ね描画系列(CST回転数・厚み・絶対真空圧など)の凡例は、Plotly側ではなく
    // タイトル横のカスタム凡例(updateTrendLegend)で表示するため、ここでは非表示にする
    showlegend: false,
    // 上段の欠点マップとX軸(時間)の目盛り位置がずれないよう、同じ表示範囲・同じdtickを明示指定する
    xaxis: {
      tickformat: TIME_TICKFORMAT, dtick: tickConfig.dtick, tick0: tickConfig.tick0, range,
      gridcolor: COLORS.grid, zerolinecolor: COLORS.grid, color: COLORS.muted,
    },
    yaxis: { title: '発生分数 (分/時間)', gridcolor: COLORS.grid, color: COLORS.muted },
    ...overlayYaxis,
  }), { responsive: true, displayModeBar: false });
}

// スナップ(欠点)の発生分数トレンドとは内容が全く異なるため、既存のトレンドに重ねず
// グラフを丸ごと切り替えて表示する(左パネル上部のタブで切り替え)
function renderLobbTrend(lobbHourlyCount, range, rightMargin, tickConfig) {
  const trace = {
    x: lobbHourlyCount.map((d) => d.hour),
    y: lobbHourlyCount.map((d) => d.count),
    type: 'bar',
    width: ONE_HOUR_MS,
    name: 'LOBB発生個数',
    marker: { color: LOBB_COLOR },
    hovertemplate: `<b>LOBB</b><br>%{x|${TIME_TICKFORMAT}}<br>発生個数: %{y}件<extra></extra>`,
  };

  return Plotly.react('trendChart', [trace], baseLayout({
    margin: { l: 50, r: rightMargin, t: 10, b: 40 },
    showlegend: false,
    // 上段の欠点マップとX軸(時間)の目盛り位置がずれないよう、同じ表示範囲・同じdtickを明示指定する
    xaxis: {
      tickformat: TIME_TICKFORMAT, dtick: tickConfig.dtick, tick0: tickConfig.tick0, range,
      gridcolor: COLORS.grid, zerolinecolor: COLORS.grid, color: COLORS.muted,
    },
    yaxis: { title: '発生個数 (件/時間)', gridcolor: COLORS.grid, color: COLORS.muted },
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
  const range = [toLocalISOString(sliderStepToDate(lo)), toLocalISOString(sliderStepToDate(hi))];
  // このスライダー操作自体が両チャートを直接同期させるため、setupChartZoomSync()の
  // ドラッグズーム相互追従ハンドラが二重に反応しないようガードする
  isSyncingZoom = true;
  Promise.all([
    Plotly.relayout('defectMap', { 'xaxis.range': range }),
    Plotly.relayout('trendChart', { 'xaxis.range': range }),
  ]).finally(() => { isSyncingZoom = false; });
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

// =========================================================
// マップ⇔トレンドのドラッグズーム相互追従
// 一方のチャートをドラッグでズーム(またはダブルクリックで解除)すると、
// もう一方のチャートのX軸表示範囲も同じ範囲に追従させる(双方向)
// =========================================================
let isSyncingZoom = false;

// Plotlyのrelayoutイベントが返す日時は "YYYY-MM-DD HH:MM:SS.ssss" 形式
// (タイムゾーン情報なしのローカル時刻文字列)のことがあり、そのままでは
// Dateコンストラクタの解釈が環境依存になるため、'T'区切りに正規化してから渡す
function parseAnyDate(v) {
  if (typeof v === 'number') return new Date(v);
  return new Date(String(v).replace(' ', 'T'));
}

function updatePeriodSliderFromRange(range) {
  if (!periodSliderRange) return;
  const { startMs, endMs } = periodSliderRange;
  const totalMs = endMs - startMs;
  if (totalMs <= 0) return;
  const toStep = (v) => {
    const ms = parseAnyDate(v).getTime();
    const clamped = Math.min(Math.max(ms, startMs), endMs);
    return ((clamped - startMs) / totalMs) * PERIOD_SLIDER_STEPS;
  };
  el('periodSliderMin').value = toStep(range[0]);
  el('periodSliderMax').value = toStep(range[1]);
  updatePeriodSliderUI();
}

function setupChartZoomSync() {
  const mapDiv = el('defectMap');
  const trendDiv = el('trendChart');

  function handleRelayout(targetDiv) {
    return (eventData) => {
      if (isSyncingZoom) return;

      let newRange = null;
      if (eventData['xaxis.range[0]'] !== undefined && eventData['xaxis.range[1]'] !== undefined) {
        newRange = [eventData['xaxis.range[0]'], eventData['xaxis.range[1]']];
      } else if (eventData['xaxis.range']) {
        newRange = eventData['xaxis.range'];
      } else if (eventData['xaxis.autorange']) {
        // ダブルクリックでのズーム解除。直前「適用」時点の全期間表示に戻す
        newRange = currentFullRange;
      } else {
        return;
      }
      if (!newRange) return;

      isSyncingZoom = true;
      Plotly.relayout(targetDiv, { 'xaxis.range': newRange }).finally(() => { isSyncingZoom = false; });
      updatePeriodSliderFromRange(newRange);
    };
  }

  mapDiv.on('plotly_relayout', handleRelayout(trendDiv));
  trendDiv.on('plotly_relayout', handleRelayout(mapDiv));
}

async function applyFilter(recalcAxisRange = true) {
  showError(null);
  const startLocal = el('startInput').value;
  const endLocal = el('endInput').value;
  if (!startLocal || !endLocal) {
    showError('開始日時と終了日時を指定してください');
    return;
  }
  // PI側のTimeStamp列はタイムゾーン情報のないJST(ローカル)の生の数値として保存されているため、
  // ここでUTCに変換して送ってしまうと、バックエンドのSQLクエリが実際には9時間早い範囲を
  // 問い合わせることになる(2026-07-22判明。datetime-localの値は元々タイムゾーン情報を
  // 持たないローカル時刻の文字列なので、変換せずそのまま送る)
  const start = startLocal;
  const end = endLocal;
  const types = getSelectedTypes();
  const showLobb = isReferenceMapElementSelected('LOBB');
  const showDevitrification = isReferenceMapElementSelected('失透');

  const btn = el('applyFilter');
  btn.disabled = true;
  btn.textContent = '読み込み中…';
  try {
    const paramsDefects = new URLSearchParams({ start, end });
    types.forEach((t) => paramsDefects.append('type', t));
    const paramsProduct = new URLSearchParams({ start, end });

    // LOBB発生個数トレンド表示中は、既存トレンドの重ね描画系列(CST回転数等)は使わないため取得しない
    const selectedOverlayKeys = getSelectedOverlaySeriesKeys();
    const activeSeries = trendMode === 'defects'
      ? OVERLAY_SERIES.filter((s) => selectedOverlayKeys.includes(s.key))
      : [];

    const fetches = [
      fetchJSON(`/api/defects?${paramsDefects}`),
      fetchJSON(`/api/product_position?${paramsProduct}`),
    ];
    // LOBB・失透はチェックが外れている場合、取得自体をスキップする
    if (showLobb) {
      fetches.push(fetchJSON(`/api/lobb_points?${new URLSearchParams({ start, end })}`));
    }
    if (showDevitrification) {
      fetches.push(fetchJSON(`/api/devitrification_points?${new URLSearchParams({ start, end })}`));
    }
    if (trendMode === 'lobb') {
      fetches.push(fetchJSON(`/api/lobb_hourly_count?${new URLSearchParams({ start, end })}`));
    }
    fetches.push(...activeSeries.map((s) => fetchJSON(`${s.endpoint}?${new URLSearchParams({ start, end })}`)));

    const [{ data: defects }, { data: productPos }, ...rest] = await Promise.all(fetches);

    let i = 0;
    const lobbPoints = showLobb ? rest[i++].data : [];
    const devitrification = showDevitrification ? rest[i++].data : [];
    const lobbHourlyCount = trendMode === 'lobb' ? rest[i++].data : [];
    const overlayResults = rest.slice(i);

    const seriesData = {};
    activeSeries.forEach((s, idx) => { seriesData[s.key] = overlayResults[idx].data; });

    const range = [start, end];
    currentFullRange = range;
    const tickConfig = computeTimeAxisTicks(start, end);
    const rightMargin = computeRightMargin(activeSeries.length);
    updateTrendLegend(activeSeries);
    // トレンド側の右軸(CST回転数・厚み・絶対真空圧)はPlotlyのautoshiftで自動配置されるため、
    // 指定したmargin.rの通りに描画されるとは限らない。先にトレンドを描画し、実際に確定した
    // 余白(_fullLayout.margin)を読み取ってスナップマップ側にそのまま適用することで、
    // 2つの独立したチャート間でもプロット領域の幅を厳密に一致させ、X軸(時刻)の
    // 縦方向のズレを防ぐ
    if (trendMode === 'lobb') {
      await renderLobbTrend(lobbHourlyCount, range, rightMargin, tickConfig);
    } else {
      await renderTrend(defects, types, range, activeSeries, seriesData, recalcAxisRange, rightMargin, tickConfig);
    }
    const resolvedMargin = el('trendChart')._fullLayout.margin;
    renderDefectMap(
      defects, productPos, devitrification, lobbPoints, types, range, resolvedMargin,
      showLobb, showDevitrification, tickConfig,
    );
    resetPeriodSlider(new Date(start).getTime(), new Date(end).getTime());

    el('lastUpdated').textContent = `最終更新 ${new Date().toLocaleTimeString('ja-JP')}`;
  } catch (e) {
    showError(e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = '適用';
  }
}

// リアルタイム更新のポーリング間隔
const LIVE_UPDATE_INTERVAL_MS = 5 * 60 * 1000; // 5分

function startLiveUpdates() {
  if (liveTimer) return;
  liveTimer = setInterval(() => {
    el('endInput').value = toLocalInputValue(new Date());
    // リアルタイム更新中はデータのみ更新し、CST回転数・厚みの軸レンジは
    // 直前の「適用」操作時点の値のまま固定する(ユーザー指示)
    applyFilter(false);
  }, LIVE_UPDATE_INTERVAL_MS);
}

function stopLiveUpdates() {
  clearInterval(liveTimer);
  liveTimer = null;
}

function setupLiveToggle() {
  el('liveToggle').addEventListener('change', (e) => {
    if (e.target.checked) {
      startLiveUpdates();
    } else {
      stopLiveUpdates();
    }
  });
}

function updateTrendTabsUI() {
  el('trendTabDefects').classList.toggle('active', trendMode === 'defects');
  el('trendTabLobb').classList.toggle('active', trendMode === 'lobb');
}

function setupTrendTabs() {
  el('trendTabDefects').addEventListener('click', () => {
    if (trendMode === 'defects') return;
    trendMode = 'defects';
    updateTrendTabsUI();
    applyFilter(true);
  });
  el('trendTabLobb').addEventListener('click', () => {
    if (trendMode === 'lobb') return;
    trendMode = 'lobb';
    updateTrendTabsUI();
    applyFilter(true);
  });
}

async function init() {
  setDefaultRange(24 * 3); // 初期表示は現在時刻から3日前まで
  await loadDefectTypes();
  renderOverlaySeriesCheckboxes();
  el('applyFilter').addEventListener('click', () => applyFilter(true));
  setupLiveToggle();
  setupPeriodSlider();
  setupTypeSelectButtons();
  setupTrendTabs();
  await applyFilter();
  setupChartZoomSync();
  // リアルタイム更新はデフォルトON(index.htmlのliveToggleにchecked指定)。
  // HTMLのchecked属性だけではchangeイベントが発火しないため、ここで明示的に開始する
  if (el('liveToggle').checked) {
    startLiveUpdates();
  }
}

document.addEventListener('DOMContentLoaded', init);
