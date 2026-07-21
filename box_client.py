# -*- coding: utf-8 -*-
"""
Box.com からの写真リスト取得モジュール
======================================

config.BOX_JWT_CONFIG_FILE には、Box Developer Console で
Custom App(Server Authentication with JWT)を作成した際にダウンロードできる
設定ファイル(config.json)のパスを指定してください。

作成手順の概要:
  1. https://app.box.com/developers/console でCustom Appを新規作成
  2. 認証方式は "Server Authentication (with JWT)" を選択
  3. Configurationタブで公開鍵/秘密鍵ペアを生成 → 設定ファイルがダウンロードされる
  4. Application Scopesで "Read all files and folders stored in Box" を有効化
  5. 管理者の承認(Authorization)が必要な場合あり
  6. 対象フォルダにこのアプリのService Accountをコラボレーターとして追加
"""
import re
from datetime import datetime

from boxsdk import JWTAuth, Client

import config

_client = None


def _get_client():
    global _client
    if _client is None:
        auth = JWTAuth.from_settings_file(config.BOX_JWT_CONFIG_FILE)
        _client = Client(auth)
    return _client


def _extract_datetime(filename: str):
    m = re.search(config.PHOTO_FILENAME_DATETIME_PATTERN, filename)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), config.PHOTO_FILENAME_DATETIME_FORMAT)
    except ValueError:
        return None


def get_photos(start: datetime, end: datetime):
    """
    指定フォルダ内の画像ファイルのうち、ファイル名から抽出した日時が
    [start, end] の範囲に入るものを一覧で返す。

    Returns
    -------
    list[dict]  # [{id, name, timestamp}, ...] timestamp昇順
    """
    client = _get_client()
    folder = client.folder(folder_id=config.BOX_FOLDER_ID)
    results = []

    for item in folder.get_items():
        if item.type != "file":
            continue
        if not item.name.lower().endswith((".jpg", ".jpeg", ".png", ".bmp")):
            continue

        ts = _extract_datetime(item.name)
        if ts is None or not (start <= ts <= end):
            continue

        results.append({"id": item.id, "name": item.name, "timestamp": ts.isoformat()})

    results.sort(key=lambda x: x["timestamp"])
    return results


def list_excel_files(folder_id: str):
    """
    指定Boxフォルダ内のExcelファイル一覧を返す(excel_photos.sync_cache用)。

    Returns
    -------
    list[dict]  # [{id, name, updated_at}, ...]
    """
    client = _get_client()
    folder = client.folder(folder_id=folder_id)
    results = []

    for item in folder.get_items():
        if item.type != "file":
            continue
        if not item.name.lower().endswith((".xlsx", ".xls")):
            continue
        results.append({
            "id": item.id,
            "name": item.name,
            "updated_at": getattr(item, "modified_at", None),
        })

    return results


def download_file_content(file_id: str) -> bytes:
    """指定Boxファイルの内容をバイト列で返す(excel_photos.sync_cache用)"""
    client = _get_client()
    return client.file(file_id).content()


def get_thumbnail_url(file_id: str) -> str:
    """フロントエンドが<img>のsrcに使う、バックエンド経由のサムネイルURL"""
    return f"/api/photo_thumbnail/{file_id}"


def get_thumbnail_bytes(file_id: str) -> bytes:
    client = _get_client()
    box_file = client.file(file_id)
    return box_file.get_thumbnail(extension="png")
