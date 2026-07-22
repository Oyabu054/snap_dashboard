# -*- coding: utf-8 -*-
import pandas as pd
import pytest

import app as app_module
import pi_client


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def test_api_trend_includes_occurrence_minutes(client, monkeypatch):
    df = pd.DataFrame({
        "hour": pd.to_datetime(["2026-03-10 08:00:00", "2026-03-10 09:00:00"]),
        "occurrence_minutes": [8.0, 2.5],
        "count": [2, 1],
    })
    monkeypatch.setattr(
        pi_client, "get_hourly_trend",
        lambda start, end, defect_types=None: df,
    )

    res = client.get("/api/trend?start=2026-03-10T00:00:00&end=2026-03-11T00:00:00")

    assert res.status_code == 200
    data = res.get_json()["data"]
    assert data == [
        {"hour": "2026-03-10T08:00:00", "occurrence_minutes": 8.0, "count": 2},
        {"hour": "2026-03-10T09:00:00", "occurrence_minutes": 2.5, "count": 1},
    ]


def test_api_trend_handles_null_occurrence_minutes(client, monkeypatch):
    df = pd.DataFrame({
        "hour": pd.to_datetime(["2026-03-10 08:00:00"]),
        "occurrence_minutes": [float("nan")],
        "count": [0],
    })
    monkeypatch.setattr(
        pi_client, "get_hourly_trend",
        lambda start, end, defect_types=None: df,
    )

    res = client.get("/api/trend?start=2026-03-10T00:00:00&end=2026-03-11T00:00:00")

    assert res.get_json()["data"] == [
        {"hour": "2026-03-10T08:00:00", "occurrence_minutes": None, "count": 0},
    ]


def test_api_cst_rotation_trend_returns_timestamp_and_value(client, monkeypatch):
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(["2026-03-10 08:00:00", "2026-03-10 08:10:00"]),
        "value": [23.4, 24.1],
    })
    monkeypatch.setattr(pi_client, "get_cst_rotation_trend", lambda start, end: df)

    res = client.get("/api/cst_rotation_trend?start=2026-03-10T00:00:00&end=2026-03-11T00:00:00")

    assert res.status_code == 200
    assert res.get_json()["data"] == [
        {"timestamp": "2026-03-10T08:00:00", "value": 23.4},
        {"timestamp": "2026-03-10T08:10:00", "value": 24.1},
    ]


def test_api_thickness_trend_returns_timestamp_and_value(client, monkeypatch):
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(["2026-03-10 08:00:00", "2026-03-10 08:05:00"]),
        "value": [5.0, 5.1],
    })
    monkeypatch.setattr(pi_client, "get_thickness_trend", lambda start, end: df)

    res = client.get("/api/thickness_trend?start=2026-03-10T00:00:00&end=2026-03-11T00:00:00")

    assert res.status_code == 200
    assert res.get_json()["data"] == [
        {"timestamp": "2026-03-10T08:00:00", "value": 5.0},
        {"timestamp": "2026-03-10T08:05:00", "value": 5.1},
    ]


def test_api_vacuum_pressure_trend_returns_timestamp_and_value(client, monkeypatch):
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(["2026-03-10 08:00:00", "2026-03-10 08:10:00"]),
        "value": [712.0, 715.5],
    })
    monkeypatch.setattr(pi_client, "get_vacuum_pressure_trend", lambda start, end: df)

    res = client.get("/api/vacuum_pressure_trend?start=2026-03-10T00:00:00&end=2026-03-11T00:00:00")

    assert res.status_code == 200
    assert res.get_json()["data"] == [
        {"timestamp": "2026-03-10T08:00:00", "value": 712.0},
        {"timestamp": "2026-03-10T08:10:00", "value": 715.5},
    ]


def test_api_product_position_returns_gross_and_net(client, monkeypatch):
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(["2026-03-10 08:00:00"]),
        "gross_start": [5.0],
        "gross_end": [210.0],
        "net_start": [10.0],
        "net_end": [200.0],
    })
    monkeypatch.setattr(pi_client, "get_product_position", lambda start, end: df)

    res = client.get("/api/product_position?start=2026-03-10T00:00:00&end=2026-03-11T00:00:00")

    assert res.status_code == 200
    assert res.get_json()["data"] == [
        {
            "timestamp": "2026-03-10T08:00:00", "gross_start": 5.0, "gross_end": 210.0,
            "net_start": 10.0, "net_end": 200.0,
        },
    ]


def test_api_lobb_points_returns_timestamp_and_position(client, monkeypatch):
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(["2026-03-10 08:00:00", "2026-03-10 09:00:00"]),
        "position": [72.0, 156.0],
    })
    monkeypatch.setattr(pi_client, "get_lobb_points", lambda start, end: df)

    res = client.get("/api/lobb_points?start=2026-03-10T00:00:00&end=2026-03-11T00:00:00")

    assert res.status_code == 200
    assert res.get_json()["data"] == [
        {"timestamp": "2026-03-10T08:00:00", "position": 72.0},
        {"timestamp": "2026-03-10T09:00:00", "position": 156.0},
    ]


def test_api_lobb_hourly_count_returns_hour_and_count(client, monkeypatch):
    df = pd.DataFrame({
        "hour": pd.to_datetime(["2026-03-10 08:00:00", "2026-03-10 09:00:00"]),
        "count": [2, 1],
    })
    monkeypatch.setattr(pi_client, "get_lobb_hourly_count", lambda start, end: df)

    res = client.get("/api/lobb_hourly_count?start=2026-03-10T00:00:00&end=2026-03-11T00:00:00")

    assert res.status_code == 200
    assert res.get_json()["data"] == [
        {"hour": "2026-03-10T08:00:00", "count": 2},
        {"hour": "2026-03-10T09:00:00", "count": 1},
    ]


def test_api_devitrification_points_returns_timestamp_and_position(client, monkeypatch):
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(["2026-03-10 08:00:00", "2026-03-10 08:05:00"]),
        "position": [30.0, 40.0],
    })
    monkeypatch.setattr(pi_client, "get_devitrification_points", lambda start, end: df)

    res = client.get("/api/devitrification_points?start=2026-03-10T00:00:00&end=2026-03-11T00:00:00")

    assert res.status_code == 200
    assert res.get_json()["data"] == [
        {"timestamp": "2026-03-10T08:00:00", "position": 30.0},
        {"timestamp": "2026-03-10T08:05:00", "position": 40.0},
    ]
