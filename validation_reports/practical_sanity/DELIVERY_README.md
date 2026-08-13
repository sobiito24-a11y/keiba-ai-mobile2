# Keiba AI Mobile 実戦モード成果物

- 実装commit: `91a7df77938f92e842852ab98356d7669b193011`
- commit message: `Add conservative practical betting mode`
- 実戦設定: `practical-1.0`
- 予想基準: Ver3の既存表示印・順位
- 条件適性: Ver4.1の★/☆/※とdata statusを補助情報として維持（順位加点なし）
- 主推奨: BUY時のみ◎単勝1点100円
- 100R保存先: `prediction_history/practical_100r/`

`practical_sanity_predictions_pre_result.csv` は結果読込前に固定した188Rの判断、`PREDICTIONS_FROZEN.flag` はそのSHA-256、`practical_sanity_results.csv` は固定後に着順・単勝払戻を結合した結果です。

188R sanity checkは回収率最適化には使用していません。固定ルールでBUY 15R、投資1,500円、払戻870円、収支-630円、回収率58.0%でした。この結果を受けた条件・weight・印境界の変更はしていません。
