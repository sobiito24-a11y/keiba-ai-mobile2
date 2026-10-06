# NAR protected Top5 group / corner ordering

Model: `nar_top5_corner_order_v1_20261006`.

The canonical saved ability rank <= 5 defines the protected group, including
all horses tied at the fifth-place boundary. The group is never truncated.
Only group members are ordered by:

`0.01180085 * ver3_ability_core - 0.22088414 * netkeiba_corner4_rank`

Missing/invalid core or exact corner rank pins the horse to its original
ordinal slot; known horses fill the remaining slots. No missing-value score
imputation is used. All missing => original ability ordering. Equal scores
use canonical ability rank then horse number. Group membership is independent
of that tie-break. First three are ◎/○/▲; every remaining group horse is △.
Outside horses have no mark. Raw ability values/ranks are never overwritten.

This is a new model, not a claim to reproduce the old nar_simple_ablation model.
No distance/course/star/jockey/weight/material/odds feature contributes.
Existing probability, race grade and research diagnostics remain separate.
Conclusion roles are based on the new group order (center/main/reserve).

`core/nar_top5_order.py` owns calculation, frozen audit and display overlays.
The NAR predictor attaches it after existing predictions. New exports store
`nar_top5_corner_order`; Dashboard stores it also in prediction_result.debug_info.
Saved order audits take precedence over recalculation. Legacy files without
this audit derive a new display from saved inputs without rewriting originals.
UI aliases are not source-frame mutations. Consumers of original tables must
explicitly read this audit to obtain the new final order.

## Retrospective validation (2026-10-06)

| Cohort | Model | Top1 | Top3 | Capture |
|---|---|---:|---:|---:|
|112 specified CSV races|A pure|30|72|90|
|112|B all-field corner|32|76|90|
|112|C protected corner|33|76|90|
|136 all saved|A|37|84|105|
|136|B|38|88|107|
|136|C|40|89|105|
|134 no boundary tie|A|37|83|104|
|134|B|38|87|106|
|134|C|40|88|104|

A/C capture is the protected group, B is strict five horses. The 134-race
figures reproduce the supplied reference. Improvements occur on Sep30/Oct1;
Sep27 Top1 worsens. No coefficients were fitted. This is not future validation.
Two six-member groups: 202630093012 and 202650100106. Missing corner at
202655092709 horse12 stays third. Data/ROI audits are kept outside repositories.

Official payouts on eligible confirmed starters give new◎ single/place ROI
79.4% / 76.9%, so improved ranking does not establish profitability.

Both repositories use identical model code. Checks cover real 136R/1474 horses,
18 JRA races unchanged versus pre-change HTML/card/navigation/PNG projections,
serialization, six-member group, missing slots, 390px sticky scroll and PNG.
