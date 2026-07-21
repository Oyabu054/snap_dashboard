# -*- coding: utf-8 -*-
"""欠点モニタリングダッシュボード バックエンド"""
import io
from datetime import datetime

import pandas as pd
from flask import Flask, jsonify, request, send_file, render_template

import config
import pi_client
import box_client

app = Flask(__name__)


def _parse_range():
    start = request.args.get("start")
    end = request.args.get("end")
    if not start or not end:
        raise ValueError("start, end は必須のクエリパラメータです")
    return start, end


@app.route("/")
def index():
    return render_template("index.html", position_max=config.POSITION_MAX)


@app.route("/api/defect_types")
def api_defect_types():
    try:
        return jsonify({"defect_types": pi_client.get_available_defect_types()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/defects")
def api_defects():
    try:
        start, end = _parse_range()
        defect_types = request.args.getlist("type")
        df = pi_client.get_defects(start, end, defect_types or None)
        data = [
            {
                "timestamp": row.timestamp.isoformat(),
                "position": float(row.position),
                "duration_minutes": (
                    float(row.duration_minutes) if pd.notna(row.duration_minutes) else None
                ),
                "defect_type": row.defect_type,
            }
            for row in df.itertuples()
        ]
        return jsonify({"data": data})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/trend")
def api_trend():
    try:
        start, end = _parse_range()
        defect_types = request.args.getlist("type")
        df = pi_client.get_hourly_trend(start, end, defect_types or None)
        data = [{"hour": row.hour.isoformat(), "count": int(row.count)} for row in df.itertuples()]
        return jsonify({"data": data})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/product_position")
def api_product_position():
    """製品(ガラスリボン)の内側・外側エッジ位置。常時表示用、フィルター非依存。"""
    try:
        start, end = _parse_range()
        df = pi_client.get_product_position(start, end)
        data = [
            {
                "timestamp": row.timestamp.isoformat(),
                "gross_start": float(row.gross_start),
                "gross_end": float(row.gross_end),
                "net_start": float(row.net_start),
                "net_end": float(row.net_end),
            }
            for row in df.itertuples()
        ]
        return jsonify({"data": data})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/photos")
def api_photos():
    try:
        start = datetime.fromisoformat(request.args.get("start"))
        end = datetime.fromisoformat(request.args.get("end"))
        photos = box_client.get_photos(start, end)
        for p in photos:
            p["thumbnail_url"] = box_client.get_thumbnail_url(p["id"])
        return jsonify({"data": photos})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/photo_thumbnail/<file_id>")
def api_photo_thumbnail(file_id):
    try:
        thumb = box_client.get_thumbnail_bytes(file_id)
        return send_file(io.BytesIO(thumb), mimetype="image/png")
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host=config.FLASK_HOST, port=config.FLASK_PORT, debug=True)
