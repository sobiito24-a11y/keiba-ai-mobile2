# CLASS INPUT ENRICHMENT REPORT

全結果は開発用の参考再計算。正式予想・v1・旧分離版・保存ファイルは不変。結果による係数調整なし。
A/Bの式・各0.5の配分を維持。今回変えるのはA/B入力だけ。他のv1成分は凍結して比較。

## 同一母集団比較

|系統|モデル|R|Top1|Top3|Top5|平均勝ち馬順位|
|---|---|---:|---:|---:|---:|---:|
|jra|enriched_top5|18|3|7|10|6.6111|
|jra|enriched_win|18|2|7|10|6.5556|
|jra|no_class_top5|18|3|7|11|6.5556|
|jra|no_class_win|18|3|7|10|6.5556|
|jra|official|18|5|7|9|6.2222|
|jra|split_top5|18|3|8|10|6.5556|
|jra|split_win|18|2|7|10|6.5556|
|jra|v1_top5|18|3|7|11|6.5556|
|jra|v1_win|18|3|7|10|6.5556|
|nar|enriched_top5|156|44|94|122|3.6026|
|nar|enriched_win|156|44|93|123|3.6090|
|nar|no_class_top5|156|43|94|121|3.6282|
|nar|no_class_win|156|44|93|123|3.6218|
|nar|official|156|47|98|120|3.5577|
|nar|split_top5|156|44|94|122|3.6026|
|nar|split_win|156|44|93|123|3.6026|
|nar|v1_top5|156|43|94|121|3.6282|
|nar|v1_win|156|44|93|123|3.6218|

## B入力・63頭監査

Counter({'1_saved_correct_html_omitted': 63})

|系統|項目|有効/頭数|
|---|---|---:|
|jra|ability_anchor|228/228|
|jra|condition_score|58/228|
|jra|enriched_A|225/228|
|jra|enriched_B|63/228|
|jra|head_count|228/228|
|jra|jockey_score|156/228|
|jra|old_A|225/228|
|jra|old_B|0/228|
|jra|pace_score|228/228|
|jra|past_age|120/228|
|jra|past_date|227/228|
|jra|past_race_id|227/228|
|jra|recent_form_score|191/228|
|jra|training_score|228/228|
|nar|ability_anchor|1682/1682|
|nar|condition_score|735/1682|
|nar|enriched_A|1666/1682|
|nar|enriched_B|544/1682|
|nar|head_count|1682/1682|
|nar|jockey_score|1507/1682|
|nar|old_A|1666/1682|
|nar|old_B|8/1682|
|nar|pace_score|1473/1682|
|nar|past_age|1619/1682|
|nar|past_date|1682/1682|
|nar|past_race_id|1682/1682|
|nar|recent_form_score|1517/1682|
|nar|training_score|0/1682|

## Top1保持・候補追加参考

jra: {'both': 9, 'neither': 8, 'enriched_only': 1}。平均追加0.611頭、追加馬11頭、勝利1・3着内3。全現行Top1を保持する集合和方式であり、候補数増による捕捉と同数順位改善は別。
nar: {'both': 119, 'neither': 33, 'enriched_only': 3, 'official_only': 1}。平均追加0.186頭、追加馬29頭、勝利3・3着内11。全現行Top1を保持する集合和方式であり、候補数増による捕捉と同数順位改善は別。

## 情報源・限界

利用ヘッダー2,112件（既存196件＋追加取得1,916件）。初回1,920件を照合し、1,916件で明示ヘッダーを確認、4件は確認不能。最終再実行では取得済みキャッシュを再利用し、未確認4件のみ再確認しました。初回取得履歴はheader_collection_audit_first_pass.json、今回履歴はheader_collection_audit.json。
Snapshotの過去race_idと新聞リンクを優先して照合。年はrace_idと月日から検証可能な形で復元。複合照合では年月日・場・R・馬識別・馬場・距離が必要。月日/スロットのみの結合は禁止。
保存された拡張レース名の明示年齢条件は同一race_id・クラス整合時のみ使用。元HTML未保存の保存値は独立した原ページ照合済みとは区別する。取得時刻不明を予測時刻で埋めない。
比較不能な年齢限定・新馬・異会場・体系差は欠損補完で数値化しない。全頭有効化を目的としない。
JRA18Rは9/27平地のみ。9/26正式順位欠損20Rと9/27障害1Rを除外。NAR156Rは佐賀9/26 1Rの保存純能力欠損を除外。NAR5位同着6頭選出は維持。
全196R・2184頭の元データと旧モデル非変更、全入力ファイルSHA一致。
本候補の正式採用は行っていない。未来予測では保存済み構造化入力・結果を復元し、旧Snapshotには再計算を実行しない。

## Bによる変化（Aを固定した差分）

jra: 新たにB有効 63頭、BによるTop5候補順位変化 6頭、勝ち馬追加捕捉 0R、取りこぼし 0R。
nar: 新たにB有効 544頭、BによるTop5候補順位変化 2頭、勝ち馬追加捕捉 0R、取りこぼし 0R。

取得可能率を上げるためのクラス推測はしていません。クラス原文が切れている／混合クラス／明示年齢不明／転入・異会場はclass_change_blockers.csvに分離しています。
JRA63頭は保存過去race_idと新聞のID・条件が整合した保存情報の復元です。JRA過去ページHTTP 400のため、元ページを今回独立取得して年齢条件まで再確認した頭数とは区別してください。

## 採用判断と確認結果

- B有効のうちJRAは同級54頭・非ゼロ9頭。NARは同級493頭・非ゼロ51頭。取得率向上と予測改善は別です。
- NARの旧8頭は門別202630100106。短縮表示「3歳以上C」を単一のC級水準として比較していましたが、正式ヘッダーはC3/C4混合でした。新候補では8頭とも比較対象外とし、それとは別の544頭で根拠のある比較が可能になりました。
- JRA63頭は全頭、race_idと新聞のクラス・条件が整合した保存情報の消失に該当。誤結合を確認したケース0頭、照合不能0頭。ただし保存原文の正しさを今回の原ページ再取得で独立確認した件数は0頭です。対象63頭の過去IDから3件を取得し直しましたがHTTP 400でした。jra_header_fetch_audit.jsonに記録しています。
- Bにより勝ち馬のTop5追加捕捉・取りこぼしは双方0R。JRA202609040912・8番サンライズオスカーはTop5候補3位→4位となり、Top3捕捉が1R悪化しました。NAR Top5候補の捕捉数は旧分離版から不変です。
- 現行Top5＋新候補の集合和はJRA平均5.611頭、NARは保存同着を含む正式集合に平均0.186頭追加。新候補単体との同数比較ではありません。
- 追加馬の勝率／複勝率：JRA 1/11＝9.1%／3/11＝27.3%、NAR 3/29＝10.3%／11/29＝37.9%。小標本であり、Bの追加捕捉効果とは区別します。
- 正式モデルへの昇格は推奨しません。研究候補の入力品質修正として保持し、係数調整はしていません。
- Dashboard pytest：835 passed、14 subtests passed。
- Mobile pytest：626 passed、14 subtests passed。
- 196R・2,184頭で変更前HEADの正式テーブル・購入判断関連データ・V2 v1・旧分離版との一致、旧保存ファイルSHA不変、両repo同一入力結果一致を確認。
- 新版の構造化入力を保存し、HTML再取得なしでA/Bを再評価する監査関数も追加。通常のSnapshot復元では保存結果をコピーし再計算しません。
- 新規予想での追加HTTPは `KEIBA_V2_FETCH_PAST_HEADERS=1` とキャッシュディレクトリ設定で有効化します。設定なしでは利用可能な保存入力を使用し、勝手に不足条件を補完しません。

変更ファイル（両repo共通）：

- core/newspaper_v2_enrichment.py
- core/newspaper_v2_past_headers.py
- core/newspaper_v2_engine.py
- core/newspaper_v2_snapshot.py
- tools/evaluate_newspaper_v2_enrichment.py
- tests/test_newspaper_v2_enrichment.py
- tests/test_newspaper_v2_class_revision.py
- docs/NEWSPAPER_V2_SHADOW.md
- docs/NEWSPAPER_V2_INPUT_ENRICHMENT_VALIDATION.md
