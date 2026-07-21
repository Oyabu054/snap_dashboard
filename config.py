# -*- coding: utf-8 -*-
"""
設定ローダー
============
実際の接続設定は config.txt(このファイルと同じディレクトリ)に記述する。
機密情報・環境固有の値をソースコード(.py)に直接書かないための構成。

- config.txt は .gitignore 済み(Git管理に含めない)
- config.txt.example をコピーして config.txt を作成し、値を書き換えること
- このモジュールは config.txt を読み込み、他のモジュールから
  `import config; config.SQL_HOST` のようにこれまで通り参照できる形で
  定数として展開するだけの役割
"""
import configparser
from pathlib import Path

_CONFIG_PATH = Path(__file__).parent / "config.txt"

if not _CONFIG_PATH.exists():
    raise FileNotFoundError(
        f"{_CONFIG_PATH} が見つかりません。\n"
        f"config.txt.example をコピーして config.txt を作成し、実際の値を設定してください。"
    )

# interpolation=None: 日時フォーマット文字列などに含まれる "%" を素通しするため
_parser = configparser.ConfigParser(interpolation=None)
_parser.read(_CONFIG_PATH, encoding="utf-8")


def _get(section, key, fallback=None):
    return _parser.get(section, key, fallback=fallback)


# ---------------------------------------------------------------
# PI 接続設定
# ---------------------------------------------------------------
# PI AFにはpymssql経由・リンクサーバーへのOPENQUERYでアクセスする
# (PIconnect/AF SDKのWindows統合認証制約を回避し、技術アカウントの
# ユーザー名/パスワードで接続するため)。
SQL_HOST = _get("pi", "sql_host")
SQL_USER = _get("pi", "sql_user")
SQL_PASSWORD = _get("pi", "sql_password")
SQL_DATABASE = _get("pi", "sql_database")

# OPENQUERY先のリンクサーバー名
SQL_LINKED_SERVER = _get("pi", "sql_linked_server")

# 欠点データ・製品位置データが属するAFフォルダ階層(eh.Path)。両要素で共通の前提
AF_HIERARCHY_PATH = _get("pi", "af_hierarchy_path")

# 欠点データを持つAF要素名(a.Element)
AF_ELEMENT_NAME = _get("pi", "af_element_name")

# 欠点データは以下4つの属性に分かれて格納されている想定
ATTR_START_TIME = _get("pi", "attr_start_time")      # 発生時刻
ATTR_DURATION = _get("pi", "attr_duration")           # 継続発生時間
ATTR_POSITION = _get("pi", "attr_position")           # 発生位置(0〜POSITION_MAX、大きいほど左側)
ATTR_DEFECT_TYPE = _get("pi", "attr_defect_type")     # 欠点の種類

# ATTR_DURATIONの値の単位。get_defects()内でこれを分単位に変換します。
DURATION_UNIT = _get("pi", "duration_unit", fallback="seconds")  # "seconds"|"minutes"|"milliseconds"

# 位置スケール(0〜この値。値が大きいほど左側)
POSITION_MAX = _parser.getint("pi", "position_max", fallback=210)

# 複数属性のタイムスタンプが完全一致しない場合に、同一欠点とみなす許容誤差
TIMESTAMP_MATCH_TOLERANCE = _get("pi", "timestamp_match_tolerance", fallback="2s")

# フィルターのドロップダウンに表示する欠点種類一覧を取得する際に遡る日数
# (PIconnectのPI相対時間構文"*-90d"はSQL直接クエリでは使えないため、日数指定に変更)
DEFECT_TYPE_LOOKBACK_DAYS = _parser.getint("pi", "defect_type_lookback_days", fallback=90)

# 製品位置データ(Gross幅・Net幅、常時表示)。AFフォルダ階層はAF_HIERARCHY_PATHを共有
# 位置の大小関係(値が大きいほど左側): Gross終わり > Net終わり > Net開始 > Gross開始
AF_PRODUCT_ELEMENT_NAME = _get("pi", "af_product_element_name") or AF_ELEMENT_NAME
ATTR_PRODUCT_GROSS_START = _get("pi", "attr_product_gross_start")
ATTR_PRODUCT_GROSS_END = _get("pi", "attr_product_gross_end")
ATTR_PRODUCT_NET_START = _get("pi", "attr_product_net_start")
ATTR_PRODUCT_NET_END = _get("pi", "attr_product_net_end")

# ---------------------------------------------------------------
# Box.com 接続設定
# ---------------------------------------------------------------
# Box Developer ConsoleでCustom App(Server Authentication with JWT)を作成し、
# ダウンロードした設定ファイルをこのパスに配置してください(これもGit管理外)。
BOX_JWT_CONFIG_FILE = _get("box", "jwt_config_file", fallback="box_jwt_config.json")

# 写真が格納されているBoxフォルダのID(フォルダURL末尾の数字)
BOX_FOLDER_ID = _get("box", "folder_id")

# Excel埋め込み写真方式で、Excelファイルが格納されているBoxフォルダのID
# (画像直置き用フォルダと異なる場合に指定。空欄ならfolder_idと同じ扱い)
EXCEL_BOX_FOLDER_ID = _get("box", "excel_folder_id") or BOX_FOLDER_ID

# ファイル名から日時を抽出する正規表現・フォーマット(画像直置き方式用)
PHOTO_FILENAME_DATETIME_PATTERN = _get("box", "filename_datetime_pattern", fallback=r"(\d{8}_\d{6})")
PHOTO_FILENAME_DATETIME_FORMAT = _get("box", "filename_datetime_format", fallback="%Y%m%d_%H%M%S")

# Excel埋め込み写真方式で、Excelファイル名からライン名/日付を抽出する正規表現。
# 名前付きグループ line_name / year / month / day が必須(timeは任意、未使用)
EXCEL_FILENAME_PATTERN = _get(
    "box",
    "excel_filename_pattern",
    fallback=r"[\(（](?P<line_name>[^\)）]*)[\)）]"
    r"(?P<year>\d{4})\.(?P<month>\d{2})\.(?P<day>\d{2})_(?P<time>\d{4})_",
)

# Excel埋め込み写真のキャッシュ保存先(index.json・抽出画像を格納するディレクトリ)
EXCEL_PHOTO_CACHE_DIR = _get("box", "excel_photo_cache_dir", fallback="cache")

# ---------------------------------------------------------------
# Flask設定
# ---------------------------------------------------------------
FLASK_HOST = _get("flask", "host", fallback="127.0.0.1")
FLASK_PORT = _parser.getint("flask", "port", fallback=5000)
