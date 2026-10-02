# 競馬新聞型V2 Shadow

正式予想を置き換えない独立研究モデル。既存 `core/v2_logic.py` とは別物です。
JRA/NARのクラス体系・係数・モデルversionは別管理。新V2にオッズ・人気・今回の着順・払戻は入力しません。

## 境界と保存

新規予想の既存 `apply_prediction_logic` 完了後にのみ計算し、`debug_info["jra_newspaper_v2_shadow"]` または `debug_info["nar_newspaper_v2_shadow"]` に保持します。
元のテーブル、純能力、Top5、印、既存勝率、買い方・購入判定は上書きしません。
新規生成時の正式比較順位は既存JRA v1関数／NAR Canonical順位をそのまま参照してV2内へ監査用に記録します。V2スコアの入力には使用しません。

Dashboard `.keiba` は既存PredictionResultのdebug保存・復元でV2を凍結。Mobileの既存prediction.json／ZIPにも同じV2を保存します。
`newspaper_v2_snapshot.py` は保存値のコピーのみ行います。復元・表示から計算エンジンは呼びません。
V2のない旧保存データは「未計算」。保存ファイルへの上書き、欠けた正式Top5の再生成は行いません。
新規保存で実際の日付型を含む過去走も保存できるよう、既存JSONシリアライズでISO日付化します（数値・予想は不変）。

## クラス判定

今回のヘッダーのRaceName/RaceData01/RaceData02を一度だけ読みます。過去走欄にも存在するRaceNameを混ぜません。
JRAはレース名に属するG1–3アイコン／明示グレード・ヘッダーの競走条件を優先。芝コースのB/C区分、汎用CSSは採用しません。
JRAはG1–3/Jpn1–3/L/OP/3勝/2勝/1勝/未勝利/新馬を区別し、障害は平地モデル対象外。
NARは年齢限定を一般A/B/Cと分離し、開催場・組別・重賞を保持。混合クラス、年齢限定、新馬、比較根拠不明のクラスには通常の上下補正を強制しません。
体系・年齢・NAR開催場が一致して比較可能な場合のみ、前走→今回の上下を評価します。
「前走からの変化」「過去3走の最高クラス」「同級好走数」は独立。過去上位経験で前走同級を降級に上書きしません。
旧クラス、旧クラス変化、原文、情報源、信頼度を併記。**修正クラスはV2専用で、旧正式計算へ接続していません。**

## 初期評価式（結果最適化なし）

設定は `core/newspaper_v2_weights.json`。係数は結果照合前に固定した研究仮説で、校正された確率ではありません。

`V2 score = 既存純能力 + Σ(下表の係数 × 各補助材料)`

|補助材料|JRA Top5候補|JRA勝ち馬候補|NAR Top5候補|NAR勝ち馬候補|
|---|---:|---:|---:|---:|
|近走変化|1.00|2.00|0.75|1.50|
|クラス・着順|0.50|0.75|0.50|0.75|
|条件比較|0.50|0.75|0.75|1.00|
|ペース×位置|0.25|0.50|0.25|0.75|
|調教|0.50|0.75|0|0|
|騎手|0.15|0.25|0.15|0.25|
|斤量|0|0|0|0|

補助材料は[-1,1]に制限。欠損は観測値を捏造せずNoneで保存し、合算時だけ寄与0。純能力欠損馬はV2順位なし。

- 近走変化：`clip((前走指数 − 2/3走前の有効指数平均)/10)`。既に純能力に含まれる近走平均そのものを再加点しません。
- クラス・着順：頭数付き前走着順を `1−2×(着順−1)/(頭数−1)` へ正規化し、比較可能な前走と今回のクラス差と各0.5で合成。クラス差はJRA1段階、NAR3単位で割りclip。年齢・会場等が不明なら補正なし。
- 条件比較：近3走の同会場・同距離・同芝ダ・同方向の指数平均と、それ以外の指数平均との差を10で割りclip。両群の実値がある時だけ使用。距離・コース・★の水準を重ねて加点しません。
- ペース：Sで4角1–3番手は+1、後方65%超は−0.5。Hかつ前方想定3頭以上なら前方−1、それ以外+0.5。Mは0。公式position bonus自体は加算しません。
- 調教：JRA A=1/B=0.5/C=0/D=−0.5。NARは不使用。
- 騎手：明示されたコース複勝率かつ20走以上のみ `clip((率−25)/25)`。
- 間隔、安定性（指数標準偏差）、着差、相手名、斤量増減、継続/乗替は監査材料。根拠未検証の一律補正はしません。

過去走HTMLは馬番で紐付け、近3走枠だけ取得。保存済み指数はラベルと日付が一致した走にだけ接続します。
同点はscore→純能力→近走変化→馬番で決定。JRA障害は全馬に対象外を記録します。

## 画面

「新聞型V2研究比較（参考）」は初期状態で閉じます。既存の結論・候補カード・全頭カード・詳細表は維持。
全頭について純能力順位／現行Top5／V2二順位と理由・不足情報をコンパクトカードで比較。390pxでは一列へ折り返します。
新V2をPNGに追加しません。既存PNGロジックは変更しません。

## 診断用評価ツール

`python tools/evaluate_newspaper_v2_shadow.py <保存.keiba...> --output <出力先> --results-json <確定着順JSON> --html-root <当時HTMLフォルダー>`

結果JSONは `{race_id: {horse_no: finish}}`。結果はV2計算完了後にのみ結合。
V2未保存の過去データは `reference_recalculation_v2_only` と明記。保存済み正式順位・勝率の欠損は補完しません。
NAR正式Top5の比較順位は保存済みCanonical純能力順位の別名として参照し、丸め値で再順位付けしません。
全頭分揃わない順位モデルは当該レースの評価対象外。モデル間の母数差に注意し、正式順位とV2が共に揃うpaired比較も出力します。
CSV（クラス監査、全頭比較、区分別集計）、JSON（V2参考再計算・入力SHA・集計）、Markdownを出力。
JRA/NAR、日付、開催場、クラス、年齢限定、平地/障害、データ品質を別集計します。

## 未来検証

次の未使用レースで予想を発走前に生成・保存し、入力ファイルSHA、モデルversion、係数、予想時刻を凍結。
発走時刻と予想生成時刻の確認不能分は未来検証に混ぜません。
結果確定後にrace_id＋馬番で別ファイルとして照合し、同じレース集合の正式順位とV2を比較します。
過去データは開発・診断用で、今回の結果だけで正式採用しません。オッズ取得時刻の不明値も予想生成時刻で代用しません。

## 両アプリの入力差への対応

既存の騎手コースHTMLパーサーにはアプリ間差があります。正式パーサーは変更せず、V2専用コピーへ同じ明示表を取り込みます。
URLのrace_id・JRA/NAR・cid=2、タイトルの会場/芝ダ/距離、馬番と馬名の一致を確認します。位置順で結合しません。
前走騎手名が不明な場合の継続/乗替はV2監査でも不明にします。正式側の保存値・表示は変更しません。


## 次期研究候補: クラス・着順分離（2026-10-02）

既存v1は変更しません。新規生成時に `jra_newspaper_shadow_v2_class_split` / `nar_newspaper_shadow_v2_class_split` を並行計算し、
`debug_info["jra_newspaper_v2_class_split_shadow"]` / `debug_info["nar_newspaper_v2_class_split_shadow"]` に追加保存します。
画面の研究パネルは引き続きv1を表示します。修正版の順位は正式予想・勝率・購入判断・画面へ接続しません。
旧保存には新項目を補完しません。保存復元は両versionともコピーのみです。

調査で、過去走のクラス表示は `Data03`（定量/馬齢等）ではなく最初の `PastDataLine` の `Icon_GradeType` にあると確認しました。
次期専用入力で馬番をキーに前走枠のクラス表示・着順Data04・頭数Data05・会場・芝ダ障を読み、原文を保存します。
v1のパーサー・`evaluate_shadow()`・係数はそのまま残します。

A（前走着順の質）: `1 - 2*(finish-1)/(head_count-1)`。
B（クラス変化）: 比較可能な前走/今回のクラス水準差をJRA1/NAR3で割り[-1,1]へ制限。
新寄与: `旧class係数 * (0.5*A + 0.5*B)`。片方が不明でも他方は独立に評価し、不明分の重みを振り替えません。
最大幅は旧class項と同じ。Top5候補はA/B各0.25、勝ち馬候補は各0.375。他項目の係数・評価はv1を再利用します。
設定は `newspaper_v2_class_split.json`。結果に合わせた探索はしていません。

Bでは過去会場から体系を識別し、年齢不明・不一致、競走種別不明・不一致、NAR会場不一致、対応するクラス水準なしを個別に記録します。
前走の年齢区分を馬の現在年齢から推測しません。重賞/年齢限定/新馬を根拠なく一般クラスへ変換しません。
クラス表示を取得できても、比較根拠が不足する場合のBはNoneです。

比較ツール:
`python tools/evaluate_newspaper_v2_class_split.py --validation-root <既存検証フォルダー> --output <新規出力フォルダー>`
既存正式順位、v1、分離版、v1からclass項だけを除去した参考モデルを同一母集団で比較。
HTML併用/保存のみの有効率、原因別頭数・レース数、馬別原文、A/B寄与、Top5入替、勝ち馬順位変動をCSVに保存します。
確定結果はモデル計算の後にだけ結合。過去データは開発診断で、正式採用の根拠としません。

## Input-enrichment research candidate (v3)

`jra_newspaper_shadow_v3_input_enriched` / `nar_newspaper_shadow_v3_input_enriched`
are saved under `<mode>_newspaper_v2_input_enriched_shadow`. Neither replaces
v1, the class-split candidate, formal scores/ranks/marks, probabilities or buying
logic. No coefficients are fitted. Only the split candidate's A/B evidence is
changed; all other components remain fixed for an attributable comparison.

`newspaper_v2_enrichment.py` retains three structured past runs, source text,
field provenance, unknown acquisition timestamps, normalized class, identity
conflicts and input hashes. Matching uses race ID with contradictory identity
checks; the fallback requires full date, venue, race number, surface, distance
and horse identity. Slot labels/month-day alone cannot merge records.
A newspaper class badge is read separately from Data03 (weight condition).
Saved expanded race names may supply explicit eligibility after a valid join.
A shortened NAR C label or mixed C3/C4 cannot establish a numeric class change.

`newspaper_v2_past_headers.py` offers a race-ID cache and validates explicit
headers. NAR official date/venue/race number must agree. Only header eligibility
and conditions enter the model; result-table rows, payoff, popularity and odds
are never inputs. Historical data collected later are reference evidence, not
claimed as a frozen prediction. Missing headers remain unknown.

Fresh prediction callers may supply `html_files["past_race_headers"]` keyed by
race ID. `KEIBA_V2_PAST_HEADER_CACHE` selects a local cache directory.
`KEIBA_V2_FETCH_PAST_HEADERS=1` opts the fresh prediction path into HTTP on cache
misses; by default no network request is added to normal prediction latency.
This setting never affects Snapshot restoration. Acquisition timestamps are
recorded only when known, not replaced by prediction timestamps. Archive source
HTML alongside the cache for independent future audits.

New snapshots retain the structured input and evaluated result. Restoration
only copies saved versions; old snapshots are not recalculated. Research
reports can be reproduced with `tools/evaluate_newspaper_v2_enrichment.py` using
`--root`, `--output`, optional `--fetch-limit` (netkeiba headers) and
`--nar-fetch-limit` (official NAR headers). Source snapshot SHA checks guard
against overwriting frozen data. All reports label retrospective computation.
