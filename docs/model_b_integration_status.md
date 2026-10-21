# Research B integration status

The legacy model A and all saved predictions remain authoritative. The original
B0–B4 coefficient configuration has not been located. `core/model_b.py.CONFIGS`
is intentionally empty: B selection falls back to A with a visible reason.
No synthetic test coefficient is used in live predictions.

Implemented independently of coefficients:
- An allowlisted, deterministic B computation scaffold; corner, pace, odds,
  popularity, formal A score and target-race outcomes are not score inputs.
- Separate A/B UI projections and explicit fallback; buying logic retains A.
- Candidate summary reuses existing stability stars and training labels.
- Separate same-distance + surface last-three-start facts; unknown history is
  distinct from known absence. This display fact is not automatically scored.
- Calendar-week interval presentation; NAR short intervals retain actual days.
- Candidate sorting preserves the selected horse and uses the same comparator
  as all-runner sorting; missing scores remain last, then saved rank/horse number.
- Legacy research panels are collapsed; the old research tab is hidden; paper
  betting panel contrast is corrected without changing betting decisions.

Pending the source configuration: exact B0–B4 reproduction, approved coefficient
registration, pre-race B snapshot persistence, historical A/B outcome comparison,
new-race B default activation, and full production rollout. The scaffold is not
claimed to reproduce the user's historical B model or its reported results.

The optional coefficient schema is provisional until original formulas are
inspected. It supports one shrunken jockey term, training and rest interaction,
weight difference, and one condition term; it does not imply adoption or efficacy.
