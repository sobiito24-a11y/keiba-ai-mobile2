# 新モードの能力独立性

## 「新モードのみ記録済みの非能力調整を差し引く」の具体的な意味

旧実装では、互換列 `raw_score` が次の形だった。

`raw_score = Ver3タイム指数コア + 斤量・状態等の旧補正`

そこで旧スナップショットを新モードで読むため、旧補正を
`_market_non_ability_adjustment` に記録し、
`raw_score - _market_non_ability_adjustment` と逆算していた。これが
「新モードのみ記録済みの非能力調整を差し引く」の意味である。

ただし、この表現は「何が本当の能力入力か」を分かりにくくする。現行実装は
補正前の値を `_ver3_ability_core` として直接保存し、新モードはこの列だけを
能力値・順位・能力帯へ渡す。差し引きは `_ver3_ability_core` を持たない旧保存
データの互換処理に限定した。旧モードの `raw_score` は変更していない。

## 能力コアの入力

`core/ver3_ability.py::calculate_ver3_ability_core` の引数は次の6項目だけである。

| 入力 | 重み |
|---|---:|
| 近3走平均 | 0.15 |
| ★最高指数（取得不能時は既存の場平均代替） | 0.30 |
| 近3走最高 | 0.20 |
| 前走指数 | 0.15 |
| 距離指数 | 0.10 |
| コース指数 | 0.10 |

斤量、状態ラベル・状態加点、騎手、脚質・展開、オッズ、人気は関数の引数にない。

## コード上の依存経路

| 項目 | 能力コア・順位・帯 | 表示先 |
|---|---|---|
| 斤量・斤量増減 | 入らない | `weight_*`、＋/－材料 |
| 状態矢印・旧状態加点 | 入らない | `state_*`、＋/－材料 |
| 騎手・乗替 | 入らない | `jockey_*` |
| 脚質・展開 | 入らない | `pace_*`、＋/－材料 |
| オッズ・人気 | 入らない | 実オッズ、帯内価格比較 |

処理順は次のとおり。

1. `core/jra_notebook_logic.py` と `core/nar_notebook_logic.py` が、6指数だけで
   `_ver3_ability_core` を保存する。
2. 互換用 `raw_score` は従来どおり旧補正を含めて保存する。
3. `core/market_compare.py::evaluate_market_table` は
   `_ver3_ability_core` を `market_ability_score` に採用する。
4. `core/market_compare.py::_ability_bands` はその能力Seriesだけで順位・帯を作る。
5. 斤量、状態、騎手、展開、オッズ等は、その後の独立列・＋/－材料へ付与する。

## 回帰テスト

- `tests/test_ver3_ability_core.py`
  - 純粋能力関数の引数が6指数だけであることと重み合計1.0を検証する。
- `tests/test_market_compare.py::test_explicit_ver3_core_is_authoritative_not_legacy_adjustments`
  - 同じ `_ver3_ability_core` に対し、旧raw、旧補正、斤量、騎手、脚質、オッズ、
    人気を大幅に変えても能力値・順位・帯が同一であることを検証する。
- `tests/test_market_compare.py::test_price_popularity_jockey_interval_weight_and_pace_do_not_change_ability`
  - 市場・騎手・間隔・斤量・展開の反事実変更で能力が動かないことを検証する。
- `tests/test_tanabata_onyankopon_regression.py`
  - 七夕賞の実HTMLから9番オニャンコポン、73.5倍、15番人気、差し、中1週、
    54kg、吉田豊、`B 復調気配`、厩舎コメントを固定する。
  - 実オッズ73.5倍・15番人気のままでも、与えられたVer3能力コアのA帯を
    降格させないことを検証する。

添付HTMLは競馬新聞ページで、Ver3タイム指数ページではない。このため回帰は
「実HTMLの市場・当日材料」と「能力コアからの独立性」を固定する。オニャンコポン
当日の正確なVer3能力値そのものは、同レースのタイム指数HTMLがない限り捏造しない。
