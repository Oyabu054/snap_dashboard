# 欠点モニタリングダッシュボード

PI AF の欠点データ(位置・種類)と Box.com 上の現場写真を1画面に統合したWebダッシュボードです。

```
左: フィルター(日時範囲 + 欠点種類)
中央上: 欠点マップ(横軸=日時、縦軸=位置)
中央下: 1時間ごとの欠点発生トレンド
右: フィルター範囲に対応するBox写真リスト
```

## 1. セットアップ

```bash
cd snap_dashboard
python -m venv venv
venv\Scripts\activate      # Windowsの場合
pip install -r requirements.txt
cp config.txt.example config.txt   # Windowsの場合は copy config.txt.example config.txt
```

PIデータへはpymssqlでSQL Serverに接続し、リンクサーバー経由のOPENQUERYで取得します
(AF SDK/PIconnectは使用しません。詳細は下記「PIの接続方式について」を参照)。

## 2. `config.txt` の編集

接続設定・機密情報は **すべて `config.txt` に分離**しており、ソースコード(.py)には
含まれません。`config.txt` は `.gitignore` 対象なのでGit管理にも入りません。
`config.py` は起動時に `config.txt` を読み込むローダーです。

以下を実際の値に書き換えてください(`[pi]` セクション)。

| 項目 | 内容 |
|---|---|
| `sql_host` / `sql_user` / `sql_password` / `sql_database` | PIのリンクサーバーが設定されているSQL Serverへの接続情報(技術アカウント) |
| `sql_linked_server` | OPENQUERY先のリンクサーバー名(PI System Explorerで確認済みのため既定値`aichi_2fl`あり) |
| `duration_unit` | 継続発生時間の単位(秒/分/ミリ秒) |
| `position_max` | 位置スケールの最大値(既定210) |
| `defect_type_lookback_days` | 欠点種類ドロップダウン用に遡って取得する日数(既定90) |

AFフォルダ階層・要素名・属性名(`a.Element`/`a.Name`)はPI System Explorerで確認済みのため、
`config.txt`ではなく `pi_client.py` 冒頭に直接定数として持たせています。変更する場合は
そちらを編集してください。

`[box]` セクション:

| 項目 | 内容 |
|---|---|
| `jwt_config_file` | Box Developer Consoleでダウンロードした認証設定ファイルのパス |
| `folder_id` | 写真フォルダ(画像直置き方式)のID(フォルダURL末尾の数字) |
| `filename_datetime_pattern` / `_format` | 写真ファイル名から日時を抽出する正規表現・フォーマット(画像直置き方式用) |
| `excel_folder_id` | Excelファイルが格納されているフォルダのID(Excel埋め込み写真方式用。空欄なら`folder_id`と同じ) |
| `excel_filename_pattern` | Excelファイルからライン名/日付を抽出する正規表現(既定は受領済みの命名規則`（ライン名）YYYY.MM.DD_HHMM_品種_厚みコード.xlsx`に対応) |
| `excel_photo_cache_dir` | Excel埋め込み写真の抽出結果(`index.json`・画像ファイル)を保存するディレクトリ(既定`cache`) |

### PIの接続方式について(重要)

当初はPIconnect(AF SDK)経由の`PIAFDatabase`接続を想定していましたが、
これはWindows統合認証のみにしか対応しておらず、技術アカウントのユーザー名/
パスワードを渡す手段がありませんでした。

そのため、**pymssqlでSQL Serverに接続し、PIが公開しているリンクサーバー
経由の`OPENQUERY`でPIの内部テーブル(`Master.Element.ElementHierarchy` /
`Attribute` / `Archive`)を直接SQLで取得する方式**に変更しています。
この方式は社内の別のPI連携プログラム(JOF/KOF監視ダッシュボード)で
実績のある方法です。`sql_user` / `sql_password` に技術アカウントの
認証情報を設定してください。

認証情報は`config.txt`に平文で残ります(Git管理外・`.gitignore`済みですが、
ファイルシステム上には残る点に注意してください)。より安全にしたい場合は
Windows資格情報マネージャー等との連携を検討してください。

### Box連携の準備
1. https://app.box.com/developers/console でCustom Appを作成
2. 認証方式 "Server Authentication (with JWT)" を選択
3. Configurationタブで鍵ペアを生成 → 設定ファイル(config.json)をダウンロード
4. Application Scopesで "Read all files and folders stored in Box" を有効化
5. 管理者承認が必要な場合は情シス等に依頼
6. 対象のBoxフォルダに、このアプリのService Accountをコラボレーターとして追加
7. ダウンロードした設定ファイルを `config.txt` の `jwt_config_file` で指定したパスに配置
   (これもGit管理外)

## 3. 実行

```bash
python app.py
```

ブラウザで `http://127.0.0.1:5000` を開いてください。

## 4. 実装上の前提・要調整ポイント

PIのAFフォルダ階層・要素名・属性名は、PI System Explorerで下記の実値が確認済みです
(`pi_client.py`にハードコード)。

```
\\T183PIAKPA1\aichi_2fl\01. PI Data\010. 生産(未修)\スナップ
```

「スナップ」要素の直下に、欠点データ4属性と製品位置データ4属性がすべて記録されています。

| 役割 | 属性名 |
|---|---|
| 発生時刻(`ATTR_START_TIME`) | スナップクリア操作適用年月日 |
| 継続発生時間(`ATTR_DURATION`) | スナップ継続時間 |
| 発生位置(`ATTR_POSITION`) | スナップ入力開始幅方向位置 |
| 欠点の種類(`ATTR_DEFECT_TYPE`) | スナップ入力欠点種類 |
| Gross開始/終了位置 | グロス開始位置 / グロス終了位置 |
| Net開始/終了位置 | ネット開始位置 / ネット終了位置 |

- **欠点データ(4属性)**: 発生時刻・継続発生時間・発生位置・種類が、それぞれ別属性として
  ほぼ同時刻に記録されている前提です(`TIMESTAMP_MATCH_TOLERANCE` 以内のズレを同一欠点とみなして
  マージします)。もし実際は欠点1件ごとに Event Frame として管理されている場合は、
  `pi_client.py` の `get_defects()` を Event Frame 用のSQL(`Master.EventFrame.*`相当のテーブル)
  から取得する実装に差し替えてください。
- **発生時刻の扱い**: `ATTR_START_TIME`(スナップクリア操作適用年月日)の値がdatetimeとして
  解釈できればそれをグラフのX軸に使い、解釈できない場合は `ATTR_POSITION` が記録された
  PIタイムスタンプにフォールバックします。
- **発生分数の集計**: `get_hourly_trend()` は継続時間(分換算)を発生時刻が属する1時間バケットに
  合計しています。1時間を跨ぐ長時間欠点を按分したい場合は、この集計ロジックを調整してください。
- **製品位置データ**: Gross(全体)幅とNet(内側)幅の2種類の帯があり、それぞれ開始・終了位置の
  計4属性が、欠点データと同じ「スナップ」要素にあります。
  位置の大小関係は `Gross終わり > Net終わり > Net開始 > Gross開始` です。
  このデータは欠点マップに常時、Gross帯は塗りつぶし・Net境界は破線として重ね表示され、
  欠点種類フィルターの影響を受けません。
- **位置の向き**: `POSITION_MAX`(既定210)を上限に、数値が大きいほど左側・小さいほど右側になる
  想定で、欠点マップのY軸は上=左・下=右で固定表示しています。
- **写真データ(Excel埋め込み方式)**: `excel_photos.py` の `parse_filename()` / `get_photos()` / `sync_cache()`
  は実装・テスト済みですが、`/api/photos` はまだ `box_client`(画像ファイル直置き方式)を
  呼んでいます。切り替え作業は未着手です(下記「今後の実装タスク」参照)。

## 5. リアルタイム監視について

右上の「リアルタイム更新」をONにすると、30秒ごとに終了日時を現在時刻に更新して
自動再取得します(WebSocketではなくポーリング方式のため、間隔は `dashboard.js` の
`setInterval(..., 30000)` で調整可能です)。

## 6. テストの実行

`pi_client.py`・`excel_photos.py`はpymssql/Box/openpyxlをモックしたユニットテストを備えています
(実機のSQL Server・Box接続がなくても実行可能)。

```bash
pip install -r requirements.txt   # pytestも含まれます
pytest
```

## 7. 今後の実装タスク

現時点で未着手・要対応の項目です。詳細は `CLAUDE.md` の「次のタスク」「既知のリスク」も参照してください。

1. `/api/photos` を `excel_photos` ベースに切り替え(現状は `box_client` の画像直置き方式のまま)
2. フィルターパネルに「写真を今すぐ同期」ボタン + 同期用APIの追加
3. 実機接続確認: SQL Server/リンクサーバーへの接続情報(`sql_host`等)を`config.txt`に設定し、
   pymssql経由での実データ取得を確認(AFフォルダ階層・要素名・属性名は確認済み)。
   タイムゾーンのずれ・DefectType列挙値の戻り値形式もあわせて確認
4. Boxフォルダの実値設定(`folder_id`/`excel_folder_id`)、JWT認証設定
5. `config.txt` を新スキーマ(`sql_host`等)に手動更新(Git管理外のため自動更新されていません)
