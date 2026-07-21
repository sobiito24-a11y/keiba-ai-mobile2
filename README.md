# Keiba AI Mobile

iPhone Safari から netkeiba のレースURLまたは保存HTMLを入力し、Keiba AI の予想結果をスマホ向けPNGとして確認・保存するStreamlitアプリです。

現在のアプリは Cloud 対応版です。研究用Notebookは実行せず、Notebook内で使っていた予想処理をPythonモジュールへ移植して呼び出します。

## 現在できること

- 地方／中央の切替
- 地方競馬の出馬表URLから `race_id` を抽出
- 地方競馬の出馬表・タイム指数・脚質分析HTMLを自動取得
- URL取得失敗時の直接HTMLアップロード
- 中央競馬の直接HTMLアップロード
- HTML自動分類
- Pythonモジュールによる予想実行
- `PredictionResult` 生成
- スマホ向け縦長PNG生成
- Streamlit上でPNG表示
- PNG保存
- 次レース用リセット

研究用Notebook本体は変更しません。

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
    nar_notebook_logic.py
    nar_predictor.py
    prediction_runtime.py
    version.py
  render/
    mobile_png.py
  assets/
  requirements.txt
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

Streamlit Cloud と同じ入口で確認する場合は、以下でも起動できます。

```bash
streamlit run streamlit_app.py
```

同じWi-Fi上のiPhoneから使う場合は、PCのローカルIPアドレスでStreamlitへアクセスします。

```text
http://192.168.1.10:8501
```

## スマホからの利用手順

1. iPhone Safariでアプリを開く
2. 地方／中央を選ぶ
3. 地方は出馬表URLを1つ入力する
4. 中央は必要HTMLをアップロードする
5. 「予想する」を押す
6. 生成されたPNGを確認する
7. 「PNGを保存」から保存する
8. 次のレースは「次のレースを予想」でリセットする

## 入力方法

### 地方競馬

通常は出馬表URLを1つ入力します。

```text
https://nar.netkeiba.com/race/shutuba.html?race_id=202644072012
```

入力URLから `race_id` を抽出し、以下を自動取得します。

- 出馬表
- タイム指数
- 脚質分析

URL取得に失敗した場合は、「詳細設定：HTMLを直接アップロード」から以下をアップロードできます。

- 出馬表HTML
- タイム指数HTML
- 脚質分析HTML

### 中央競馬

現在は直接HTMLアップロード方式です。

- タイム指数HTML
- 競馬新聞HTML
- 脚質分析HTML
- 調教HTMLは任意

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

PC版の横長詳細表をそのまま縮小せず、スマホで読みやすいカード形式へ変換します。

## Pythonモジュール化した予想処理

Cloud版では `.ipynb` ファイルを探したり実行したりしません。

予想処理は以下のPythonモジュールから呼び出します。

- 地方：`core/nar_notebook_logic.py`
- 中央：`core/jra_notebook_logic.py`

これらは研究用NotebookのロジックセルをPython化したものです。`app.py` はNotebookパスや環境変数を参照しません。

主な入口は以下です。

- `predict_nar(html_files, file_names)`
- `predict_jra(html_files, file_names)`

処理の流れは以下です。

```text
URL取得またはHTMLアップロード
↓
HTML分類
↓
PythonモジュールでAI予想
↓
PredictionResult
↓
PNG生成
```

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

PNG生成側はこの `PredictionResult` を表示するだけで、新しい予想判断は行いません。

## 日本語フォント要件

PNG生成には日本語フォントが必要です。以下の順で自動検出します。

1. OS上の日本語フォント
   - Meiryo
   - Yu Gothic
   - Noto Sans CJK / Noto Sans JP
2. `assets/` 内の `.ttf` / `.otf` / `.ttc`
3. 見つからない場合はPNG生成エラーを表示

Streamlit Cloudで文字化けする場合は、`assets/` に日本語フォントを追加してください。

## Streamlit Cloud公開方法

1. このプロジェクトをGitHubへpush
2. Streamlit Community Cloudで `Create app`
3. 対象リポジトリとブランチを選択
4. Main file path に `streamlit_app.py` を指定
5. Deploy

Cloud用のEntrypointはリポジトリ直下の `streamlit_app.py` です。アプリ一覧に `core/__init__.py` などが表示される場合は、Streamlit CloudのApp settingsからMain file pathを `streamlit_app.py` に変更してください。

## Cloud公開前の注意

- `.ipynb` ファイルはCloud実行に不要です。
- `KEIBA_NAR_NOTEBOOK_PATH` / `KEIBA_JRA_NOTEBOOK_PATH` は使用しません。
- 取得したHTMLはメモリ上で処理し、永続保存しません。
- Streamlit Cloudからnetkeibaへアクセスできない場合は、直接HTMLアップロードを使います。
- 日本語フォントがCloud環境にない場合は、`assets/` へフォント追加が必要です。

## 既知の制限

- 地方のURL自動取得はnetkeiba側のアクセス制限やページ仕様変更で失敗する場合があります。
- 中央は現在、URL自動取得ではなくHTMLアップロード方式です。
- PNGは1枚にまとめるため、頭数や文章量が非常に多い場合は縦長になります。
- 保存オッズHTMLからの組み合わせオッズ解析は現在非表示です。
- 予想ロジックを研究用Notebookで更新した場合は、対応するPythonモジュールへの再移植が必要です。
