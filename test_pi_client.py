# -*- coding: utf-8 -*-
from datetime import datetime

import pandas as pd
import pytest

import config
import pi_client


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows
        self.executed_sql = None

    def execute(self, sql):
        self.executed_sql = sql

    def fetchall(self):
        return self._rows


class _FakeConnection:
    def __init__(self, rows):
        self.cursor_obj = _FakeCursor(rows)
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def _configure(monkeypatch):
    # SQL接続・集計まわりはconfig.txt由来の値
    monkeypatch.setattr(config, "SQL_LINKED_SERVER", "test_linked_server")
    monkeypatch.setattr(config, "DURATION_UNIT", "seconds")
    monkeypatch.setattr(config, "TIMESTAMP_MATCH_TOLERANCE", "2s")
    monkeypatch.setattr(config, "DEFECT_TYPE_LOOKBACK_DAYS", 90)

    # AFフォルダ階層・要素名・属性名はpi_client.pyにハードコードされているため、
    # テストではpi_client側の定数をモックする
    monkeypatch.setattr(pi_client, "AF_HIERARCHY_PATH", "\\03. Test\\")
    monkeypatch.setattr(pi_client, "AF_ELEMENT_NAME", "DefectDetection")
    monkeypatch.setattr(pi_client, "ATTR_START_TIME", "StartTime")
    monkeypatch.setattr(pi_client, "ATTR_DURATION", "Duration")
    monkeypatch.setattr(pi_client, "ATTR_POSITION", "Position")
    monkeypatch.setattr(pi_client, "ATTR_DEFECT_TYPE", "DefectType")
    monkeypatch.setattr(pi_client, "AF_PRODUCT_ELEMENT_NAME", "ProductEdge")
    monkeypatch.setattr(pi_client, "ATTR_PRODUCT_GROSS_START", "GrossStart")
    monkeypatch.setattr(pi_client, "ATTR_PRODUCT_GROSS_END", "GrossEnd")
    monkeypatch.setattr(pi_client, "ATTR_PRODUCT_NET_START", "NetStart")
    monkeypatch.setattr(pi_client, "ATTR_PRODUCT_NET_END", "NetEnd")
    monkeypatch.setattr(pi_client, "ATTR_CST_ROTATION", "CstRotation")
    monkeypatch.setattr(pi_client, "ATTR_THICKNESS", "Thickness")
    monkeypatch.setattr(pi_client, "ATTR_VACUUM_PRESSURE", "VacuumPressure")
    monkeypatch.setattr(pi_client, "ATTR_LOBB_POSITION", "LobbPosition")
    monkeypatch.setattr(pi_client, "ATTR_DEVITRIFICATION_L", "DevitL")
    monkeypatch.setattr(pi_client, "ATTR_DEVITRIFICATION_R", "DevitR")

    # _fetch_element_raw()の短時間キャッシュがテスト間で汚染しないよう、毎回クリアする
    pi_client._raw_cache.clear()


# ===================== _build_sql =====================

def test_build_sql_includes_path_element_and_time_range():
    sql = pi_client._build_sql(
        "\\03. Test\\", "DefectDetection",
        datetime(2026, 3, 1, 0, 0, 0), datetime(2026, 3, 2, 0, 0, 0),
    )
    assert "eh.Path = ''\\03. Test\\''" in sql
    assert "a.Element = ''DefectDetection''" in sql
    assert "2026/03/01 00:00:00" in sql
    assert "2026/03/02 00:00:00" in sql


def test_build_sql_escapes_single_quotes():
    sql = pi_client._build_sql(
        "path\\o'brien\\", "el'em",
        datetime(2026, 1, 1), datetime(2026, 1, 2),
    )
    assert "o''brien" in sql
    assert "el''em" in sql


def test_build_sql_filters_by_attribute_names_when_provided():
    sql = pi_client._build_sql(
        "\\03. Test\\", "DefectDetection",
        datetime(2026, 3, 1), datetime(2026, 3, 2),
        attribute_names=["Position", "O'Brien"],
    )
    assert "a.Name IN (''Position'', ''O''Brien'')" in sql


def test_build_sql_omits_attribute_filter_when_not_provided():
    sql = pi_client._build_sql(
        "\\03. Test\\", "DefectDetection",
        datetime(2026, 3, 1), datetime(2026, 3, 2),
    )
    assert "a.Name IN" not in sql


# ===================== _fetch_element_raw =====================

def test_fetch_element_raw_returns_dataframe(monkeypatch):
    rows = [
        ("Position", "2026-03-10 08:00:00", "10.5"),
        ("DefectType", "2026-03-10 08:00:01", "Bubble"),
    ]
    fake_conn = _FakeConnection(rows)
    monkeypatch.setattr(pi_client.pymssql, "connect", lambda **kwargs: fake_conn)

    df = pi_client._fetch_element_raw(
        "DefectDetection", "2026-03-10T00:00:00", "2026-03-11T00:00:00"
    )

    assert list(df.columns) == ["Attribute", "TimeStamp", "Value"]
    assert len(df) == 2
    assert fake_conn.closed is True


def test_fetch_element_raw_filters_sql_to_used_attributes_only(monkeypatch):
    fake_conn = _FakeConnection([])
    monkeypatch.setattr(pi_client.pymssql, "connect", lambda **kwargs: fake_conn)

    pi_client._fetch_element_raw(
        "DefectDetection", "2026-03-10T00:00:00", "2026-03-11T00:00:00"
    )

    executed_sql = fake_conn.cursor_obj.executed_sql
    assert "a.Name IN (" in executed_sql
    # _configureフィクスチャでmonkeypatchした属性名(欠点・製品位置・CST回転数等)が
    # 使われていること。要素に残っている「使っていない属性」は絞り込みで除外される想定
    assert "''Position''" in executed_sql
    assert "''DefectType''" in executed_sql
    assert "''CstRotation''" in executed_sql
    assert "''LobbPosition''" in executed_sql


def test_fetch_element_raw_returns_empty_dataframe_when_no_rows(monkeypatch):
    fake_conn = _FakeConnection([])
    monkeypatch.setattr(pi_client.pymssql, "connect", lambda **kwargs: fake_conn)

    df = pi_client._fetch_element_raw(
        "DefectDetection", "2026-03-10T00:00:00", "2026-03-11T00:00:00"
    )

    assert df.empty
    assert list(df.columns) == ["Attribute", "TimeStamp", "Value"]


def test_fetch_element_raw_caches_repeated_calls_with_same_params(monkeypatch):
    # 1回のapplyFilter()で複数のgetterが同じ(element, start, end)を短時間に叩くため、
    # 2回目以降はSQLを再実行せずキャッシュを返す
    call_count = {"n": 0}
    rows = [("Position", "2026-03-10 08:00:00", "10.5")]

    def fake_connect(**kwargs):
        call_count["n"] += 1
        return _FakeConnection(rows)

    monkeypatch.setattr(pi_client.pymssql, "connect", fake_connect)

    pi_client._fetch_element_raw("DefectDetection", "2026-03-10T00:00:00", "2026-03-11T00:00:00")
    pi_client._fetch_element_raw("DefectDetection", "2026-03-10T00:00:00", "2026-03-11T00:00:00")

    assert call_count["n"] == 1


def test_fetch_element_raw_does_not_cache_across_different_params(monkeypatch):
    call_count = {"n": 0}
    rows = [("Position", "2026-03-10 08:00:00", "10.5")]

    def fake_connect(**kwargs):
        call_count["n"] += 1
        return _FakeConnection(rows)

    monkeypatch.setattr(pi_client.pymssql, "connect", fake_connect)

    pi_client._fetch_element_raw("DefectDetection", "2026-03-10T00:00:00", "2026-03-11T00:00:00")
    pi_client._fetch_element_raw("DefectDetection", "2026-03-12T00:00:00", "2026-03-13T00:00:00")

    assert call_count["n"] == 2


def test_fetch_element_raw_refetches_after_ttl_expires(monkeypatch):
    call_count = {"n": 0}
    rows = [("Position", "2026-03-10 08:00:00", "10.5")]

    def fake_connect(**kwargs):
        call_count["n"] += 1
        return _FakeConnection(rows)

    monkeypatch.setattr(pi_client.pymssql, "connect", fake_connect)

    fake_time = {"t": 1000.0}
    monkeypatch.setattr(pi_client.time, "monotonic", lambda: fake_time["t"])

    pi_client._fetch_element_raw("DefectDetection", "2026-03-10T00:00:00", "2026-03-11T00:00:00")
    fake_time["t"] += pi_client._RAW_CACHE_TTL_SECONDS + 1
    pi_client._fetch_element_raw("DefectDetection", "2026-03-10T00:00:00", "2026-03-11T00:00:00")

    assert call_count["n"] == 2


# ===================== _attribute_series =====================

def test_attribute_series_extracts_numeric_values_sorted():
    df_raw = pd.DataFrame({
        "Attribute": ["Position", "DefectType", "Position"],
        "TimeStamp": pd.to_datetime([
            "2026-03-10 08:00:05", "2026-03-10 08:00:00", "2026-03-10 08:00:01",
        ]),
        "Value": ["10.5", "Bubble", "20.0"],
    })

    series = pi_client._attribute_series(df_raw, "Position", numeric=True)

    assert list(series.values) == [20.0, 10.5]
    assert list(series.index) == list(
        pd.to_datetime(["2026-03-10 08:00:01", "2026-03-10 08:00:05"])
    )


def test_attribute_series_keeps_strings_when_not_numeric():
    df_raw = pd.DataFrame({
        "Attribute": ["DefectType"],
        "TimeStamp": pd.to_datetime(["2026-03-10 08:00:00"]),
        "Value": ["Bubble"],
    })

    series = pi_client._attribute_series(df_raw, "DefectType", numeric=False)

    assert series.iloc[0] == "Bubble"


# ===================== get_defects =====================

def test_get_defects_merges_attributes_and_converts_duration(monkeypatch):
    df_raw = pd.DataFrame({
        "Attribute": ["Position", "DefectType", "Duration", "StartTime"],
        "TimeStamp": pd.to_datetime([
            "2026-03-10 08:00:00", "2026-03-10 08:00:00",
            "2026-03-10 08:00:01", "2026-03-10 08:00:00",
        ]),
        "Value": ["100.0", "Bubble", "120", "2026-03-10T08:00:00"],
    })
    monkeypatch.setattr(pi_client, "_fetch_element_raw", lambda element, start, end: df_raw)

    result = pi_client.get_defects("2026-03-10T00:00:00", "2026-03-11T00:00:00")

    assert len(result) == 1
    row = result.iloc[0]
    assert row["position"] == 100.0
    assert row["defect_type"] == "Bubble"
    assert row["duration_minutes"] == 2.0
    assert row["timestamp"] == pd.Timestamp("2026-03-10T08:00:00")


def test_get_defects_falls_back_to_pi_timestamp_when_start_time_unparseable(monkeypatch):
    df_raw = pd.DataFrame({
        "Attribute": ["Position", "DefectType", "Duration", "StartTime"],
        "TimeStamp": pd.to_datetime(["2026-03-10 08:00:00"] * 4),
        "Value": ["100.0", "Bubble", "120", "N/A"],
    })
    monkeypatch.setattr(pi_client, "_fetch_element_raw", lambda element, start, end: df_raw)

    result = pi_client.get_defects("2026-03-10T00:00:00", "2026-03-11T00:00:00")

    assert result.iloc[0]["timestamp"] == pd.Timestamp("2026-03-10 08:00:00")


def test_get_defects_filters_by_defect_types(monkeypatch):
    df_raw = pd.DataFrame({
        "Attribute": [
            "Position", "DefectType", "Position", "DefectType",
            "Duration", "Duration", "StartTime", "StartTime",
        ],
        "TimeStamp": pd.to_datetime([
            "2026-03-10 08:00:00", "2026-03-10 08:00:00",
            "2026-03-10 09:00:00", "2026-03-10 09:00:00",
            "2026-03-10 08:00:00", "2026-03-10 09:00:00",
            "2026-03-10 08:00:00", "2026-03-10 09:00:00",
        ]),
        "Value": [
            "100.0", "Bubble", "50.0", "Scratch",
            "60", "60", "2026-03-10T08:00:00", "2026-03-10T09:00:00",
        ],
    })
    monkeypatch.setattr(pi_client, "_fetch_element_raw", lambda element, start, end: df_raw)

    result = pi_client.get_defects(
        "2026-03-10T00:00:00", "2026-03-11T00:00:00", defect_types=["Bubble"]
    )

    assert list(result["defect_type"]) == ["Bubble"]


def test_get_defects_returns_empty_dataframe_when_no_data(monkeypatch):
    monkeypatch.setattr(
        pi_client, "_fetch_element_raw",
        lambda element, start, end: pd.DataFrame(columns=["Attribute", "TimeStamp", "Value"]),
    )

    result = pi_client.get_defects("2026-03-10T00:00:00", "2026-03-11T00:00:00")

    assert result.empty
    assert list(result.columns) == ["timestamp", "position", "duration_minutes", "defect_type"]


def test_get_defects_excludes_non_defect_types_even_without_filter(monkeypatch):
    # NET切れ/RIP/その他/不明は欠点データではないため、defect_types指定の有無によらず除外する
    attrs = ["Position", "DefectType"] * 5
    timestamps = []
    values = []
    for i, dtype in enumerate(["Bubble", "NET切れ", "RIP", "その他", "不明"]):
        ts = f"2026-03-10 {8 + i:02d}:00:00"
        timestamps += [ts, ts]
        values += [str(10.0 * (i + 1)), dtype]
    df_raw = pd.DataFrame({
        "Attribute": attrs,
        "TimeStamp": pd.to_datetime(timestamps),
        "Value": values,
    })
    monkeypatch.setattr(pi_client, "_fetch_element_raw", lambda element, start, end: df_raw)

    result = pi_client.get_defects("2026-03-10T00:00:00", "2026-03-11T00:00:00")

    assert list(result["defect_type"]) == ["Bubble"]


def test_get_defects_excludes_non_defect_types_even_if_explicitly_requested(monkeypatch):
    df_raw = pd.DataFrame({
        "Attribute": ["Position", "DefectType", "Position", "DefectType"],
        "TimeStamp": pd.to_datetime([
            "2026-03-10 08:00:00", "2026-03-10 08:00:00",
            "2026-03-10 09:00:00", "2026-03-10 09:00:00",
        ]),
        "Value": ["10.0", "Bubble", "20.0", "RIP"],
    })
    monkeypatch.setattr(pi_client, "_fetch_element_raw", lambda element, start, end: df_raw)

    result = pi_client.get_defects(
        "2026-03-10T00:00:00", "2026-03-11T00:00:00", defect_types=["Bubble", "RIP"]
    )

    assert list(result["defect_type"]) == ["Bubble"]


# ===================== get_available_defect_types =====================

def test_get_available_defect_types_returns_sorted_unique(monkeypatch):
    df_raw = pd.DataFrame({
        "Attribute": ["DefectType", "DefectType", "DefectType", "Position"],
        "TimeStamp": pd.to_datetime(["2026-01-01"] * 4),
        "Value": ["Scratch", "Bubble", "Bubble", "1.0"],
    })
    captured = {}

    def fake_fetch(element, start, end):
        captured["element"] = element
        return df_raw

    monkeypatch.setattr(pi_client, "_fetch_element_raw", fake_fetch)

    result = pi_client.get_available_defect_types()

    assert result == ["Bubble", "Scratch"]
    assert captured["element"] == "DefectDetection"


def test_get_available_defect_types_returns_empty_list_when_no_data(monkeypatch):
    monkeypatch.setattr(
        pi_client, "_fetch_element_raw",
        lambda element, start, end: pd.DataFrame(columns=["Attribute", "TimeStamp", "Value"]),
    )

    assert pi_client.get_available_defect_types() == []


def test_get_available_defect_types_excludes_non_defect_types(monkeypatch):
    df_raw = pd.DataFrame({
        "Attribute": ["DefectType"] * 5,
        "TimeStamp": pd.to_datetime(["2026-01-01"] * 5),
        "Value": ["Bubble", "NET切れ", "RIP", "その他", "不明"],
    })
    monkeypatch.setattr(pi_client, "_fetch_element_raw", lambda element, start, end: df_raw)

    result = pi_client.get_available_defect_types()

    assert result == ["Bubble"]


# ===================== get_product_position =====================

def test_get_product_position_merges_four_attributes(monkeypatch):
    df_raw = pd.DataFrame({
        "Attribute": ["GrossStart", "GrossEnd", "NetStart", "NetEnd"],
        "TimeStamp": pd.to_datetime(["2026-03-10 08:00:00"] * 4),
        "Value": ["5.0", "210.0", "10.0", "200.0"],
    })
    monkeypatch.setattr(pi_client, "_fetch_element_raw", lambda element, start, end: df_raw)

    result = pi_client.get_product_position("2026-03-10T00:00:00", "2026-03-11T00:00:00")

    assert len(result) == 1
    row = result.iloc[0]
    assert row["gross_start"] == 5.0
    assert row["gross_end"] == 210.0
    assert row["net_start"] == 10.0
    assert row["net_end"] == 200.0


def test_get_product_position_resamples_gross_net_to_10min_average(monkeypatch):
    # Gross/Netは1分間隔で記録され行数の大半を占めるため、10分平均に間引いて
    # レスポンスサイズ・描画負荷を抑える(2026-07-22追加)
    df_raw = pd.DataFrame({
        "Attribute": [
            "GrossStart", "GrossStart", "GrossEnd", "GrossEnd",
            "NetStart", "NetStart", "NetEnd", "NetEnd",
        ],
        "TimeStamp": pd.to_datetime([
            "2026-03-10 08:00:00", "2026-03-10 08:05:00",
            "2026-03-10 08:00:00", "2026-03-10 08:05:00",
            "2026-03-10 08:00:00", "2026-03-10 08:05:00",
            "2026-03-10 08:00:00", "2026-03-10 08:05:00",
        ]),
        "Value": ["4.0", "6.0", "208.0", "212.0", "9.0", "11.0", "198.0", "202.0"],
    })
    monkeypatch.setattr(pi_client, "_fetch_element_raw", lambda element, start, end: df_raw)

    result = pi_client.get_product_position("2026-03-10T00:00:00", "2026-03-11T00:00:00")

    assert len(result) == 1
    row = result.iloc[0]
    assert row["timestamp"] == pd.Timestamp("2026-03-10 08:00:00")
    assert row["gross_start"] == 5.0
    assert row["gross_end"] == 210.0
    assert row["net_start"] == 10.0
    assert row["net_end"] == 200.0


def test_get_product_position_returns_empty_dataframe_when_no_data(monkeypatch):
    monkeypatch.setattr(
        pi_client, "_fetch_element_raw",
        lambda element, start, end: pd.DataFrame(columns=["Attribute", "TimeStamp", "Value"]),
    )

    result = pi_client.get_product_position("2026-03-10T00:00:00", "2026-03-11T00:00:00")

    assert result.empty


def test_get_product_position_excludes_zero_outliers_on_anchor_attribute(monkeypatch):
    # GrossStartに0(ハンチングによる異常値)が混じっているタイムスタンプは除外される
    df_raw = pd.DataFrame({
        "Attribute": ["GrossStart", "GrossStart", "GrossEnd", "GrossEnd", "NetStart", "NetStart", "NetEnd", "NetEnd"],
        "TimeStamp": pd.to_datetime([
            "2026-03-10 08:00:00", "2026-03-10 09:00:00",
            "2026-03-10 08:00:00", "2026-03-10 09:00:00",
            "2026-03-10 08:00:00", "2026-03-10 09:00:00",
            "2026-03-10 08:00:00", "2026-03-10 09:00:00",
        ]),
        "Value": ["0.0", "5.0", "210.0", "212.0", "10.0", "11.0", "200.0", "202.0"],
    })
    monkeypatch.setattr(pi_client, "_fetch_element_raw", lambda element, start, end: df_raw)

    result = pi_client.get_product_position("2026-03-10T00:00:00", "2026-03-11T00:00:00")

    assert len(result) == 1
    assert result.iloc[0]["gross_start"] == 5.0


def test_get_product_position_excludes_zero_outliers_on_other_attribute(monkeypatch):
    # GrossEndに0(ハンチングによる異常値)が混じっている場合、その時刻ではNaNになり
    # 別時刻の正常値がmerge_asofで拾われる
    df_raw = pd.DataFrame({
        "Attribute": ["GrossStart", "GrossEnd", "GrossEnd", "NetStart", "NetEnd"],
        "TimeStamp": pd.to_datetime([
            "2026-03-10 08:00:00",
            "2026-03-10 08:00:00", "2026-03-10 08:00:01",
            "2026-03-10 08:00:00", "2026-03-10 08:00:00",
        ]),
        "Value": ["5.0", "0.0", "210.0", "10.0", "200.0"],
    })
    monkeypatch.setattr(pi_client, "_fetch_element_raw", lambda element, start, end: df_raw)

    result = pi_client.get_product_position("2026-03-10T00:00:00", "2026-03-11T00:00:00")

    assert len(result) == 1
    assert result.iloc[0]["gross_end"] == 210.0



# ===================== get_hourly_trend =====================

def test_get_hourly_trend_aggregates_occurrence_minutes(monkeypatch):
    df_defects = pd.DataFrame({
        "timestamp": pd.to_datetime([
            "2026-03-10 08:10:00", "2026-03-10 08:40:00", "2026-03-10 09:05:00",
        ]),
        "position": [100.0, 90.0, 80.0],
        "duration_minutes": [5.0, 3.0, 2.0],
        "defect_type": ["Bubble", "Bubble", "Scratch"],
    })
    monkeypatch.setattr(pi_client, "get_defects", lambda start, end, defect_types=None: df_defects)

    result = pi_client.get_hourly_trend("2026-03-10T00:00:00", "2026-03-11T00:00:00")

    assert len(result) == 2
    assert result.iloc[0]["occurrence_minutes"] == 8.0
    assert result.iloc[0]["count"] == 2
    assert result.iloc[1]["occurrence_minutes"] == 2.0


# ===================== get_cst_rotation_trend =====================

def test_get_cst_rotation_trend_resamples_to_10min_average(monkeypatch):
    # 08:00〜08:09の1分間隔10点(値1〜10) → 平均5.5、08:10の1点(値20) → 平均20.0
    timestamps = pd.date_range("2026-03-10 08:00:00", periods=10, freq="1min")
    timestamps = timestamps.append(pd.DatetimeIndex(["2026-03-10 08:10:00"]))
    df_raw = pd.DataFrame({
        "Attribute": ["CstRotation"] * 11,
        "TimeStamp": timestamps,
        "Value": [str(v) for v in list(range(1, 11)) + [20]],
    })
    monkeypatch.setattr(pi_client, "_fetch_element_raw", lambda element, start, end: df_raw)

    result = pi_client.get_cst_rotation_trend("2026-03-10T00:00:00", "2026-03-11T00:00:00")

    assert list(result.columns) == ["timestamp", "value"]
    assert len(result) == 2
    assert result.iloc[0]["timestamp"] == pd.Timestamp("2026-03-10 08:00:00")
    assert result.iloc[0]["value"] == 5.5
    assert result.iloc[1]["timestamp"] == pd.Timestamp("2026-03-10 08:10:00")
    assert result.iloc[1]["value"] == 20.0


def test_get_cst_rotation_trend_returns_empty_dataframe_when_no_data(monkeypatch):
    monkeypatch.setattr(
        pi_client, "_fetch_element_raw",
        lambda element, start, end: pd.DataFrame(columns=["Attribute", "TimeStamp", "Value"]),
    )

    result = pi_client.get_cst_rotation_trend("2026-03-10T00:00:00", "2026-03-11T00:00:00")

    assert result.empty
    assert list(result.columns) == ["timestamp", "value"]


# ===================== get_thickness_trend =====================

def test_get_thickness_trend_returns_raw_values_without_resampling(monkeypatch):
    df_raw = pd.DataFrame({
        "Attribute": ["Thickness", "Thickness"],
        "TimeStamp": pd.to_datetime(["2026-03-10 08:05:00", "2026-03-10 08:00:00"]),
        "Value": ["5.1", "5.0"],
    })
    monkeypatch.setattr(pi_client, "_fetch_element_raw", lambda element, start, end: df_raw)

    result = pi_client.get_thickness_trend("2026-03-10T00:00:00", "2026-03-11T00:00:00")

    assert list(result.columns) == ["timestamp", "value"]
    assert len(result) == 2
    assert list(result["timestamp"]) == list(
        pd.to_datetime(["2026-03-10 08:00:00", "2026-03-10 08:05:00"])
    )
    assert list(result["value"]) == [5.0, 5.1]


def test_get_thickness_trend_returns_empty_dataframe_when_no_data(monkeypatch):
    monkeypatch.setattr(
        pi_client, "_fetch_element_raw",
        lambda element, start, end: pd.DataFrame(columns=["Attribute", "TimeStamp", "Value"]),
    )

    result = pi_client.get_thickness_trend("2026-03-10T00:00:00", "2026-03-11T00:00:00")

    assert result.empty
    assert list(result.columns) == ["timestamp", "value"]


# ===================== get_vacuum_pressure_trend =====================

def test_get_vacuum_pressure_trend_resamples_to_10min_average(monkeypatch):
    timestamps = pd.date_range("2026-03-10 08:00:00", periods=10, freq="1min")
    timestamps = timestamps.append(pd.DatetimeIndex(["2026-03-10 08:10:00"]))
    df_raw = pd.DataFrame({
        "Attribute": ["VacuumPressure"] * 11,
        "TimeStamp": timestamps,
        "Value": [str(v) for v in list(range(700, 710)) + [720]],
    })
    monkeypatch.setattr(pi_client, "_fetch_element_raw", lambda element, start, end: df_raw)

    result = pi_client.get_vacuum_pressure_trend("2026-03-10T00:00:00", "2026-03-11T00:00:00")

    assert list(result.columns) == ["timestamp", "value"]
    assert len(result) == 2
    assert result.iloc[0]["timestamp"] == pd.Timestamp("2026-03-10 08:00:00")
    assert result.iloc[0]["value"] == 704.5
    assert result.iloc[1]["timestamp"] == pd.Timestamp("2026-03-10 08:10:00")
    assert result.iloc[1]["value"] == 720.0


def test_get_vacuum_pressure_trend_returns_empty_dataframe_when_no_data(monkeypatch):
    monkeypatch.setattr(
        pi_client, "_fetch_element_raw",
        lambda element, start, end: pd.DataFrame(columns=["Attribute", "TimeStamp", "Value"]),
    )

    result = pi_client.get_vacuum_pressure_trend("2026-03-10T00:00:00", "2026-03-11T00:00:00")

    assert result.empty
    assert list(result.columns) == ["timestamp", "value"]


# ===================== get_devitrification_points =====================

def test_get_devitrification_points_combines_l_and_r_sides(monkeypatch):
    # L側/R側は区別せず、時刻順に並んだ1系列の点として返す
    df_raw = pd.DataFrame({
        "Attribute": ["DevitL", "DevitR", "DevitL"],
        "TimeStamp": pd.to_datetime([
            "2026-03-10 08:00:00", "2026-03-10 08:05:00", "2026-03-10 08:10:00",
        ]),
        "Value": ["30.0", "40.0", "35.0"],
    })
    monkeypatch.setattr(pi_client, "_fetch_element_raw", lambda element, start, end: df_raw)

    result = pi_client.get_devitrification_points("2026-03-10T00:00:00", "2026-03-11T00:00:00")

    assert list(result.columns) == ["timestamp", "position"]
    assert len(result) == 3
    assert list(result["position"]) == [30.0, 40.0, 35.0]


def test_get_devitrification_points_excludes_zero_outliers(monkeypatch):
    df_raw = pd.DataFrame({
        "Attribute": ["DevitL", "DevitR"],
        "TimeStamp": pd.to_datetime(["2026-03-10 08:00:00", "2026-03-10 08:05:00"]),
        "Value": ["0.0", "40.0"],
    })
    monkeypatch.setattr(pi_client, "_fetch_element_raw", lambda element, start, end: df_raw)

    result = pi_client.get_devitrification_points("2026-03-10T00:00:00", "2026-03-11T00:00:00")

    assert list(result["position"]) == [40.0]


def test_get_devitrification_points_returns_empty_dataframe_when_no_data(monkeypatch):
    monkeypatch.setattr(
        pi_client, "_fetch_element_raw",
        lambda element, start, end: pd.DataFrame(columns=["Attribute", "TimeStamp", "Value"]),
    )

    result = pi_client.get_devitrification_points("2026-03-10T00:00:00", "2026-03-11T00:00:00")

    assert result.empty
    assert list(result.columns) == ["timestamp", "position"]


# ===================== get_lobb_points =====================
# LOBB位置はGross/Netと違い極端にまばら(実機で約28時間に2件しか記録されていないことを確認済み)
# なため、merge_asofでGrossの時系列に合わせようとするとほぼ必ず取りこぼす。失透と同様、
# 独立した点として取得する

def test_get_lobb_points_returns_raw_points(monkeypatch):
    df_raw = pd.DataFrame({
        "Attribute": ["LobbPosition", "LobbPosition"],
        "TimeStamp": pd.to_datetime(["2026-03-10 15:25:00", "2026-03-11 01:14:00"]),
        "Value": ["72.0", "156.0"],
    })
    monkeypatch.setattr(pi_client, "_fetch_element_raw", lambda element, start, end: df_raw)

    result = pi_client.get_lobb_points("2026-03-10T00:00:00", "2026-03-12T00:00:00")

    assert list(result.columns) == ["timestamp", "position"]
    assert len(result) == 2
    assert list(result["position"]) == [72.0, 156.0]


def test_get_lobb_points_excludes_zero_outliers(monkeypatch):
    df_raw = pd.DataFrame({
        "Attribute": ["LobbPosition", "LobbPosition"],
        "TimeStamp": pd.to_datetime(["2026-03-10 08:00:00", "2026-03-10 08:05:00"]),
        "Value": ["0.0", "72.0"],
    })
    monkeypatch.setattr(pi_client, "_fetch_element_raw", lambda element, start, end: df_raw)

    result = pi_client.get_lobb_points("2026-03-10T00:00:00", "2026-03-11T00:00:00")

    assert list(result["position"]) == [72.0]


def test_get_lobb_points_returns_empty_dataframe_when_no_data(monkeypatch):
    monkeypatch.setattr(
        pi_client, "_fetch_element_raw",
        lambda element, start, end: pd.DataFrame(columns=["Attribute", "TimeStamp", "Value"]),
    )

    result = pi_client.get_lobb_points("2026-03-10T00:00:00", "2026-03-11T00:00:00")

    assert result.empty
    assert list(result.columns) == ["timestamp", "position"]


# ===================== get_lobb_hourly_count =====================

def test_get_lobb_hourly_count_counts_readings_per_hour(monkeypatch):
    df_raw = pd.DataFrame({
        "Attribute": ["LobbPosition"] * 4,
        "TimeStamp": pd.to_datetime([
            "2026-03-10 08:10:00", "2026-03-10 08:40:00",
            "2026-03-10 09:05:00", "2026-03-10 09:50:00",
        ]),
        "Value": ["100.0", "110.0", "90.0", "95.0"],
    })
    monkeypatch.setattr(pi_client, "_fetch_element_raw", lambda element, start, end: df_raw)

    result = pi_client.get_lobb_hourly_count("2026-03-10T00:00:00", "2026-03-11T00:00:00")

    assert list(result.columns) == ["hour", "count"]
    assert len(result) == 2
    assert result.iloc[0]["hour"] == pd.Timestamp("2026-03-10 08:00:00")
    assert result.iloc[0]["count"] == 2
    assert result.iloc[1]["hour"] == pd.Timestamp("2026-03-10 09:00:00")
    assert result.iloc[1]["count"] == 2


def test_get_lobb_hourly_count_excludes_zero_outliers(monkeypatch):
    df_raw = pd.DataFrame({
        "Attribute": ["LobbPosition", "LobbPosition"],
        "TimeStamp": pd.to_datetime(["2026-03-10 08:10:00", "2026-03-10 08:40:00"]),
        "Value": ["0.0", "110.0"],
    })
    monkeypatch.setattr(pi_client, "_fetch_element_raw", lambda element, start, end: df_raw)

    result = pi_client.get_lobb_hourly_count("2026-03-10T00:00:00", "2026-03-11T00:00:00")

    assert result.iloc[0]["count"] == 1


def test_get_lobb_hourly_count_returns_empty_dataframe_when_no_data(monkeypatch):
    monkeypatch.setattr(
        pi_client, "_fetch_element_raw",
        lambda element, start, end: pd.DataFrame(columns=["Attribute", "TimeStamp", "Value"]),
    )

    result = pi_client.get_lobb_hourly_count("2026-03-10T00:00:00", "2026-03-11T00:00:00")

    assert result.empty
    assert list(result.columns) == ["hour", "count"]
