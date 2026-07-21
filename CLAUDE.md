# CLAUDE.md — 欠点モニタリングダッシュボード 引き継ぎ資料

## プロジェクト概要

フロートガラス製造ラインの欠点データ(PI AF)と現場写真(Box上のExcelに埋め込み)を
1画面に統合するWebダッシュボード。Claude(Web版)との対話で仕様策定・プロトタイプ実装まで
完了しており、以降の開発をClaude Codeで行う。

- 実行環境: Windows端末上でFlaskをローカル起動し、ブラウザで閲覧
- スタック: Python (Flask + pymssql + pandas + boxsdk) / フロントは素のJS + Plotly.js(CDN)
- PIデータへはAF SDK/PIconnectではなく、pymssqlでSQL Serverに接続し
  リンクサーバー経由のOPENQUERYで取得する方式(詳細は「PIの接続方式」参照)

## 画面仕様(ユーザーと合意済み)

1画面構成。白背景ベース(ダークテーマから変更済み)。

| 領域 | 内容 |
|---|---|
| 左 | フィルターパネル: 開始/終了日時、欠点種類チェックボックス、適用ボタン、クイック選択(1h/8h/24h/7d) |
| 中央上 | 欠点マップ: X=日時(右が最新)、Y=位置0〜210(**上=左側=大きい値、下=右側**)。欠点は発生時刻→+継続時間の**横線分**で表示(マーカーサイズでの表現は却下済み)。ホバーで種類/発生時刻/位置/継続時間のツールチップ表示 |
| 中央下 | 時間帯別トレンド: 1時間ごとの**発生分数**(継続時間の合計・分)の棒グラフ。件数ではない点に注意 |
| 右 | 現場写真リスト: 日時抽出してフィルターの日時範囲と連動 |
| 右上 | リアルタイム更新トグル(30秒ポーリング、終了日時を現在時刻に更新して再取得) |

### 製品位置(常時表示・フィルター非依存)

欠点マップに4本の線を常時重ね描画。**塗りつぶしはしない**(ユーザー指示)。

位置の大小関係(値が大きいほど左側=画面上side):
```
Gross終わり > Net終わり > Net開始 > Gross開始
```
- Gross(全体幅): 実線・薄いグレー (#94a3b8)
- Net(内側幅): 破線 (#475569)

## データモデル(実値確認済み、2026-07-21)

PI System Explorerで下記のAFフォルダ階層・要素名・属性名を確認済み。
`config.txt`ではなく`pi_client.py`冒頭にハードコードしている(機密情報ではなく、
アプリのビジネスロジックの一部と判断)。

```
\\T183PIAKPA1\aichi_2fl\01. PI Data\010. 生産(未修)\スナップ
```

「スナップ」要素(AF_HIERARCHY_PATH=`\01. PI Data\010. 生産(未修)\`、
AF_ELEMENT_NAME=`スナップ`)の直下に、欠点データ4属性・製品位置データ4属性が
すべて記録されている(別要素ではなく同一要素)。

### 欠点データ(4属性)
1. 発生時刻 (`ATTR_START_TIME`) = `スナップクリア操作適用年月日`
2. 継続発生時間 (`ATTR_DURATION`) = `スナップ継続時間` — 単位は`DURATION_UNIT`で設定(要実機確認)
3. 発生位置 (`ATTR_POSITION`) = `スナップ入力開始幅方向位置` — 0〜210、大きいほど左
4. 種類 (`ATTR_DEFECT_TYPE`) = `スナップ入力欠点種類`

現実装は「4つの時系列属性を近接タイムスタンプ(`TIMESTAMP_MATCH_TOLERANCE`=2s)で
merge_asofマージ」する方式。**Event Frame方式だった場合は `pi_client.get_defects()` を
Event Frame用のSQL(`Master.EventFrame.*`相当のテーブル)から取得する実装に
書き換えること。**

### 製品位置データ
同じ「スナップ」要素にある以下4属性。
- Gross開始位置 = `グロス開始位置`、Gross終了位置 = `グロス終了位置`
- Net開始位置 = `ネット開始位置`、Net終了位置 = `ネット終了位置`

### 写真データ(Box上のExcelに埋め込み)
- 写真はExcelファイル内に埋め込まれていることがほとんど(画像ファイル直置きではない)
- Excelの分割単位は**不規則**
- 写真と日時の対応は**ファイル名・シート名の日付のみ**(=日単位の粒度になる)
- 処理方式: **定期事前抽出+キャッシュ、＋「今すぐ同期」ボタン**のハイブリッドで合意済み
- **命名規則を受領済み**: `（ライン名）YYYY.MM.DD_HHMM_品種_厚みコード.xlsx`
  (括弧は全角・半角どちらもあり得る想定、HHMMはファイル作成/出力時刻で
  フィルタリングには使わない=日単位粒度)。正規表現は`config.EXCEL_FILENAME_PATTERN`
- `parse_filename()`(ファイル名→ライン名/日付)・`get_photos()`(cache/index.jsonから
  日付範囲でフィルタ)・`sync_cache()`(Box取得+openpyxl画像抽出+差分キャッシュ書き込み、
  manifest.jsonでBox側updated_atを比較し未変更ファイルはスキップ)はすべて実装・テスト済み。
  `box_client.py`に`list_excel_files()`/`download_file_content()`を追加済み(boxsdkのモック
  なしテスト対象外、既存の`get_photos()`と同様の位置づけ)

## ファイル構成

```
snap_dashboard/
├── app.py              # Flask本体。API: /api/defect_types, /api/defects,
│                       #   /api/trend, /api/product_position, /api/photos,
│                       #   /api/photo_thumbnail/<id>
├── config.py           # config.txtを読み込む設定ローダー(値はここに書かない)
├── config.txt          # 実際の接続設定・機密情報(.gitignore対象)
├── config.txt.example  # config.txtのテンプレート(Gitコミット対象)
├── .gitignore          # config.txt, box_jwt_config.json 等を除外
├── pi_client.py        # PIアクセス。pymssql+OPENQUERYで取得、merge_asofで4属性を欠点1件に統合
├── box_client.py       # Box API(JWT認証)。画像直置き方式 + Excel一覧/ダウンロード関数
├── excel_photos.py     # Excel埋め込み写真抽出。parse_filename/get_photos/sync_cache実装済み
├── test_pi_client.py   # pi_client.pyのテスト(pymssqlをモック)
├── test_excel_photos.py # excel_photos.pyのテスト
├── requirements.txt
├── README.md           # 人間向けセットアップ手順(テスト実行方法・今後のタスクも記載)
├── templates/index.html
└── static/
    ├── css/style.css   # 白背景テーマ。デザイントークンは:rootのCSS変数に集約
    └── js/dashboard.js # Plotly描画、フィルター、ポーリング
```

このリポジトリは現時点でGit管理下にありません(`.git`未作成)。`.gitignore`は準備済みです。

## 実装済みの細かい仕様・判断

- 発生時刻は `ATTR_START_TIME` の値をdatetimeとして解釈できればX軸に使用、
  できなければPositionのPIタイムスタンプにフォールバック(`_parse_start_time`)
- 継続時間が欠損/極小の欠点も見えるよう最小表示幅 `MIN_VISIBLE_DURATION_MINUTES = 0.15` 分
- 発生分数の集計は発生時刻が属する1時間バケットに全量計上(時間跨ぎの按分は未実装)
- ライブ更新は `Plotly.react` で再描画(newPlotから変更済み、ちらつき防止)
- 適用ボタンはロード中 disabled + 「読み込み中…」表示
- Boxエラーは写真パネル内のメッセージに留め、グラフ表示は妨げない
- pandas: `resample("1h")` (大文字Hは非推奨のため使用しない)
- Box認証はJWT (Custom App)。設定手順はREADME参照
- 欠点の線分は `mode: 'lines+markers'`(小さいマーカーでホバー判定を広げている)。
  ホバー時は種類・発生時刻(`%{x|%m/%d %H:%M:%S}`)・位置・継続時間を表示、
  `hoverlabel`は白背景で明示指定(白テーマ変更時の視認性対策)

## 設定管理(config.txt化・要認識)

ユーザー要望により、接続設定・機密情報はすべて `config.txt`(Git管理外、`.gitignore`済み)
に分離済み。`config.py` は `config.txt` を読み込んで定数展開するローダーのみ。
`config.txt.example` がテンプレート。**新しい設定項目を追加する際は両方のファイルを
更新すること**(loaderのconfig.pyと、example)。

**PIの接続方式(2026-07-20変更)**: 当初PIconnect(AF SDK)の`PIAFDatabase`を想定していたが、
Windows統合認証のみで技術アカウントが使えない制約が判明。ユーザーから提供された
別プログラム(JOF/KOF監視ダッシュボード、pymssql + OPENQUERYでPIの内部テーブルを
直接SQL取得)を参考に、`pi_client.py`をpymssql方式に全面書き換え済み。
`config.txt`の`sql_host`/`sql_user`/`sql_password`/`sql_database`(SQL Server接続)、
`sql_linked_server`(リンクサーバー名、既定値`aichi_2fl`)を使用する。
**旧キー(`af_server`/`af_database`/`af_element_path`/`af_product_element_path`/
`pi_username`/`pi_password`/`pi_domain`)は廃止**。ユーザーの実際の`config.txt`
(Git管理外)は新スキーマへの手動更新が必要(このファイルは機密情報のため
Claude Codeが直接書き換えていない)。

`requirements.txt`は`PIconnect`を削除し`pymssql>=2.3`を追加済み。

**AF階層・要素名・属性名はconfig.txtから除外(2026-07-21変更)**: PI System Explorerで
実値確認済みのため、ユーザー指示により`af_hierarchy_path`/`af_element_name`/
`af_product_element_name`/`attr_*`/`attr_product_*`は`config.txt`に置かず、
`pi_client.py`冒頭に直接定数としてハードコードする方針に変更。理由: これらは
デプロイ環境ごとに変わる機密情報ではなく、このPIシステム固有の固定値(ビジネスロジックの一部)
のため。値を変更する場合は`pi_client.py`を直接編集すること。

## 既知のリスク・要実機確認事項

1. **タイムゾーン**: フロントは `toISOString()` でUTC(Z付き)を送信。SQL側の
   `ar.TimeStamp BETWEEN`比較で実機のPI内部テーブルのタイムゾーンとずれないか要確認。
   ずれる場合はバックエンドでローカル時刻に変換してからSQLクエリに渡す
2. **DefectTypeが列挙値(Enumeration Set)の場合**、`ar.Value`の戻り値が
   期待通りの文字列でない可能性あり。`get_available_defect_types()` の動作確認
3. **データ量**: 7日間表示で欠点数が数千件を超える場合、線分方式(1欠点3点)の
   描画性能とAPI応答サイズを確認。必要ならWebGL(scattergl)や間引きを検討
4. **旧形式.xls**: Excel写真抽出でxlsが混在する場合openpyxl不可。
   ユーザーは過去にxlrd+openpyxlの変換スクリプトを作成済みなので流用可
5. **`ATTR_DURATION`(スナップ継続時間)の実際の単位**が秒/分/ミリ秒のいずれか未確認。
   `config.txt`の`duration_unit`で調整

(旧リスク「属性名はすべて仮名」は2026-07-21のPI System Explorer確認で解消済み)

## 実装再開前のチェックリスト(2026-07-21時点)

### A. ユーザー側で対応が必要(設定・実機確認。Claude Codeでは代行不可)

1. **`config.txt`を新スキーマに手動更新**: pymssql移行に伴い`sql_host`/`sql_user`/
   `sql_password`/`sql_database`/`sql_linked_server`/`defect_type_lookback_days`が
   新規追加、`af_server`/`af_database`/`af_element_path`/`af_product_element_path`/
   `pi_username`/`pi_password`/`pi_domain`は廃止。AFフォルダ階層・要素名・属性名は
   config.txtに置かず`pi_client.py`にハードコード済み(実値確認済みのため設定不要)。
   `excel_folder_id`(Excel格納Boxフォルダ)も追加項目。config.txtは機密情報のため
   Claude Codeは直接編集していない。`config.txt.example`と差分を取って更新すること
   → **2026-07-21 対応済み・実機接続確認済み**(下記参照)
2. タイムゾーンのずれ(既知リスク1)・DefectType列挙値の戻り値形式(既知リスク2)・
   `ATTR_DURATION`の実際の単位(既知リスク5)を実機で確認 → 残作業(接続自体はOK、
   返ってきたデータの中身の確認が次のステップ)

**実機接続確認済み(2026-07-21)**: `sql_host`/`sql_user`/`sql_password`/`sql_database`/
`sql_linked_server`を設定し、`python -c "import pi_client; print(pi_client.get_available_defect_types())"`
でPI(pymssql経由のOPENQUERY)への接続に成功した。

デバッグで判明した`config.txt`記述時の重要な注意点(**このファイルはconfigparser(INI)
が読むプレーンテキストであり、Pythonコードとしては評価されない**):
- 値をダブルクォート`"..."`で囲むと、クォート文字自体が値に含まれてしまう
  (例: `sql_host = "t183piakpv1"` → 実際の値は`"t183piakpv1"`というクォート付き文字列になり、
  接続先ホスト名として無効になって`Adaptive Server is unavailable`エラーが発生した)
- `r"..."`(Pythonのraw文字列プレフィックス)も同様に、`r`と`"`がそのまま値に含まれる
- 値は**クォートなし・プレフィックスなしでそのまま**書くこと(例: `sql_password = P@ss123`)
- バックスラッシュを含む値(例: `DOMAIN\username`)を`repr()`で確認すると`\\`と2つ表示されるが、
  これは表示上の仕様であり実際のデータは1つのまま(`print()`で確認すれば1つに見える)

**Box連携はユーザー指示により後回し(2026-07-21)**: `box_jwt_config.json`/`folder_id`等が
未設定でもアプリはクラッシュしない(写真パネルにエラーメッセージが出るのみで、
欠点マップ・トレンド・製品位置は正常動作)ことを実機相当の環境で確認済み。
Box Developer Console設定・フォルダID取得は着手不要、PI接続確認を優先する。

### B. 次の実装タスク(優先順、Claude Codeで対応)

1. PI接続は確認済み。`get_available_defect_types()`が返す欠点種類の中身(文字列として
   正しく読めるか=既知リスク2)、タイムゾーンのずれ(既知リスク1)、`duration_unit`の
   妥当性(既知リスク5)を、実際のデータを見ながら確認・調整する
2. (Box対応再開後)`/api/photos` を excel_photos ベースに切り替え。
   `get_photos()`は`{id, name, timestamp}`のみ返す設計のため、サムネイル表示には
   `index.json`の`path`(ローカル保存先)を使う経路を`app.py`側に追加する必要あり
   (現状の`/api/photo_thumbnail/<id>`はBox APIから取得する前提なので、ローカルファイルを
   返すエンドポイント、または`get_photos`の戻り値にpathを含める設計変更を検討)
3. (Box対応再開後)フィルターパネルに「写真を今すぐ同期」ボタン + `POST /api/photos/sync`
   (`excel_photos.sync_cache()`を呼ぶ)追加
4. 必要ならPyInstallerでのスタンドアロン化(ユーザーは過去にカメラビューアで
   .specカスタマイズの経験あり。ただしFlaskアプリなので単純なexe化より
   バッチ起動+ブラウザ自動オープンの方が簡単かもしれない)

## 開発環境メモ

`boxsdk`はPyPI上のバージョン10.0以降、パッケージ名はそのままに実体が別物のSDK
(`box_sdk_gen`)へ移行しており、`from boxsdk import JWTAuth, Client`(現行コードの前提)が
壊れる。`requirements.txt`は`boxsdk[jwt]>=3.9,<10`に固定済み。

## ユーザーの好み・進め方

- 完成品を一括で渡すより、**対話しながら段階的に作る**進め方を好む
- 指摘は率直・簡潔。過剰な装飾や冗長な説明は不要
- ビジュアルの確認は画像(スクリーンショット)ベースで行うと話が早い
  (本プロジェクトではPlaywright+ダミーデータのmock.htmlでモックアップ画像を生成した)
