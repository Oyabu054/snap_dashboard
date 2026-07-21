# -*- coding: utf-8 -*-
"""
PI からの欠点データ / 製品位置データ取得モジュール
====================================================

PI AFへは、pymssqlでSQL Serverに接続し、リンクサーバー経由の OPENQUERY で
PIの内部テーブル(Master.Element.ElementHierarchy / Attribute / Archive)を
直接SQLで取得する方式を採用しています(PIconnect/AF SDKがWindows統合認証
のみにしか対応しておらず、技術アカウントでの接続ができなかったため)。

前提(実際のAF構造に合わせてconfig.txtを調整してください):
  config.AF_HIERARCHY_PATH 配下の config.AF_ELEMENT_NAME 要素の直下に、
  欠点1件ごとに以下4つの属性が同時刻(または近接した時刻)で記録されている
  想定です。
    - ATTR_START_TIME    : 発生時刻
    - ATTR_DURATION      : 継続発生時間
    - ATTR_POSITION      : 発生位置(0〜POSITION_MAX、大きいほど左側)
    - ATTR_DEFECT_TYPE   : 欠点の種類

  config.AF_PRODUCT_ELEMENT_NAME の要素には、常時表示する製品(ガラスリボン)
  の内側・外側エッジ位置が連続的な時系列として記録されている想定です。
  AFフォルダ階層(eh.Path)は欠点データ・製品位置データで共通です。
"""
from datetime import datetime, timedelta

import pandas as pd
import pymssql

import config


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
    sql = _build_sql(config.AF_HIERARCHY_PATH, element_name, start_dt, end_dt)

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
    df_raw = _fetch_element_raw(config.AF_ELEMENT_NAME, start, end)
    if df_raw.empty:
        return pd.DataFrame(columns=["timestamp", "position", "duration_minutes", "defect_type"])

    pos_series = _attribute_series(df_raw, config.ATTR_POSITION, numeric=True)
    type_series = _attribute_series(df_raw, config.ATTR_DEFECT_TYPE, numeric=False)
    duration_series = _attribute_series(df_raw, config.ATTR_DURATION, numeric=True)
    start_time_series = _attribute_series(df_raw, config.ATTR_START_TIME, numeric=False)

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

    df_raw = _fetch_element_raw(config.AF_ELEMENT_NAME, start_dt, end_dt)
    if df_raw.empty:
        return []

    recent = _attribute_series(df_raw, config.ATTR_DEFECT_TYPE, numeric=False)
    if recent.empty:
        return []
    return sorted(set(recent.values.tolist()))


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
    df_raw = _fetch_element_raw(config.AF_PRODUCT_ELEMENT_NAME, start, end)
    if df_raw.empty:
        return pd.DataFrame(columns=["timestamp", "gross_start", "gross_end", "net_start", "net_end"])

    gross_start_series = _attribute_series(df_raw, config.ATTR_PRODUCT_GROSS_START, numeric=True)
    gross_end_series = _attribute_series(df_raw, config.ATTR_PRODUCT_GROSS_END, numeric=True)
    net_start_series = _attribute_series(df_raw, config.ATTR_PRODUCT_NET_START, numeric=True)
    net_end_series = _attribute_series(df_raw, config.ATTR_PRODUCT_NET_END, numeric=True)

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
