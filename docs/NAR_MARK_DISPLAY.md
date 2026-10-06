# NAR final marks and submark display (2026-10-06)

Ranking model is unchanged: nar_top5_corner_order_v1_20261006.
Display/formal mark map: 1◎,2○,3▲,4✔︎,5△; all further protected boundary-tie
members are △. 4✔︎ is 狙い. No rank, score, ability, jockey or selection change.
Old saved ranking audits remain frozen; display projects the current role map
from their saved group/rank. Source snapshots are never rewritten on restore.

The existing core/nar_race_diagnostics._nar_warning_reason is reused unmodified.
Outside pure rank5, any of: current evaluationTop5, frontcorner group, recent
Top3, same course/distance star, course/distance index>=80 yields a ✓ warning.
Saved ☆/✓/注目/注目馬/注意馬 are preserved as submarks, never formal promotions.
No new jockey, distance or other selection conditions are introduced.

Summary cards: every formal-marked or existing-submarked horse. No three-warning
limit. Blank horses may be omitted only from cards. Detail table remains all
horses; outside formal rank is shown as — while internal ordering is preserved.
Conclusion: center◎,main○▲,aim✔︎,reserve△, formal group only.

Verification:136R/1474 horses,136 fourth-place mark changes,700 existing outside
submarks displayed. Group/rank/scores/purchase unchanged; both apps identical.
JRA18-race detail/card/nav/PNG projection hashes unchanged vs prior HEAD.
390px sticky scroll and details, six-member preservation and saved restore tested.
