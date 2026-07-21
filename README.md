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

ファイル名や拡張子ではなく、本文の構造で自動分類します。ショートカット側で同じファイル名になったり、拡張子が `.html` になったりしても、中身がJSONであれば `data_type` で読み込めます。旧形式の `courseanalysis` JSONも互換入力として利用できます。

地方JSONでは以下を検証します。

- 必須3種類が揃っている
- `data_type` が `entry` / `speed` / `courseanalysis` のいずれか、またはコース分析HTMLとして判定できる
- 3ファイルの `race_id` が一致している
- 出馬表／タイム指数の `horses` が空ではない
- 出馬表／タイム指数の頭数が一致している
- 出馬表／タイム指数の馬番セットが一致している
- コース脚質分析の `running_styles` が空ではない
- コース脚質HTMLでは `score1` のChart.jsグラフから脚質ラベル、1着率、2着率、3着率、着外率を抽出できる

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
