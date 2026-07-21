# Keiba AI Mobile

iPhone Safari から netkeiba のHTMLをアップロードし、Keiba AI の予想結果をスマホ向けPNGとして確認・保存するためのWebアプリです。

現在のバージョンは Phase3 / `APP_VERSION = 0.3.0` です。

## 現在できること

- 地方／中央の切替
- HTMLまとめてアップロード
- HTML自動分類
- 必須HTMLの不足チェック
- Notebook Bridge 経由で既存Notebookロジックを実行
- `PredictionResult` 生成
- スマホ向け縦長PNG生成
- Streamlit上でPNG表示
- PNG保存
- 次レース用リセット

研究用Notebook本体は変更しません。

## フォルダ構成

```text
keiba_ai_mobile/
  app.py
  core/
    html_classifier.py
    jra_predictor.py
    models.py
    nar_predictor.py
    notebook_bridge.py
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

## ローカル起動方法

```bash
cd keiba_ai_mobile
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

同じWi-Fi上のiPhoneから使う場合は、PCのローカルIPアドレスでStreamlitへアクセスします。

例：

```text
http://192.168.1.10:8501
```

## スマホからの利用手順

1. iPhone Safariでアプリを開く
2. 地方／中央を選ぶ
3. 必要HTMLをまとめてアップロードする
4. 認識結果を確認する
5. 「予想する」を押す
6. 生成されたPNGを確認する
7. 「PNGを保存」から保存する
8. 次のレースは「次のレースを予想」でリセットする

## 必要HTML

地方：

- タイム指数HTML
- 出馬表HTML
- 脚質分析HTML

中央：

- タイム指数HTML
- 競馬新聞HTML
- 脚質分析HTML
- 調教HTMLは任意

HTMLはまとめてアップロードできます。ユーザーが種類を選ぶ必要はなく、ファイル名、title、canonical、og:url、body id、table class/id から自動分類します。

## PNGレイアウト

PNGは幅1080pxのスマホ縦長画像です。

表示順：

1. レース情報
2. 簡易レース全体表
3. 馬評価（全頭）
4. 注目馬
5. AIレース考察
6. 今回の馬券構成
7. バージョン情報

PC版の横長詳細表はそのまま縮小せず、スマホで読めるカード形式へ変換します。

## 日本語フォント要件

PNG生成には日本語フォントが必要です。以下の順で自動検出します。

1. OS上の日本語フォント
   - Meiryo
   - Yu Gothic
   - Noto Sans CJK / Noto Sans JP
2. `assets/` 内の `.ttf` / `.otf` / `.ttc`
3. 見つからない場合はPNG生成エラーを表示

フォントの絶対パスをアプリ全体へ直接埋め込まず、`render/mobile_png.py` のフォント検出処理で集中管理しています。

## PredictionResult

Phase2以降、Notebook Bridgeから以下を受け取ります。

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

Phase3では、この `PredictionResult` を `render_mobile_png()` へ渡してPNGを生成します。

## Notebook Bridge依存

`core/notebook_bridge.py` は、既存の研究用Notebookを変更せずに読み込みます。

依存Notebook：

- 地方：`netkeiba_nar_ai_prediction_pc_html_colab_venue_trial.ipynb`
- 中央：`netkeiba_ai_prediction_pc_html_colab_jra_venue_trial.ipynb`

読み込むセル：

- セル5：主要ライブラリ、HTML解析、スコア計算、補助関数
- セル6：会場別試験ロジック、追加表示・評価関数
- セル7：解析実行セル

Bridgeが取得する主な変数・表示：

- `result_df`
- `race_info`
- `running_style_info`
- `ai_confidence_summary`
- `display_cols`
- `print_ver30_all_horse_rating()`
- `print_ver30_attention_horses()`
- `print_ver30_ai_race_review()`
- `print_ver30_betting_structure()`

Notebook更新時に確認する項目：

- セル番号5/6/7が変わっていないか
- `result_df` の列名が変わっていないか
- Ver3.0表示関数名が変わっていないか
- `race_info` のキーが変わっていないか
- HTML入力用変数名が変わっていないか

Notebook構造が変わった場合は、Mobile側のBridgeも確認が必要です。

## Notebookパス

通常は現在のCodexフォルダ構成から自動検出します。別の場所にNotebookを置く場合は環境変数で指定できます。

```bash
KEIBA_NAR_NOTEBOOK_PATH=/path/to/netkeiba_nar_ai_prediction_pc_html_colab_venue_trial.ipynb
KEIBA_JRA_NOTEBOOK_PATH=/path/to/netkeiba_ai_prediction_pc_html_colab_jra_venue_trial.ipynb
```

## Streamlit Cloud公開方法

1. このプロジェクトをGitHubへpush
2. Streamlit Community Cloudで `Create app`
3. 対象リポジトリとブランチを選択
4. Main file path に `keiba_ai_mobile/app.py` を指定
5. Deploy

公開前の注意：

- Notebookファイルをどこに置くか決める
- Notebook Bridgeがクラウド環境でNotebookへアクセスできるようにする
- 日本語フォントがクラウド環境に存在するか確認する
- アップロードHTMLはメモリ上で処理し、永続保存しない

## 既知の制限

- 予想ロジックはNotebook構造に依存します。
- PNGは1枚にまとめるため、頭数や文章量が極端に多いと縦長になります。
- 実オッズHTMLの組み合わせオッズ取得はPhase3では使用しません。
- PNG生成側では新しい予想判断を行わず、Notebook Bridgeの結果を表示します。
- Streamlit Cloudでは日本語フォントの追加設定が必要になる可能性があります。
