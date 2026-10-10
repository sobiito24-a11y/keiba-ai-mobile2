# 順位・4角研究（正式予想には接続しない）

`core/rank_corner_research.py` と専用CLIだけで動作する任意実行の研究機能です。predictor/UI/既存Snapshotには接続しません。正式順位・印・勝率・考察を更新しません。

## 入力

JSONのキーは `race_id`, `mode` (`nar`/`jra`), `rows`, `metadata`。
各馬は `horse_no`, `pure`（保存ver3_ability_core）, `pure_rank`（保存順位）, `corner4`, `formal_rank`, `formal_score`, `formal_mark`, `candidate`（保存正式候補集合のbool）, `status` を使用。その他の許可項目はモジュールのFIELDS参照。
丸め前の値から保存順位を再計算しません。純能力同順位の代表馬は馬番昇順。表示用純能力値が同じでも保存順位を優先します。結果・実4角・払戻・オッズは予測入力に含めません。

NAR A=保存正式順位（欠落時の式再現は参考再計算と明記）、B=保存純能力順位、C=純能力−3×4角、D=純能力−5×4角。C/Dは正式候補内だけ再順位します。境界同順位6頭等を削りません。欠損馬は純能力順での元の枠に固定し、残りの枠のみ並べ替えます。レース全体を純能力順へ戻す処理とは異なります。予測時点の取消・除外のみ対象外とし、結果判明後の取消で予測を並べ替えません。

JRA A=保存正式順位、B=位置カテゴリ補正＋正確4角補正を除外、C=両補正半減。exact_bonus_only_removedは正確4角のみ除外。純能力・調教・再現性等の保存内訳の合計が正式スコアと一致する平地のみ作成。構成要素欠落・障害は推測補完しません。

## 過去研究

```powershell
python tools/freeze_rank_corner_research.py inputs.json research.json --registry C:/research/registry --csv research.csv
```

既存出力は上書きしません。同一race_idはmode単位で共有registryに一度だけ登録できます。Dashboard/Mobile・出力フォルダをまたいで同じregistryを指定してください。保存失敗時も登録は残す安全側動作です。新しいファイル名やモデル版で二重保存しないでください。

## 発走前の未来検証

```powershell
python tools/freeze_rank_corner_research.py inputs.json frozen.json --phase future_validation --registry C:/research/registry --csv frozen.csv
```

metadataに `date`（YYYY-MM-DD）, `prediction_created_at`, `scheduled_post_time`（時差付きISO時刻）, `source_hash`, `formal_origin` を付与してください。`source_hash`は元の予測入力の識別用です。正規化入力自体のSHA256は自動生成します。
2026-10-10以前の研究済み日付は未来検証として拒否。生成時刻≤実保存時刻<予定発走時刻、日本時間の開催日一致、完全な研究結果が必要です。時刻・日付は信頼できる発走前データを渡してください。研究日付が増えた場合は研究済み境界の管理が別途必要です。これは自動収集・自動購入機能ではなく、予測完成後に明示実行する保存機能です。

## 確定後の別処理

```powershell
python tools/freeze_rank_corner_research.py frozen.json joined.json --outcomes outcomes.json
```

outcomesには同じrace_id、馬番で紐付けた着順・実4角・払戻と取得元/時刻を格納。予測JSONを変更せず、予測全体のハッシュ付き別JSONへ結合します。入力ハッシュ・race_idの不一致は拒否します。欠損払戻を0円にしないでください。実4角の集団表記は区間として保持し、確定した一点順位と分けて評価してください。

研究の高成績をそのまま正式採用しません。Top1だけでなく複勝・Top2・Top4・回収率と高額払戻依存、日別の対応比較を確認します。
