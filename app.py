# -*- coding: utf-8 -*-
"""欠点モニタリングダッシュボード バックエンド"""
import io
import sys
import threading
import webbrowser
from datetime import datetime
from pathlib import Path

import pandas as pd
from flask import Flask, jsonify, request, send_file, render_template

import config
import pi_client
import box_client

# PyInstallerでexe化した場合、templates/staticはsys._MEIPASS(exe内の一時展開先)に
# 同梱される。通常実行時はこのファイルと同じフォルダを見る。
if getattr(sys, "frozen", False):
    _RESOURCE_DIR = Path(sys._MEIPASS)
else:
    _RESOURCE_DIR = Path(__file__).parent

app = Flask(
    __name__,
    template_folder=str(_RESOURCE_DIR / "templates"),
    static_folder=str(_RESOURCE_DIR / "static"),
)


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
        data = [
            {
                "hour": row.hour.isoformat(),
                "occurrence_minutes": (
                    float(row.occurrence_minutes) if pd.notna(row.occurrence_minutes) else None
                ),
                "count": int(row.count),
            }
            for row in df.itertuples()
        ]
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


def _open_browser():
    webbrowser.open(f"http://127.0.0.1:{config.FLASK_PORT}/")


if __name__ == "__main__":
    # サーバー起動を待ってからブラウザを開く(exe化時に起動直後に自動で開くための対応)
    threading.Timer(1.0, _open_browser).start()
    # debug=Trueのリローダーは自身のプロセスを再起動するため、ブラウザが二重に開いてしまう。
    # exe配布を前提に無効化する(開発時にコード変更を反映したい場合は手動でプロセスを再起動すること)
    app.run(host=config.FLASK_HOST, port=config.FLASK_PORT, debug=False)
