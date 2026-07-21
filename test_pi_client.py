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
    monkeypatch.setattr(config, "SQL_LINKED_SERVER", "test_linked_server")
    monkeypatch.setattr(config, "AF_HIERARCHY_PATH", "\\03. Test\\")
    monkeypatch.setattr(config, "AF_ELEMENT_NAME", "DefectDetection")
    monkeypatch.setattr(config, "ATTR_START_TIME", "StartTime")
    monkeypatch.setattr(config, "ATTR_DURATION", "Duration")
    monkeypatch.setattr(config, "ATTR_POSITION", "Position")
    monkeypatch.setattr(config, "ATTR_DEFECT_TYPE", "DefectType")
    monkeypatch.setattr(config, "DURATION_UNIT", "seconds")
    monkeypatch.setattr(config, "TIMESTAMP_MATCH_TOLERANCE", "2s")
    monkeypatch.setattr(config, "DEFECT_TYPE_LOOKBACK_DAYS", 90)
    monkeypatch.setattr(config, "AF_PRODUCT_ELEMENT_NAME", "ProductEdge")
    monkeypatch.setattr(config, "ATTR_PRODUCT_GROSS_START", "GrossStart")
    monkeypatch.setattr(config, "ATTR_PRODUCT_GROSS_END", "GrossEnd")
    monkeypatch.setattr(config, "ATTR_PRODUCT_NET_START", "NetStart")
    monkeypatch.setattr(config, "ATTR_PRODUCT_NET_END", "NetEnd")


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


def test_fetch_element_raw_returns_empty_dataframe_when_no_rows(monkeypatch):
    fake_conn = _FakeConnection([])
    monkeypatch.setattr(pi_client.pymssql, "connect", lambda **kwargs: fake_conn)

    df = pi_client._fetch_element_raw(
        "DefectDetection", "2026-03-10T00:00:00", "2026-03-11T00:00:00"
    )

    assert df.empty
    assert list(df.columns) == ["Attribute", "TimeStamp", "Value"]


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


# ===================== get_product_position =====================

def test_get_product_position_merges_four_attributes(monkeypatch):
    df_raw = pd.DataFrame({
        "Attribute": ["GrossStart", "GrossEnd", "NetStart", "NetEnd"],
        "TimeStamp": pd.to_datetime(["2026-03-10 08:00:00"] * 4),
        "Value": ["0.0", "210.0", "10.0", "200.0"],
    })
    monkeypatch.setattr(pi_client, "_fetch_element_raw", lambda element, start, end: df_raw)

    result = pi_client.get_product_position("2026-03-10T00:00:00", "2026-03-11T00:00:00")

    assert len(result) == 1
    row = result.iloc[0]
    assert row["gross_start"] == 0.0
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
