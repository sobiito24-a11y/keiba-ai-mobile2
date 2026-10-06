# Jockey positive evidence v1

Version `jockey_positive_v1_20261006`, shared source in both applications.

- JRA absolute: displayed place percentage >=30.0 with >=20 starts.
- NAR absolute: displayed place percentage >=35.0 with >=20 starts.
- Upgrade: saved rider change, both samples >=20, current minus previous >=15pt.
- Both => exactly one positive evidence, no numerical score addition.
- Continuing riders can qualify absolute only. Unknown values stay None/neutral.
- Shadow: JRA25..<30 / NAR30..<35; upgrade10..<15, samples>=20.

Inputs reuse `jockey_place_text` and saved course starts. Previous statistics
use explicit saved fields, or exact normalized name + identical condition from
another horse's saved statistics in the SAME race. Conflicting or unmatched
statistics remain missing. No cross-race/new statistics, result or odds input.
Saved change status takes precedence over legacy identity heuristics.

The new evidence is displayed beside jockey statistics and on conclusion/all
horse cards. It is saved independently as `jockey_positive_evidence`, with
source, missing status, both flags, one count, reason and version. Saved audits
are frozen on restore. Existing material/shadow payloads remain untouched.

No new mark-promotion rule was specified: existing final-role allocation is
preserved. JRA final mark layer records one jockey positive reason, while
strong negative caps retain precedence. NAR group/order/marks remain those of
`nar_top5_corner_order_v1_20261006`; jockey evidence only supports the explanation.
Outside horses cannot enter the formal group through this feature.

Retrospective audit: 54 JRA races/768 horses and136 NAR races/1474 horses.
All ranks/scores/groups/marks unchanged. Both applications identical.
JRA absolute inside Top5:61 horses,12 wins,31 places. Removing exactly30.0%
(3 horses) reproduces the reported58/12/31; specified inclusive threshold wins.
NAR absolute inside group:220 horses,53 wins,129 places.
Upgrade with identifiable previous statistics:JRA4 (2 wins,3 places),NAR13
(4 wins,8 places). ReportedNAR22 not reproduced; missing previous statistics
are not inferred to force matching counts.

No changed-mark horses; improvement in mark ROI is not claimed. NAR mark ROI
remains the prior model's values. JRA54-race payout source unavailable in the
selected input set, so no JRA ROI is fabricated.

Full audit CSV/report is outside the repos under2026-10-06/jockey_positive.
