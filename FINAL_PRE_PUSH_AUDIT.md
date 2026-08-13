# Push前 最終追加実装・監査報告

## 結論

競馬新聞HTMLに明示された当日コース・展開情報を、Market Compareの独立表示層へ追加した。Ver3能力コア、能力順位、AA/A/B/C/Z能力帯、帯内オッズ比較には入力していない。騎手のコース別勝率・連対率・複勝率・出走回数は今回の保存HTML群に実値がなかったため、推測取得は行っていない。

完全回帰は `python -m pytest -q` で `200 passed, 14 subtests passed`。実装前の収集数 `184 tests` から16件増え、既存テスト削除は0件である。commit / pushは実施していない。

## 1. 変更ファイル一覧

今回の展開/コース独立表示で追加・変更したファイル:

- `core/course_materials.py`: 保存新聞HTMLの構造化、完全性・欠損判定、結果表への独立列付加
- `core/jra_predictor.py`: Market Compare時だけ共通parserを接続
- `core/nar_predictor.py`: Market Compare時だけ共通parserを接続
- `core/nar_json_input.py`: NAR JSON経路でも原新聞HTMLを独立parser用キーに保持
- `core/market_compare.py`: 展開/コース1グループ化、騎手コース客観値・サンプル判定、独立列・材料表示
- `app.py`: 一画面の全頭表、馬別カード、レース事実欄へ独立表示
- `tests/test_course_materials.py`: JRA/NAR、PC/スマホ、実七夕賞、欠損、独立性、重複排除、騎手サンプルの追加回帰
- `tests/test_nar_courseanalysis_input.py`: NAR JSON経路で生新聞HTMLが保持されることを追加確認
- `tests/test_ver3_ability_core.py`: 6項目weightの完全一致を明示確認
- `COURSE_DATA_AUDIT.md`: 実装後の結果を追記
- `README.md`: 利用条件、欠損、完全回帰基準を更新
- `FINAL_PRE_PUSH_AUDIT.md`: 本報告

最終候補には、前回承認済みのPC/スマホHTML Routing関連変更も同梱する:

- `core/html_classifier.py`
- `core/models.py`
- `tests/test_html_upload_routing.py`
- `tests/test_detail_analysis_table.py`
- `requirements-test.txt`

## 2. 取得できるコース情報

保存HTMLに明示実値がある場合だけ取得する。

| 情報 | 所在 | 実データ確認 |
|---|---|---|
| コース条件 | `.CourseDataArea.Time h2` の静的HTML | JRA新潟 `新潟1200m芝 Aコース`、七夕賞 `福島2000m芝 Bコース`、NAR佐賀 `佐賀1300mダ` |
| ペース H/M/S | `.CourseDataArea.Time .Data` の文字と `Pace_*` class | 新潟H、七夕賞M、佐賀H |
| スタート後/3角/4角の推定位置 | active DOMの `HorseIcon` style、無補正inline JS | 新潟18/18、七夕賞16/16、佐賀10/10を3時点で確認 |
| 4角位置別複勝率 | `.PositionMarkList` の3×3静的テキスト | 新潟、七夕賞で9セル取得 |
| 有利位置ラベル | `.PositionMapImg > dt` | 新潟 `中目有利`、七夕賞 `フラット` |
| 表示済み推定有利馬 | `.PositionPickupHorseWrap li` | 新潟6番、七夕賞13番を確認。ただし完全リストではない |
| AI見解の表示済み部分 | `.DevelopOpinionArea dd p` | 部分文と `complete=false` を保持 |
| 前半/後半3F | `PredictRap_Table` の非dummy実値行 | 各JRA例で1頭分。カバレッジ不足のため材料不使用 |
| 騎手コース上位候補 | `AnaBestTable` の「騎手」 | 新潟で3頭。率・件数なしの参考順位としてのみ保持 |

NARでは保存HTMLのJavaScriptにコメント済みの別頭数向け座標が残る例があった。行コメントを除去し、現在DOMに存在する馬番集合で絞ることで、旧14頭座標ではなく実出走10頭を取得する。

## 3. 取得できないコース情報

- トラックバイアス: 実テキストがない。NARで `BiasPattern222` のclassだけがある例は「コードのみ・意味未確定」とし、意味を生成しない。JRA例は空DOM/ダミーで「HTML内に実値なし」。
- ラップ予測: 見出しはあるが値セルがdummy画像だけ。数値は生成しない。
- 完全なAI見解: 文末が `...`、直後がdummyの場合は部分取得のまま。
- 全頭の前半/後半3F: 確認HTMLは1頭だけで、残りはdummy。3頭未満は比較材料にしない。
- 完全な推定有利馬リスト: 見える1頭の後に会員向けdummyがあるため、非表示分を否定・補完しない。
- 今回再添付の `keiba_data.zip`: 中身はHTMLではなく、NAR `courseanalysis&cid=2` に対する「未対応ページ」エラーJSON。ここからコース/騎手値を作らない。

## 4. 騎手成績の取得元

今回確認した競馬新聞、JRA courseanalysis、NAR競馬新聞には、当該競馬場＋距離＋芝/ダート条件の騎手別「勝率・連対率・複勝率・出走回数」は存在しなかった。

- 新潟競馬新聞: `AnaBestTable` に騎手上位候補3件と `data.html?mode=ranking` へのリンクだけ。率・件数なし。
- 七夕賞競馬新聞: 騎手ランキング表なし。
- NAR佐賀競馬新聞: コース別騎手率表なし。
- 馬欄の騎手名、乗替、`0-0-0-2` 等は騎手コース統計と断定できないため流用しない。

したがって現状の実データ取得元は「なし」、参考順位の取得元だけが競馬新聞 `AnaBestTable` である。将来、明示列 `jockey_course_win_rate / quinella_rate / place_rate / starts / condition / source` が供給された場合にだけ構造化表示する契約を追加した。知名度・名前による評価はない。

## 5. 騎手成績のサンプル数処理

- 出走回数なし: `参考値 / サンプル数未取得`。○△を付けない。
- 20走未満: `参考 / サンプル不足 n=...`。率が高くても＋材料にしない。
- 20走以上: 勝率・複勝率がともに極端な場合だけ弱い `○` または `△`。それ以外は `±`。
- 参考ランキングだけ: `該当コース上位候補N位（率・件数なし）`。強評価しない。
- どのケースもVer3能力、能力帯、適正オッズへ入力しない。

## 6. 展開材料の重複排除方法

同じ提供元のペース、推定位置、4角ヒートマップ、有利位置ラベル、推定有利馬は、1頭につき1つの `course_development_mark / reason` にまとめる。材料リストへ入る `展開/コース：...` は最大1件である。

優先順は、明示された推定有利馬 → 前/後有利ラベルと脚質の組合せ → H/Sと脚質の組合せ → 位置取得済み・評価保留。例として「推定有利馬」「H×差し」「4角前方」を別々に積まない。4角 `フラット` は `±` であり加点しない。

## 7. 能力コアが変更されていない証拠

`core/ver3_ability.py` の関数シグネチャは次の6引数だけで、今回変更していない。

| 入力 | weight |
|---|---:|
| 近3走平均 | 15% |
| ★最高指数 | 30% |
| 近3走最高 | 20% |
| 前走指数 | 15% |
| 距離指数 | 10% |
| コース指数 | 10% |

`tests/test_ver3_ability_core.py` は辞書全体の完全一致、合計1.0、6引数だけであることを検証する。`tests/test_course_materials.py` はコース、ペース、騎手名、騎手率を反転しても `market_ability_score / market_ability_rank / ability_band_v2` が同一であることを確認する。

実装上も `evaluate_market_table()` は最初に `_ver3_ability_core` から能力値・順位・帯を確定し、その後のrow passで展開/騎手表示を作る。後段から能力列への代入はない。

## 8. AA/A/B/C/Zが独立している証拠

- 帯判定 `_ability_bands(ability)` の引数は上記能力seriesだけ。
- オッズ、人気、騎手、騎手成績、斤量、状態、間隔、脚質、提供元ペース、位置、有利ラベルは帯確定後の表示列。
- Market Compare接続は `prediction_logic_version == "market"` の場合だけ。既存Ver3/Ver4/実戦モードは追加parserを呼ばない。
- オニャンコポン回帰では、実HTMLの73.5倍・15番人気でも固定Ver3コア90.0のA帯を維持する。

## 9. 全pytest結果

実行コマンド:

```text
python -m pytest -q
```

最終結果:

```text
200 passed, 14 subtests passed in 38.37s
```

収集結果は `200 tests collected`。実装前基準184件に16件を追加した。

## 10. PC/スマホ双方の確認結果

- PCとスマホは `classify_html / validate_upload_bundle` → JRA/NAR predictor → `parse_netkeiba_course_materials` の同一経路。
- canonicalが `race.netkeiba.com` と `race.sp.netkeiba.com` の場合で同じJRA判定・同じ構造化結果になるテストを追加。
- ファイル名に依存せず、canonical/og:url、固有URL、固有DOM、title、最後にファイル名の既存優先順を維持。
- unknown、race_id不一致、mode不一致、同kind重複を既存Routingテストと合わせて維持。

## 11. JRA/NAR双方の確認結果

- JRA実fixture（七夕賞）: 福島2000m芝B、M、16頭×3時点、4角3×3、フラット、表示有利馬13、3F 1/16、バイアス/ラップ実値なし。
- JRA実HTML（新潟）: 新潟1200m芝A、H、18頭×3時点、4角3×3、中目有利、表示有利馬6、騎手参考順位3、3F 1/18。
- NAR実HTML（佐賀）: 佐賀1300mダ、H、実出走10頭×3時点。コメント済み旧14頭分を除外。バイアスはコードのみ、ラップ実値なし。
- JRA/NAR mode不一致は `JRA/NAR不一致`、race_id不一致は `race_id不一致` として材料を付けない。

## 12. 既存テストを削除していないこと

- 実装開始時: `184 tests collected`。
- 実装後: `200 tests collected`。
- 既存subtest: 14件のまま。
- 削除されたテストファイル・テストケース: 0件。
- 新規: `tests/test_course_materials.py` の16件。
- 既存テストの判定緩和なし。NAR原文保持テストはdecode後の前後空白だけを正規化し、本文完全一致を検証する。

## 13. 実レースのMarket Compare表示例

七夕賞保存HTML `race_id=202603020611` のオニャンコポン回帰を、同HTMLの展開/コース情報と結合した例。能力コア90.0は既存回帰シナリオの固定値であり、新聞HTMLから再推定した値ではない。その他のオッズ、人気、脚質、斤量、騎手、間隔、位置、コース、ペースは保存HTML実値。

```text
9 オニャンコポン
A｜73.5倍（能力順位2位・固定Ver3能力90.0）

能力：A
脚質：差
間隔：中1週
斤量：54.0kg
騎手：吉田豊（継続/乗替は未取得）
騎手コース：取得不能（HTML内に率・件数なし）
コース条件：福島2000m芝 Bコース
提供元ペース：M
推定位置：スタート left=75.88% / 3角 left=88.91% / 4角 left=100%, SpeedUp_02
4角傾向：フラット
展開/コース：± 4角傾向フラット

＋ 復調
－ なし
```

コース情報を追加しても `A｜73.5倍` は変わらない。騎手率がないため、吉田豊という名前だけで＋を付けていない。

## 配布状態

- PC/スマホ共通アプリ、JRA/NAR、テスト、実fixture、監査文書を1つのZIPへ格納する。
- commit / pushは未実施。
