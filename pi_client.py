# -*- coding: utf-8 -*-
"""
PI からの欠点データ / 製品位置データ取得モジュール
====================================================

PI AFへは、pymssqlでSQL Serverに接続し、リンクサーバー経由の OPENQUERY で
PIの内部テーブル(Master.Element.ElementHierarchy / Attribute / Archive)を
直接SQLで取得する方式を採用しています(PIconnect/AF SDKがWindows統合認証
のみにしか対応しておらず、技術アカウントでの接続ができなかったため)。

AFフォルダ階層・要素名・属性名はPI System Explorerで確認済みのため、
config.txtではなくこのファイルに直接定数として持たせている
(環境依存の接続情報(SQL Server/リンクサーバー)のみconfig.txtで管理)。

  \\T183PIAKPA1\aichi_2fl\01. PI Data\010. 生産(未修)\スナップ 要素の直下に、
  欠点1件ごとに以下4つの属性が同時刻(または近接した時刻)で記録されている。
    - ATTR_START_TIME    : 発生時刻(スナップクリア操作適用年月日)
    - ATTR_DURATION      : 継続発生時間
    - ATTR_POSITION      : 発生位置(0〜POSITION_MAX、大きいほど左側)
    - ATTR_DEFECT_TYPE   : 欠点の種類

  同じ「スナップ」要素に、常時表示する製品(ガラスリボン)のGross/Net幅
  (開始・終了位置、計4属性)も記録されている。
"""
from datetime import datetime, timedelta

import pandas as pd
import pymssql

import config

# ---------------------------------------------------------------
# AFフォルダ階層・要素名・属性名(PI System Explorerで確認済み、2026-07-21)
# \\T183PIAKPA1\aichi_2fl\01. PI Data\010. 生産(未修)\スナップ
# ---------------------------------------------------------------
AF_HIERARCHY_PATH = "\\01. PI Data\\010. 生産(未修)\\"
AF_ELEMENT_NAME = "スナップ"

ATTR_START_TIME = "スナップクリア操作適用年月日"
ATTR_DURATION = "スナップ継続時間"
ATTR_POSITION = "スナップ入力開始幅方向位置"
ATTR_DEFECT_TYPE = "スナップ入力欠点種類"

# 製品位置データも欠点データと同じ要素に記録されている
AF_PRODUCT_ELEMENT_NAME = AF_ELEMENT_NAME
ATTR_PRODUCT_GROSS_START = "グロス開始位置"
ATTR_PRODUCT_GROSS_END = "グロス終了位置"
ATTR_PRODUCT_NET_START = "ネット開始位置"
ATTR_PRODUCT_NET_END = "ネット終了位置"

# CST回転数・厚みも同じ要素に記録されている(2026-07-21 AF階層に追加)
ATTR_CST_ROTATION = "CST回転数"
ATTR_THICKNESS = "厚み"

# ATTR_DEFECT_TYPEの値のうち、実際の欠点(スナップ)ではないため常に除外する種類
# (ユーザー指示、2026-07-21)。defect_typesフィルターの指定有無によらず除外する。
EXCLUDED_DEFECT_TYPES = {"NET切れ", "RIP", "その他", "不明"}


def _connect():
    return pymssql.connect(
        server=config.SQL_HOST,
        user=config.SQL_USER,
        password=config.SQL_PASSWORD,
        database=config.SQL_DATABASE,
    )


def _build_sql(hierarchy_path: str, element_name: str, start_dt, end_dt) -> str:
    """指定AF要素の全属性を取得するOPENQUERY文を組み立てる"""
    start_str = start_dt.strftime("%Y/%m/%d %H:%M:%S")
    end_str = end_dt.strftime("%Y/%m/%d %H:%M:%S")
    # OPENQUERYのパススルー文字列(シングルクォート括り)内のリテラルなので、
    # 値中のシングルクォートは''に二重化してエスケープする
    safe_path = hierarchy_path.replace("'", "''")
    safe_element = element_name.replace("'", "''")

    return f"""
    SELECT * FROM OPENQUERY({config.SQL_LINKED_SERVER},
        'SELECT a.Name Attribute, ar.TimeStamp, ar.Value
         FROM Master.Element.ElementHierarchy eh
         INNER JOIN Master.Element.Attribute a ON a.ElementID = eh.ElementID
         INNER JOIN Master.Element.Archive ar ON ar.AttributeID = a.ID
         WHERE eh.Path = ''{safe_path}''
           AND a.Element = ''{safe_element}''
           AND ar.TimeStamp BETWEEN ''{start_str}'' AND ''{end_str}''
         ORDER BY ar.TimeStamp
        ')
    """


def _fetch_element_raw(element_name: str, start, end) -> pd.DataFrame:
    """
    指定AF要素の全属性の生データを取得する。

    Returns
    -------
    pd.DataFrame[Attribute, TimeStamp, Value]
    """
    start_dt = pd.to_datetime(start)
    end_dt = pd.to_datetime(end)
    sql = _build_sql(AF_HIERARCHY_PATH, element_name, start_dt, end_dt)

    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        return pd.DataFrame(columns=["Attribute", "TimeStamp", "Value"])

    df = pd.DataFrame(rows, columns=["Attribute", "TimeStamp", "Value"])
    df["TimeStamp"] = pd.to_datetime(df["TimeStamp"])
    return df


def _attribute_series(df_raw: pd.DataFrame, attr_name: str, numeric: bool) -> pd.Series:
    """
    ロング形式の生データから指定属性のみを、TimeStamp昇順のSeriesとして抽出する。
    DefectType等の非数値属性はnumeric=Falseで文字列のまま保持する。
    """
    sub = df_raw[df_raw["Attribute"] == attr_name].sort_values("TimeStamp")
    values = pd.to_numeric(sub["Value"], errors="coerce") if numeric else sub["Value"]
    return pd.Series(values.values, index=pd.DatetimeIndex(sub["TimeStamp"]))


def _drop_zero_outliers(series: pd.Series) -> pd.Series:
    """
    製品位置(Gross/Net)センサーのハンチング(瞬間的に0を記録する異常値)を除外する。
    0は正常な位置として扱わず、欠測として扱う。
    """
    return series[series != 0]


def _duration_to_minutes(series: pd.Series) -> pd.Series:
    """ATTR_DURATIONの値を分単位に変換する"""
    values = pd.to_numeric(series, errors="coerce")
    unit = config.DURATION_UNIT
    if unit == "seconds":
        return values / 60.0
    if unit == "milliseconds":
        return values / 60000.0
    if unit == "minutes":
        return values
    raise ValueError(f"未対応のDURATION_UNITです: {unit}")


def _parse_start_time(value):
    """
    ATTR_START_TIMEの値をdatetimeとして解釈できればそれを返す。
    解釈できない場合はNoneを返し、呼び出し側でPIタイムスタンプにフォールバックする。
    """
    try:
        parsed = pd.to_datetime(value)
        if pd.isna(parsed):
            return None
        return parsed
    except (TypeError, ValueError):
        return None


def _merge_on_nearest(base_df: pd.DataFrame, series: pd.Series, colname: str) -> pd.DataFrame:
    other = pd.DataFrame({"pi_timestamp": series.index, colname: series.values}).sort_values("pi_timestamp")
    return pd.merge_asof(
        base_df, other, on="pi_timestamp", direction="nearest",
        tolerance=pd.Timedelta(config.TIMESTAMP_MATCH_TOLERANCE),
    )


def get_defects(start, end, defect_types=None) -> pd.DataFrame:
    """
    指定期間の欠点データを取得する。

    Returns
    -------
    pd.DataFrame[timestamp, position, duration_minutes, defect_type]
        timestamp列は「発生時刻」属性の値を優先し、解釈できない場合は
        Position属性が記録されたPIタイムスタンプを使用します。
    """
    df_raw = _fetch_element_raw(AF_ELEMENT_NAME, start, end)
    if df_raw.empty:
        return pd.DataFrame(columns=["timestamp", "position", "duration_minutes", "defect_type"])

    pos_series = _attribute_series(df_raw, ATTR_POSITION, numeric=True)
    type_series = _attribute_series(df_raw, ATTR_DEFECT_TYPE, numeric=False)
    duration_series = _attribute_series(df_raw, ATTR_DURATION, numeric=True)
    start_time_series = _attribute_series(df_raw, ATTR_START_TIME, numeric=False)

    if pos_series.empty:
        return pd.DataFrame(columns=["timestamp", "position", "duration_minutes", "defect_type"])

    df = pd.DataFrame({"pi_timestamp": pos_series.index, "position": pos_series.values}).sort_values("pi_timestamp")
    df = _merge_on_nearest(df, type_series, "defect_type")
    df = _merge_on_nearest(df, duration_series, "duration_raw")
    df = _merge_on_nearest(df, start_time_series, "start_time_raw")

    df["duration_minutes"] = _duration_to_minutes(df["duration_raw"])

    parsed_start = df["start_time_raw"].apply(_parse_start_time)
    df["timestamp"] = parsed_start.fillna(df["pi_timestamp"])

    df = df[["timestamp", "position", "duration_minutes", "defect_type"]]
    df = df[~df["defect_type"].isin(EXCLUDED_DEFECT_TYPES)]

    if defect_types:
        df = df[df["defect_type"].isin(defect_types)]

    return df.sort_values("timestamp").reset_index(drop=True)


def get_hourly_trend(start, end, defect_types=None) -> pd.DataFrame:
    """
    1時間ごとの欠点「発生分数」(継続発生時間の合計・分)と件数を集計する。

    簡略化のため、継続時間はすべて発生時刻(timestamp)が属する
    1時間バケットに計上しています。1時間を跨ぐ長時間の欠点を按分したい
    場合はここを調整してください。
    """
    df = get_defects(start, end, defect_types)
    if df.empty:
        return pd.DataFrame(columns=["hour", "occurrence_minutes", "count"])

    df = df.set_index("timestamp")
    hourly = df.resample("1h").agg(
        occurrence_minutes=("duration_minutes", "sum"),
        count=("position", "size"),
    ).reset_index()
    hourly.rename(columns={"timestamp": "hour"}, inplace=True)
    return hourly


def get_available_defect_types():
    """フィルターパネルに表示する欠点種類の一覧を取得する"""
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=config.DEFECT_TYPE_LOOKBACK_DAYS)

    df_raw = _fetch_element_raw(AF_ELEMENT_NAME, start_dt, end_dt)
    if df_raw.empty:
        return []

    recent = _attribute_series(df_raw, ATTR_DEFECT_TYPE, numeric=False)
    if recent.empty:
        return []
    return sorted(set(recent.values.tolist()) - EXCLUDED_DEFECT_TYPES)


def get_product_position(start, end) -> pd.DataFrame:
    """
    製品位置(Gross幅・Net幅それぞれの開始・終了位置)を時系列で取得する。
    常時表示用のため、欠点種類フィルターの影響を受けない。

    位置の大小関係(値が大きいほど左側):
        gross_end > net_end > net_start > gross_start

    Returns
    -------
    pd.DataFrame[timestamp, gross_start, gross_end, net_start, net_end]
    """
    df_raw = _fetch_element_raw(AF_PRODUCT_ELEMENT_NAME, start, end)
    if df_raw.empty:
        return pd.DataFrame(columns=["timestamp", "gross_start", "gross_end", "net_start", "net_end"])

    gross_start_series = _drop_zero_outliers(_attribute_series(df_raw, ATTR_PRODUCT_GROSS_START, numeric=True))
    gross_end_series = _drop_zero_outliers(_attribute_series(df_raw, ATTR_PRODUCT_GROSS_END, numeric=True))
    net_start_series = _drop_zero_outliers(_attribute_series(df_raw, ATTR_PRODUCT_NET_START, numeric=True))
    net_end_series = _drop_zero_outliers(_attribute_series(df_raw, ATTR_PRODUCT_NET_END, numeric=True))

    if gross_start_series.empty:
        return pd.DataFrame(columns=["timestamp", "gross_start", "gross_end", "net_start", "net_end"])

    df = pd.DataFrame({
        "pi_timestamp": gross_start_series.index, "gross_start": gross_start_series.values,
    }).sort_values("pi_timestamp")
    df = _merge_on_nearest(df, gross_end_series, "gross_end")
    df = _merge_on_nearest(df, net_start_series, "net_start")
    df = _merge_on_nearest(df, net_end_series, "net_end")
    df.rename(columns={"pi_timestamp": "timestamp"}, inplace=True)
    return df


def get_cst_rotation_trend(start, end) -> pd.DataFrame:
    """
    CST回転数(rpm)を10分平均で取得する。時間帯別トレンドグラフに重ねて表示するための系列。

    Returns
    -------
    pd.DataFrame[timestamp, value]
    """
    df_raw = _fetch_element_raw(AF_ELEMENT_NAME, start, end)
    if df_raw.empty:
        return pd.DataFrame(columns=["timestamp", "value"])

    series = _attribute_series(df_raw, ATTR_CST_ROTATION, numeric=True)
    if series.empty:
        return pd.DataFrame(columns=["timestamp", "value"])

    resampled = series.resample("10min").mean().dropna()
    return pd.DataFrame({"timestamp": resampled.index, "value": resampled.values})


def get_thickness_trend(start, end) -> pd.DataFrame:
    """
    厚み(mm)を生データのまま取得する。時間帯別トレンドグラフに重ねて表示するための系列。

    Returns
    -------
    pd.DataFrame[timestamp, value]
    """
    df_raw = _fetch_element_raw(AF_ELEMENT_NAME, start, end)
    if df_raw.empty:
        return pd.DataFrame(columns=["timestamp", "value"])

    series = _attribute_series(df_raw, ATTR_THICKNESS, numeric=True)
    if series.empty:
        return pd.DataFrame(columns=["timestamp", "value"])

    return pd.DataFrame({"timestamp": series.index, "value": series.values})
