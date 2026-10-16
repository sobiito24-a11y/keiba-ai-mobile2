# 正式順位・純能力・市場比較（独立研究）

本番アプリから呼ばれないオフライン研究です。正式順位・印・スコア・既存固定判断JSON・OCRを変更しません。過去の成績は全件探索済みであり、未来の利益優位性の証拠ではありません。

## 再集計

`python tools/audit_market_ranks.py --archive research.zip --snapshot original.keiba --snapshot second.keiba --reference 03_三者比較_レース明細.csv --output new_output_directory`

研究アーカイブは metadata.json / packets.json / outcomes.json を含むもの。Snapshotはメタデータが指定する保存元だけを採用し、別版への自動差し替えをしません。保存正式順位の欠損を現行コードで補いません。馬番同点は保存順位、最後に馬番で決定。人気の同オッズは競争順位を表示し、候補5頭を切る場合だけ馬番で安定化します。

正式・純能力・市場・純能力上位3頭＋市場補完を比較。JRAの位置除外／半減は元Snapshotの `jra_formal_comparison_snapshot` に全構成要素があり、保存スコアとの誤差が0.0011以下の平地だけ対象です。補正前の値を現行予測エンジンで推定しません。

出力は comparison/races/strata/horse_audit/candidates/tickets/returns/exclusions.csv、研究入力JSON、マニフェスト、単独HTML監査ページ。HTMLの馬別情報は折りたたみ式。本番画面に自動買い目を追加しません。

単複は1・2・5頭、ペアは事前に列挙した順の1・2・全点。各点100円なので、全点方式の総投資は他方式と異なります。比較は同じ券種・点数区分・対象日で行ってください。払戻欠損はunknownとして既知分ROIから除外し、件数を表示します。馬単は順序を保存。返還は券種別の明示的refundsだけ認め、特殊決済や不完全な的中払戻は推測しません。最高1件・2件除外は投資据置と購入自体除外の両方を出します。

## 次回の発走前固定

入力JSONのトップレベルは `race_id, mode, horses, metadata`。馬は core/market_rank_audit.py のFIELDS、時刻等はMETAだけを受理し、着順・払戻は予測入力から除外します。formal_rank_sourceには実際の保存順位の出典を設定してください。オッズ観測時刻不明はnullで保持し、保存時刻で代用しません。

`python tools/freeze_market_rank_audit.py prediction.json --output freezes`

同一mode/race_idのファイルは排他的作成で二重保存を拒否します。既存ファイルを書き換えません。ローカル時刻とハッシュだけでは発走前の存在・結果未閲覧は証明できないため、prospective_eligibleは自動的にtrueになりません。未使用レース台帳と外部時刻証跡を別途管理してください。

結果JSONは `{"race_id":"...","outcome":{"confirmed":true,"finishes":{"1":1},"payouts":{}}}` の別ファイルとします。

`python tools/freeze_market_rank_audit.py freezes/jra_123.json --result outcome.json --output settlement.json`

ハッシュ・race_idを検証して結果だけ別出力へ保存します。過去固定JSONのschemaには触れません。このCLIの比較は候補捕捉用であり、ユーザーが実際に購入したものとして扱いません。

## 制約

旧研究の35ファイル・1,410RというLibrary全体の所持状況は添付一式だけでは再現できません。個々のオッズ観測時刻も不足しています。現時点で未使用開催日の検証結果は0Rです。市場支持との不一致は検出できますが、その原因を欠損値から推測しません。指数そのものの因果的な改善や校正済み期待値は提供しません。
