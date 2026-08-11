# Keiba AI Mobile

iPhone Safari から地方競馬・中央競馬の予想結果を確認し、スマホ向けPNGとして保存する Streamlit アプリです。

研究用Notebookは変更せず、Cloudでは `.ipynb` を実行しません。予想処理は Python モジュールへ移植したものを呼び出します。

## 現在できること

- 地方／中央の切替
- 地方競馬のショートカットJSONアップロード
- 地方競馬のHTML直接アップロード fallback
- 地方競馬の旧URL入力モード fallback
- 中央競馬のHTMLアップロード
- HTML／JSON自動分類
- Pythonモジュールによる予想実行
- `PredictionResult` 生成
- スマホ向け縦長PNG生成
- Streamlit上でPNG表示
- PNG保存
- 次レース用リセット

## 予想ロジック Ver4 / Ver3

画面上部の「予想ロジック」で、絶対評価のVer4と従来のVer3を切り替えられます。

- Ver4: 結果・払戻・レース内min/maxを使わない0〜100の `horse_score_v4` と、レース内順位の `race_rank_v4` を別々に生成
- Ver3: 従来Notebook移植ロジックをそのまま実行
- Ver4は元のVer3列を上書きせず、`*_v4` 列と監査情報をPredictionResultのコピーへ追加
- Ver4の買い判断は `BUY / LIGHT / WATCH / SKIP`、旧画面向けには `BUY / HOLD / SKIP` へ互換変換

保存済みPrediction Historyの回帰確認は次のツールで行えます。実着順JSONはVer4計算後にだけ結合されます。

```bash
python tools/analyze_ver4_regression.py prediction1.zip prediction2.zip \
  --results-json work/results.json \
  --output work/ver4_analysis
```

`work/` はGit管理外です。比較CSV、コンポーネントCSV、判断サマリー、監査Markdownが生成されます。

## フォルダ構成

```text
keiba_ai_mobile/
  streamlit_app.py
  app.py
  core/
    html_classifier.py
    jra_notebook_logic.py
    jra_predictor.py
    models.py
    nar_json_input.py
    nar_notebook_logic.py
    nar_predictor.py
    prediction_runtime.py
    version.py
  render/
    mobile_png.py
  assets/
  requirements.txt
  packages.txt
  README.md
  .gitignore
```

## 必要ライブラリ

```text
streamlit
pandas
beautifulsoup4
lxml
requests
pillow
numpy
```

## ローカル起動

```bash
cd keiba_ai_mobile
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Streamlit Cloud と同じ入口で確認する場合は以下です。

```bash
streamlit run streamlit_app.py
```

## 検証用HTMLの一括保存

検証データ作成用に、ローカルPCでログイン済みブラウザを使ってnetkeibaのHTMLを一括保存する補助ツールを用意しています。

Streamlit Cloudやアプリ本体から直接取得するものではありません。プレミアムページやログイン済みページを扱うため、必ず自分のPC上で、通常の閲覧に近い速度で実行してください。保存HTMLやブラウザプロファイルは `.gitignore` で除外しています。

### 初回準備

```bash
cd keiba_ai_mobile
pip install -r tools/requirements-collector.txt
python -m playwright install chromium
```

### 開催日だけで中央全レースの5種HTMLを保存

中央競馬は開催日だけ指定できます。指定日のレース一覧ページへアクセスし、画面に表示されているレースリンクだけを表示順に巡回してHTML収集を開始します。

例：`2026-07-26` を指定すると、その日に開催されている福島・新潟・札幌などの全レースを対象にします。

```bash
python tools/netkeiba_html_collector.py ^
  --mode jra ^
  --date 2026-07-26 ^
  --out collected_html
```

中央の既定保存対象は以下5種です。

- 競馬新聞
- 調教
- タイム指数
- 脚質分析
- レース結果

### race_id一覧から中央5種HTMLを保存

`race_ids.txt` にrace_idまたはrace URLを並べます。

```text
202610020810
https://race.netkeiba.com/race/speed.html?race_id=202610020811
```

以下を実行します。

```bash
python tools/netkeiba_html_collector.py ^
  --mode jra ^
  --race-ids-file race_ids.txt ^
  --out collected_html
```

### 地方HTMLを保存

```bash
python tools/netkeiba_html_collector.py ^
  --mode nar ^
  --race-ids-file race_ids.txt ^
  --out collected_html
```

地方の既定保存対象は以下4種です。

- 競馬新聞
- タイム指数
- 脚質分析
- レース結果

地方で出馬表も保存したい場合は、`--kinds` で明示します。

```bash
python tools/netkeiba_html_collector.py ^
  --mode nar ^
  --race-ids-file race_ids.txt ^
  --kinds newspaper,speed,style,result,shutuba ^
  --out collected_html
```

### レース一覧ページの表示順で保存

開催日のレース一覧URLを直接指定することもできます。この場合も、HTML本文全体からrace_idを拾うのではなく、一覧ページに表示されているレースリンクだけを表示順に巡回します。

```bash
python tools/netkeiba_html_collector.py ^
  --mode jra ^
  --list-url "https://race.netkeiba.com/top/race_list.html?kaisai_date=20260720" ^
  --out collected_html
```

### ログインが必要な場合

初回やセッション切れ時はブラウザがログインページを表示します。ブラウザ上でログインを完了し、ターミナルへ戻ってEnterを押すと続きから保存します。

ログイン状態は `.collector_profile/` に保存されます。このフォルダはcookie等を含む可能性があるため、GitHubへpushしないでください。

### 保存先

既定では以下のように保存されます。

```text
collected_html/
  jra/
    202610020810/
      202610020810_newspaper.html
      202610020810_oikiri.html
      202610020810_speed.html
      202610020810_style.html
      202610020810_result.html
  manifest_YYYYMMDD_HHMMSS.csv
```

既存ファイルはスキップします。再取得したい場合は `--overwrite` を付けます。

## スマホからの利用手順

1. iPhone Safariでアプリを開く
2. 地方／中央を選ぶ
3. 地方はiPhoneショートカットで保存した3つのJSONをまとめて追加する
4. 中央は必要HTMLをまとめて追加する
5. 認識結果を確認する
6. 「予想する」を押す
7. 生成されたPNGを確認する
8. 「PNGを保存」から保存する
9. 次のレースは「次のレースを予想」でリセットする

## 入力方法

### 地方競馬

通常は、iPhoneショートカットで保存した以下3ファイルをまとめてアップロードします。

| ファイル | 判定方法 | 内容 |
|---|---|---|
| 出走表JSON | `data_type = "entry"` | 馬番、馬名、性齢、斤量、騎手、馬体重、単勝オッズ、人気など |
| タイム指数JSON | `data_type = "speed"` | 最高指数、5走平均、距離指数、コース指数、近3走指数など |
| コース脚質分析HTML | HTML本文の `mode=courseanalysis` / `cid=1` / `score1` | コースの脚質傾向 |
| 競馬新聞HTML | `newspaper.html` / `競馬新聞` / `nar.netkeiba.com` | entry JSONが無い場合に出走表相当データを生成 |

ファイル名や拡張子ではなく、本文の構造で自動分類します。ショートカット側で同じファイル名になったり、拡張子が `.html` になったりしても、中身がJSONであれば `data_type` で読み込めます。旧形式の `courseanalysis` JSONも互換入力として利用できます。
entry JSONがある場合はentryを優先します。entry JSONが無い場合は、地方競馬新聞HTMLから馬番、馬名、horse_id、枠番、脚質、騎手、斤量、馬体重、人気、オッズ、調教師、所属などを抽出してentry相当データを生成します。

地方JSONでは以下を検証します。

- 必須3種類が揃っている
- `entry` または `newspaper HTML`、`speed`、`courseanalysis` が揃っている
- `data_type` が `entry` / `speed` / `courseanalysis` のいずれか、またはコース分析HTML/競馬新聞HTMLとして判定できる
- 3ファイルの `race_id` が一致している
- 出馬表／タイム指数の `horses` が空ではない
- 出馬表／タイム指数の頭数が一致している
- 出馬表／タイム指数の馬番セットが一致している
- コース脚質分析の `running_styles` が空ではない
- コース脚質HTMLでは `score1` のChart.jsグラフから脚質ラベル、1着率、2着率、3着率、着外率を抽出できる
- コース全体の脚質成績は `running_styles` として保持し、各馬の脚質は `horse_number` ごとの `running_style` として別管理する
- 各馬の `running_style` とコース全体の脚質成績を照合し、既存の脚質勝率・連対率・複勝率の評価へ反映する

JSONを作れない場合は「詳細設定：HTMLを直接アップロード」から、以下のHTMLをまとめて追加できます。

- 出馬表HTML
- タイム指数HTML
- 脚質分析HTML

旧URL入力モードも詳細設定内に残しています。ただし、Streamlit Cloudからnetkeibaのログイン済みページへアクセスできない場合があるため、標準運用はショートカットで保存したファイルのアップロード方式です。

### 中央競馬

中央競馬も、iPhone Safariでログイン済みページを保存したHTMLをまとめてアップロードします。Cloudからnetkeibaへ直接ログイン取得は行いません。

- タイム指数HTML
- 競馬新聞HTML
- 脚質分析HTML
- 調教HTMLは任意反映

競馬新聞コメントや調教情報が一部の馬で欠けていても、必須HTMLが揃っていれば予想は継続します。調教HTMLを追加した場合は、認識結果に「調教」として表示され、既存中央ロジックへ渡されます。
## PNGレイアウト

PNGは幅1080pxを基準にしたスマホ向け縦長画像です。

表示順は以下です。

1. レース情報
2. 本日の結論
3. 今回の馬券構成
4. 簡易レース全体表
5. 馬評価（全頭）
6. 注目馬
7. AIレース考察
8. バージョン情報

PC版の横長詳細表をそのまま縮小せず、スマホで縦に読めるカード形式へ変換します。

## PredictionResult

予想モジュールから以下を受け取ります。

- `version`
- `created_at`
- `race_mode`
- `race_name`
- `race_info`
- `overall_table`
- `horse_evaluation`
- `attention_horses`
- `ai_race_review`
- `betting_structure`
- `source_files`
- `raw_output`

PNG生成側は `PredictionResult` を表示するだけで、新しい予想判断は行いません。

## Pythonモジュール化した予想処理

Cloud版ではNotebookを探したり実行したりしません。

- 地方：`core/nar_notebook_logic.py`
- 中央：`core/jra_notebook_logic.py`

主な入口は以下です。

- `predict_nar(html_files, file_names)`
- `predict_jra(html_files, file_names)`

地方JSON入力は `core/nar_json_input.py` で既存HTML解析に渡せる最小HTMLへ変換し、既存の `predict_nar()` を呼び出します。

処理の流れは以下です。

```text
地方JSONアップロード
↓
data_typeで自動分類
↓
race_id／馬番／頭数を検証
↓
既存解析用の最小HTMLへ変換
↓
PythonモジュールでAI予想
↓
PredictionResult
↓
PNG生成
```

## 日本語フォント要件

PNG生成には日本語フォントが必要です。以下の順で取得します。

1. `assets/fonts/NotoSansJP-Regular.ttf`
2. `KEIBA_AI_FONT_PATH` で指定したフォント
3. `assets/` または `assets/fonts/` 内のNoto系フォント
4. Google FontsからNoto Sans JPを初回のみ自動取得
5. OS上の日本語フォント
   - Meiryo
   - Yu Gothic
   - Noto Sans CJK / Noto Sans JP

DejaVu Sansは日本語グリフが無いため、PNG描画には使用しません。日本語フォントを取得できない場合のみ、PNG生成エラーを表示します。

Streamlit Cloudでは `packages.txt` の `fonts-noto-cjk` も利用します。

## Streamlit Cloud公開方法

1. このプロジェクトをGitHubへpush
2. Streamlit Community Cloudで `Create app`
3. 対象リポジトリとブランチを選択
4. Main file path に `streamlit_app.py` を指定
5. Deploy

Cloud用のEntrypointはリポジトリ直下の `streamlit_app.py` です。アプリ一覧に `core/__init__.py` などが表示される場合は、Streamlit CloudのApp settingsからMain file pathを `streamlit_app.py` に変更してください。

## Cloud公開前の注意

- `.ipynb` ファイルはCloud実行に不要です
- `KEIBA_NAR_NOTEBOOK_PATH` / `KEIBA_JRA_NOTEBOOK_PATH` は使用しません
- 取得したHTML／JSONはメモリ上で処理し、永続保存しません
- Streamlit Cloudからnetkeibaのログイン済みページは取得できないため、地方はJSONアップロード方式を標準にしています
- 保存オッズHTMLから組み合わせオッズを安定取得する機能は現在非表示です

## 既知の制限

- 地方JSONに含まれない情報は追加推測しません
- 地方JSONに馬ごとの脚質が無い場合、脚質は既存ロジック側で取得不可扱いになります
- 中央は現在URL方式ではなくHTMLアップロード方式です
- PNGは1枚にまとめるため、頭数や文章量が非常に多い場合は縦長になります
- 研究用Notebookで予想ロジックを更新した場合は、対応するPythonモジュールへの再移植が必要です

## Phase 1 レース俯瞰UI

通常画面は、レースサマリー、勢力図、馬別サマリーカード、詳細表の順に表示します。

- 能力ランク: 能力評価値を全レース共通の固定閾値で S/A/B/C/D に分類します。AI順位では判定しません。
- 能力帯: そのレース内で能力が近い馬をまとめる相対表示です。
- 勢いランク: 3走前、2走前、前走の指数推移を中心に S/A/B/C/D または判定保留で表示します。
- 調教評価: 中央のみ表示します。勢い判定では補助材料に留めます。

現在の暫定閾値は `core/form_rank.py` に集約しています。AI点、印、能力評価値、買い目ロジック、★最高指数の計算式は変更していません。

監査CSV / JSON / Markdownには、`ability_rank`, `ability_rank_reason`, `momentum_score`, `momentum_rank`, `momentum_reason`, `recent3_trend`, `recent3_slope`, `recent3_volatility`, `recent3_valid_count` を追加しています。
