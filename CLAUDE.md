# CLAUDE.md — 欠点モニタリングダッシュボード 引き継ぎ資料

## 現在地点(2026-07-22時点、次のチャットで最初に読む部分)

- **Git**: `master`ブランチ、最新コミット`0155031`まで push済み・作業ツリークリーン。
  リポジトリ: `git@github.com:Oyabu054/snap_dashboard.git`
- **exe化は完了・実機確認済み**: `pyinstaller SnapMonitor.spec`でのビルド・起動・PI接続を
  ユーザー実機で確認済み。複数PC(最大5台程度)からの閲覧もコード変更不要で対応可能
  (README「8.」参照)
- **アプリの機能は一通り完成・実機確認済み**: PI接続・欠点マップ(スナップ・LOBB・失透・
  Gross/Net常時表示)・時間帯別トレンド(発生分数+CST回転数/厚み/絶対真空圧の重ね描画、
  LOBB発生個数トレンドへのタブ切り替え)・製品位置表示、いずれも実機で動作確認済み。
  タイムゾーンのずれ(SQL問い合わせ範囲・フロントエンド描画の両方)も原因確定・修正済み。
  Box連携は情シス却下によりUI非接続のまま保留中
- **直前の作業: パフォーマンス改善**: 属性追加に伴い動作が重くなった件を調査・対応済み
  (`_fetch_element_raw()`の短時間キャッシュ・`threaded=True`・SQL属性絞り込み・
  Gross/Netの10分間隔への間引き・Plotlyの`scattergl`化)。詳細は下記
  「パフォーマンス対応」「Gross/Netの10分平均化」参照
- **次にやるべきこと: 本番向けサーバー(waitress)への移行**。ユーザー承認済み・
  次のセッションで着手予定。詳細な作業計画は下記「waitressへの移行(次の作業)」参照。
  実機作業(ビルド・起動・複数PC接続確認)はユーザー側対応
- ユーザー・私(Claude Code)ともにこの1セッションで多数のやり取りを経ているため、
  過去の判断理由(なぜこうしたか)は本ドキュメント内に極力残してある。迷ったら該当セクションを参照

## waitressへの移行(次の作業)

現状はFlask開発用サーバー(`app.run(..., threaded=True)`)で運用中。ユーザーから
本番向けWSGIサーバー(`waitress`)への移行を依頼された(2026-07-22)。以下の理由で
Flask開発用サーバーは本番運用に向かないため:
- Werkzeugの開発用サーバーは公式に「本番環境で使うな」と明記されている
- `threaded=True`でスレッド生成は可能だが、長時間稼働・複数PCからの同時アクセスに
  対しては`waitress`のようなスレッドプール実装の方が安定する

**今回のパフォーマンス改善(キャッシュ・属性絞り込み・Gross/Net間引き)とは独立した対応**であり、
サーバー切り替え自体はどちらかというと安定性・信頼性の向上が主目的(体感速度の改善は
既に別対応で完了済み)。

### 作業手順(想定)

1. `requirements.txt`に`waitress>=3.0`を追加(実行時に必要な依存関係として、
   `pyinstaller`のようなビルド専用ではなく通常のセクションに置く)
2. `app.py`の`if __name__ == "__main__":`ブロックを変更:
   ```python
   from waitress import serve
   ...
   if __name__ == "__main__":
       threading.Timer(1.0, _open_browser).start()
       serve(app, host=config.FLASK_HOST, port=config.FLASK_PORT, threads=8)
   ```
   - ブラウザ自動オープンの`threading.Timer`はWSGIサーバーの選択と独立なのでそのまま流用可
   - `debug=False`や`app.run()`固有の引数は不要になる(waitressに`debug`の概念はない)
   - `threads`はデフォルト4。複数PC(最大5台)+1回の操作で最大8並列APIリクエストが飛ぶ
     ことを踏まえ、8前後を目安に調整(要実機での体感確認)
3. `SnapMonitor.spec`の`hiddenimports`に`collect_submodules("waitress")`を追加
   (pymssql/boxsdkと同様、PyInstallerの静的解析だけでは検出しきれない依存がある可能性)。
   既存行:
   ```python
   hiddenimports = collect_submodules("pymssql") + collect_submodules("boxsdk")
   ```
   を
   ```python
   hiddenimports = collect_submodules("pymssql") + collect_submodules("boxsdk") + collect_submodules("waitress")
   ```
   に変更
4. `README.md`の該当箇所を更新:
   - 「3. 実行」: `python app.py`で起動する説明はそのままだが、内部でwaitressが使われる旨を追記
   - 「7. exe化して配布する」: 特記事項なし(exe化手順自体は変わらない)
   - 「8. 複数PCから閲覧する」: 「サーバーはFlask開発用サーバー(`app.run()`)のまま運用する
     方針」という記述をwaitressに置き換え
5. `test_app.py`はFlaskの`app.test_client()`を使っておりWSGIサーバーの選択とは無関係のため、
   影響なく動作する想定(念のためテスト実行で確認)
6. 実機で`pyinstaller SnapMonitor.spec`→ビルド→起動→PI接続→複数PCからのアクセス、を
   再確認(ユーザー側対応)

### 確認しておきたい点(次のセッションでユーザーに聞く)

- `threads`の初期値(上記は8を仮置き)でよいか、閲覧PC数などから別の値にすべきか
- コンソールウィンドウの扱い(`SnapMonitor.spec`の`console=True`は現状維持のまま
  トラブルシューティング用に残すか)

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
| 左 | フィルターパネル: 開始/終了日時、表示範囲絞り込みスクロールバー(デュアルハンドル、データ再取得なしで両チャートをズーム)、スナップ種類チェックボックス(全選択/全解除ボタン付き)、適用ボタン、クイック選択(1h/8h/24h/7d)、下部に「ストリエboxリンク」(外部Boxフォルダへのリンク、後述) |
| 中央上 | スナップマップ: X=日時(右が最新)、Y=位置0〜210(**上=左側=大きい値、下=右側**)。欠点は発生時刻→+継続時間の**横線分**で表示(マーカーサイズでの表現は却下済み)。ホバーで種類/発生時刻/位置/継続時間のツールチップ表示。Gross/Net幅の凡例は非表示(ユーザー指示で削除済み) |
| 中央下 | 時間帯別トレンド: 1時間ごとの**発生分数**(継続時間の合計・分)のスナップ種類別積み上げ棒グラフ。件数ではない点に注意。マップとX軸(時間)範囲を明示的に同期しており、縦方向にズレず表示される |
| 右上 | リアルタイム更新トグル(30秒ポーリング、終了日時を現在時刻に更新して再取得) |

**画面表示は「欠点」ではなく「スナップ」と表記する(2026-07-21変更、ユーザー指示)**。
タイトル・見出し・ラベル・topbarのeyebrow(`DEFECT MONITOR`→`SNAP MONITOR`)が対象。
**内部のコード(変数名・関数名・API等、例: `defect_type`/`get_defects()`)は変更していない**、
画面表示テキストのみの変更。

**スナップ種類の除外**: `NET切れ`/`RIP`/`その他`/`不明`は実際のスナップ(欠点)データでは
ないため、`pi_client.py`の`EXCLUDED_DEFECT_TYPES`定数で常時除外している
(`defect_types`フィルター指定の有無によらず、`get_defects()`/`get_available_defect_types()`
の両方で除外)。チェックボックス一覧にも表示されない。

**画面右側の現場写真パネルは廃止(2026-07-21)**: 情シスへのBox Custom App承認依頼が却下されたため、
Box API経由の写真表示は撤回。代わりに左パネル下部に外部Boxフォルダへの直リンク
「ストリエboxリンク」(`https://agc.ent.box.com/folder/354740164678`)を設置し、
ユーザーが手動でBoxを開いて閲覧する運用に変更した。

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
1. 発生時刻 (`ATTR_START_TIME`) = `スナップ入力操作適用年月日`(2026-07-22変更。旧`スナップクリア
   操作適用年月日`はオペレーターのクリア操作時刻を指すため、まだクリアされていない直近の
   スナップが種類/継続時間側とマージできずフィルターで消える不具合があり、入力操作時刻に変更した)
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
- **2026-07-21時点でUIからは未接続・保留中**: 情シスへのBox Custom App承認依頼が
  却下されたため、`/api/photos`をexcel_photosベースに切り替える作業は棚上げ。
  コード自体(`excel_photos.py`/`box_client.py`のBox関連関数、`app.py`の
  `/api/photos`・`/api/photo_thumbnail/<id>`)は削除せず残しているが、フロントエンド
  (`dashboard.js`/`index.html`)からは呼び出していない。承認が得られた場合や
  別の認証方式(クライアント資格情報許可など)が使えるようになった場合に再開する

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
├── test_app.py         # app.py(Flaskルート)のテスト
├── test_config.py      # config.pyのBASE_DIR解決ロジックのテスト(sys.frozenをモック)
├── SnapMonitor.spec    # PyInstaller単一exeビルド設定(exe化。README「7.」参照)
├── requirements.txt
├── README.md           # 人間向けセットアップ手順(テスト実行方法・exe化・複数PC閲覧・今後のタスクも記載)
├── templates/index.html
└── static/
    ├── css/style.css   # 白背景テーマ。デザイントークンは:rootのCSS変数に集約
    └── js/dashboard.js # Plotly描画、フィルター、ポーリング
```

このリポジトリはGit管理下にあり、GitHub(`git@github.com:Oyabu054/snap_dashboard.git`)に
push済み。`config.txt`等の機密情報は`.gitignore`で除外されている(Git管理には含まれない)。

## 実装済みの細かい仕様・判断

- **`merge_asof`はまばらな属性には使えない(2026-07-22判明)**: LOBB位置をGross/Netと同じ
  `merge_asof(tolerance=2s)`でマップに表示しようとしたところ「マップに表示されない」不具合が
  発生。実機確認したところGross/Netは約28時間で1681件連続サンプリングされているのに対し、
  LOBB位置はわずか2件と極端にまばらで、Grossの連続タイムスタンプと2秒以内で一致することが
  ほぼなかった。失透と同様、`get_lobb_points()`で独立した点として取得する方式に修正済み
  (`get_product_position()`にはもう`lobb_position`列を含めない)。**教訓: 新しい属性を
  マップに追加する際は、まず実機でサンプリング頻度(1日あたり何件記録されるか)を確認し、
  Gross/Netのように連続的なら`merge_asof`で線として、失透・LOBBのようにまばらなら
  独立取得の点として扱うこと**
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
- スナップ種類の配色は`dataviz`スキルで検証済みの8色固定パレット
  (青/緑/マゼンタ/黄/アクア/オレンジ/紫/赤、CVD安全性を`validate_palette.js`で確認済み)。
  フィルターのチェックボックスにも色スウォッチを表示
- X軸(日時)は`tickformat: '%-m/%-d %H:%M'`・`nticks: 20`で共通化。マップとトレンドの
  X軸範囲が独立に自動計算されると縦方向にズレて見えるため、`applyFilter()`で確定した
  `[start, end]`を両チャートの`xaxis.range`に明示指定して同期している
- **プロット領域の幅も両チャートで一致させる必要がある(2026-07-22追記)**: トレンド側は
  CST回転数・厚み・絶対真空圧の右軸をPlotlyの`autoshift`で自動配置しているため、
  実際に描画される余白(margin)が指定値通りになるとは限らない。`margin.r`を両チャートに
  同じ値を渡すだけでは幅がズレる場合があったため、`applyFilter()`で**先にトレンドを
  描画してから**`document.getElementById('trendChart')._fullLayout.margin`で実際に
  確定した余白を読み取り、その値をそのままスナップマップ側の`margin`に適用する方式に変更した
  (`renderDefectMap`は`rightMargin`という数値ではなく`margin`オブジェクトを受け取る)
- トレンドの棒グラフは`width: 60*60*1000`(1時間分のミリ秒)で幅を固定。Plotlyはデータ点の
  間隔から幅を自動推定するため、表示期間が短くバー本数が少ないと実際の1時間からズレて見えていた
- 期間絞り込みスクロールバー(左パネル)はPlotly標準のrangeslider(マップ下)を廃止し、
  オーバーラップさせた2つの`<input type=range>`によるデュアルハンドルスライダーで実装。
  データの再取得はせず、両チャートの`xaxis.range`を`Plotly.relayout`でズームするのみ
  (フィルター適用のたびに全期間表示へリセットされる)

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

1. **DefectTypeが列挙値(Enumeration Set)の場合**、`ar.Value`の戻り値が
   期待通りの文字列でない可能性あり。`get_available_defect_types()` の動作確認
2. **データ量**: 7日間表示で欠点数が数千件を超える場合、線分方式(1欠点3点)の
   描画性能とAPI応答サイズを確認。必要なら間引きも検討(WebGL化は下記対応済み)
3. **旧形式.xls**: Excel写真抽出でxlsが混在する場合openpyxl不可。
   ユーザーは過去にxlrd+openpyxlの変換スクリプトを作成済みなので流用可
4. **`ATTR_DURATION`(スナップ継続時間)の実際の単位**が秒/分/ミリ秒のいずれか未確認。
   `config.txt`の`duration_unit`で調整

**パフォーマンス対応(2026-07-22、属性追加に伴う動作の重さの改善)**: CST回転数・厚み・
絶対真空圧・LOBB・失透を追加した結果、1回の「適用」操作で最大8並列のAPIリクエストが
飛ぶようになったが、各リクエストが独立して`_fetch_element_raw()`(スナップ要素の
全属性・全件をSELECT)を実行しており、同じデータを最大8回重複取得していたことが
主な原因と判明。以下2点で対応:
- `pi_client._fetch_element_raw()`に短時間(`_RAW_CACHE_TTL_SECONDS`=10秒)キャッシュを
  追加。同じ(element, start, end)への呼び出しはキャッシュを返す。キーごとの
  `threading.Lock`でsingle-flight化(同時に同じキーで呼ばれた場合、後続は待たされて
  最初の1回だけが実際にSQLを叩く)。テストでは`_configure`フィクスチャで
  `pi_client._raw_cache.clear()`しテスト間の汚染を防止
- `app.py`の`app.run()`に`threaded=True`を追加。Flask開発用サーバーはデフォルトで
  シングルスレッドのため、フロントエンドが並列リクエストを送ってもサーバー側で
  直列処理されていた
- 加えて`dashboard.js`側のPlotlyトレース(欠点線分・Gross/Net/LOBB/失透)を
  `type: 'scatter'`から`type: 'scattergl'`(WebGL)に変更し、長期間表示時の
  クライアント側描画性能も改善
- **属性絞り込み(2026-07-22追加)**: 「スナップ」要素にはアプリで使っていない属性も
  残っている(実機確認: `スナップ入力操作適用直`・`スナップ入力操作適用ＡＧＣ日付`・
  `スナップ入力効果範囲`・`スナップ入力欠点サイズ`・`スナップクリア操作適用年月日`・
  `スナップクリア操作適用ＡＧＣ日付`等、旧`ATTR_START_TIME`だった`スナップクリア操作適用年月日`
  も含む)。`_build_sql()`に`attribute_names`引数を追加し、`a.Name IN (...)`で
  絞り込めるようにした。`_fetch_element_raw()`は`_used_attribute_names()`
  (実際に使っている14属性の一覧を返す関数)を渡して呼ぶ。関数にしているのは、
  テストがpi_clientのATTR_*定数をmonkeypatchすることがあり、モジュール読み込み時に
  リストを固定するとmonkeypatchした値が反映されないため。実機確認では全18属性
  10,674行→14属性10,319行(約355行減、Gross/Net/CST回転数/絶対真空圧が行数の大半を
  占めるため削減率は小さい)。新しい属性をpi_client.pyで使うようになったら
  `_used_attribute_names()`にも追加すること

**Gross/Netの10分平均化(2026-07-22追加)**: Gross/Netは1分間隔で記録され、
全体行数の約65%(4属性×1681行=6,724/10,319行、実機確認)を占める。SQL側での間引き
(`DATEPART(minute, ar.TimeStamp) % 10 = 0`のような絞り込み)はPIのリンクサーバーが
対応しておらずエラーになったため断念(実機で確認済み)。また実測では**クエリ時間は
行数よりも接続・準備の固定オーバーヘッド(約0.6秒)に支配されている**ことが分かった
(0行→1681行でほぼ同じ0.6秒台、1681行→10,317行で0.65秒→1.45秒)ため、SQL取得時間への
効果は限定的と判断。代わりに`get_product_position()`内で`_resample_10min_mean()`
(pandasの`resample("10min").mean()`)を使い、取得後にGross/Netだけ10分平均に間引いて
返すようにした。SQLクエリ自体(行数)は変わらないが、`/api/product_position`の
レスポンスサイズとPlotlyでの描画点数は大幅に減る(実機確認: 約28時間で1,681行→169行)。
CST回転数は既存の`_fetch_10min_average_trend()`で同様の10分平均化済み、
厚み・LOBB・失透はそもそも記録頻度が低い(実機確認: 28時間で数件〜数十件)ため対象外。

(旧リスク「属性名はすべて仮名」は2026-07-21のPI System Explorer確認で解消済み)

**タイムゾーンのずれは2026-07-22に原因確定・修正済み(2箇所)**: 症状は「直近のスナップが
取得できない」→(1つ目の修正後)「スナップの表示だけ9時間ズレる」という2段階で発覚。
このWSL環境から実PIサーバーへの接続に成功したため、実データで直接検証・確認済み。

1. **バックエンドへのクエリ範囲がズレる**: `dashboard.js`の`applyFilter()`が日時入力欄の
   ローカル時刻(JST想定)を`new Date(...).toISOString()`でUTCに変換してから送信していたため、
   バックエンドのSQLクエリ(`ar.TimeStamp BETWEEN`、タイムゾーン変換なしで文字列を組み立てる)が
   実際には**9時間早い範囲**をPIに問い合わせてしまっていた。午後〜夜間のスナップが軒並み
   欠落する形で症状が出ていた。修正: `toISOString()`変換をやめ、`datetime-local`の値
   (タイムゾーン情報を持たないローカル時刻文字列)をそのまま送信
   (`const start = startLocal; const end = endLocal;`)
2. **フロントエンドの描画がズレる**: 1つ目を直すとデータ欠落は解消したが、スナップの
   マップ・トレンド棒グラフだけ表示が9時間ズレる症状が新たに顕在化した。原因は
   `buildDurationSegments()`(マップの線分)・`buildHourlyTrendByType()`(トレンドの
   時間バケットキー)・`applyPeriodSliderZoom()`(期間スライダー)が、Dateオブジェクトを
   `.toISOString()`で文字列化し直しており、これがUTC変換されるためPlotlyがUTCとして解釈し
   9時間ズレて表示されていた。CST回転数等はAPIから返るタイムゾーン情報のないローカル時刻
   文字列をそのままPlotlyに渡している(Dateオブジェクトへの変換を経由しない)ため影響を受けず、
   スナップ関連の描画だけがこの問題の対象だった。修正: `toLocalISOString()`
   (タイムゾーン情報を持たないローカル時刻文字列を返す関数)を新設し、上記3箇所の
   `.toISOString()`を置き換え

`get_defects()`で位置・継続時間・種類・発生時刻の4属性は同一タイムスタンプで記録されており、
`merge_asof`のマージ自体は問題なかった(2秒の許容誤差で十分)。

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
2. DefectType列挙値の戻り値形式(既知リスク1)・`ATTR_DURATION`の実際の単位(既知リスク4)
   を実機で確認 → 残作業(接続自体はOK、返ってきたデータの中身の確認が次のステップ。
   タイムゾーンのずれは2026-07-22に原因確定・修正済み、上記「既知のリスク」参照)

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

**Box連携は情シス却下により保留(2026-07-21更新)**: 当初はJWT Custom Appでの
API連携を予定していたが、情シスへの承認依頼が却下された。`box_jwt_config.json`/
`folder_id`等が未設定でもアプリはクラッシュしない(実機相当の環境で確認済み)ため、
UI上の写真パネルは廃止し、左パネル下部に外部Boxフォルダへの直リンク
「ストリエboxリンク」を設置する方式に変更した(上記「画面右側の現場写真パネルは廃止」参照)。
`excel_photos.py`/`box_client.py`のBoxコードは削除せず保持。承認が得られた場合や
クライアント資格情報許可(CCG)等の別方式が使えるようになった場合に、下記タスクを再開する。

**exe化を試行 → revert → 原因はおそらく古いプロセスと判明・再適用(2026-07-21)**:
`SnapMonitor.spec`(PyInstaller単一exeビルド設定)・`app.py`への起動時ブラウザ自動オープン
(`threading.Timer`+`webbrowser.open`、`debug=False`に変更)・`config.py`への`BASE_DIR`
(exe化時はexe自身のフォルダを基準に`config.txt`等を絶対パス解決)を実装しコミット
(`8e2283e`)したが、ユーザーの実機で以下の再現しない不具合が発生:

- 症状: ブラウザ上で「スナップ種類」読み込みが失敗し、`(20009, ... Adaptive Server is
  unavailable ... (YOUR_SQL_SERVER_HOST))`というエラー(config.txt.exampleのプレースホルダ)
  が表示された
- ただし`python -c "import config; print(config.BASE_DIR); print(repr(config.SQL_HOST))"`
  を**同じフォルダ・同じターミナルセッションで**実行すると、`BASE_DIR`もSQL_HOSTの値も
  正しく表示され、`python app.py`自体もエラーなく起動した
- この「診断コマンドでは正しいのに、ブラウザ経由のAPIリクエストだけ古いプレースホルダの
  エラーになる」という矛盾から、**ポート5000を握ったままの古いプロセス(以前のexe起動や
  `python app.py`の多重起動)が残っていて、ブラウザが実際にはそちらに接続している**可能性を
  疑った
- ユーザー指示により、原因が整理できるまで`git revert 8e2283e`(コミット`b596215`)で
  exe化関連の変更は一旦すべて取り消し
- **2026-07-21 追記(切り分け結果)**: ユーザーがタスクマネージャーで確認したところ、
  `SnapMonitor.exe`/`python.exe`の重複起動は見当たらなかった。それでも一度この状態で
  再テストした際はうまくいかず、**PCを再起動してから改めてクリーンな状態でテストしたところ
  成功した**。「タスクマネージャー上は多重起動が見えないが、再起動で直った」ことから、
  完全な原因確定はできていないものの(タスクマネージャーに出ない何らかのプロセス/ソケットの
  残存、OS側のポート開放待ち状態など)、**exe化コード自体(`8e2283e`の内容)がバグの原因では
  なかった可能性が高い**と判断し、同じ内容を`git revert b596215`で再度復元(`b995f09`)。
  併せて`config.py`の`BASE_DIR`解決ロジックに単体テスト(`test_config.py`)を追加(45件全て
  パス確認済み、実行はscratch venvで`pip install -r requirements.txt`後に`pytest`)
- **再発した場合の切り分け方**: 同様の「診断コマンドは正しいのにブラウザ経由だけ古い値/エラーに
  なる」症状が再発したら、まずタスクマネージャーでの確認に加えて**PC再起動**を先に試す
  (今回はこれで解消した)。それでも直らない場合は、`netstat -ano | findstr :5000`
  (PowerShell)等でポート5000を握っているプロセスのPIDを直接特定する方法も有効

### B. 次の実装タスク(優先順、Claude Codeで対応)

1. **exe化コードは再適用済み(`b995f09`)、ただし未push**: ユーザーの確認が取れ次第
   `git push`する。その後ユーザー実機で`pyinstaller SnapMonitor.spec`→
   `dist/SnapMonitor.exe`起動→ブラウザ自動オープン→PI接続成功、を再確認してもらう
2. **複数PC(最大5台程度)からの閲覧に対応(2026-07-21追加)**: `config.py`の`FLASK_HOST`は
   既に`config.txt`の`[flask] host`から読む設計だったため、コード変更は不要と判断。
   ホストPC1台の`config.txt`で`host = 0.0.0.0`に変更するだけで、同一LAN上の他PCから
   `http://<ホストPCのIP>:5000/`で閲覧可能。手順・注意点はREADME「8. 複数PCから閲覧する」
   に追記済み。当初はFlask開発用サーバー(`app.run()`)のまま運用する方針だったが、
   2026-07-22にユーザーから本番向けWSGIサーバー(`waitress`)への移行を依頼された。
   詳細は本ドキュメント冒頭「waitressへの移行(次の作業)」参照。
   ホストPC側のWindowsファイアウォールでのポート開放は実機操作のためユーザー側対応
3. PI接続は確認済み。`get_available_defect_types()`が返す欠点種類の中身(文字列として
   正しく読めるか=既知リスク1)、`duration_unit`の妥当性(既知リスク4)を、
   実際のデータを見ながら確認・調整する(タイムゾーンのずれは2026-07-22に修正済み)
4. (Box連携再開時)`/api/photos` を excel_photos ベースに切り替え。
   `get_photos()`は`{id, name, timestamp}`のみ返す設計のため、サムネイル表示には
   `index.json`の`path`(ローカル保存先)を使う経路を`app.py`側に追加する必要あり
   (現状の`/api/photo_thumbnail/<id>`はBox APIから取得する前提なので、ローカルファイルを
   返すエンドポイント、または`get_photos`の戻り値にpathを含める設計変更を検討)
5. (Box連携再開時)フィルターパネルに「写真を今すぐ同期」ボタン + `POST /api/photos/sync`
   (`excel_photos.sync_cache()`を呼ぶ)追加

## 開発環境メモ

`boxsdk`はPyPI上のバージョン10.0以降、パッケージ名はそのままに実体が別物のSDK
(`box_sdk_gen`)へ移行しており、`from boxsdk import JWTAuth, Client`(現行コードの前提)が
壊れる。`requirements.txt`は`boxsdk[jwt]>=3.9,<10`に固定済み。

## ユーザーの好み・進め方

- 完成品を一括で渡すより、**対話しながら段階的に作る**進め方を好む
- 指摘は率直・簡潔。過剰な装飾や冗長な説明は不要
- ビジュアルの確認は画像(スクリーンショット)ベースで行うと話が早い
  (本プロジェクトではPlaywright+ダミーデータのmock.htmlでモックアップ画像を生成した)
