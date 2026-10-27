# Eval: baseline vs after-fixes

*Before: [eval-baseline.md](eval-baseline.md) (2026-10-26 11:30) · After: [eval-after-fixes.md](eval-after-fixes.md) (2026-10-27 21:22) · `uv run python -m creditcoach.evals --compare baseline --label after-fixes`*

| | Cases | Before | After | Change |
|---|---|---|---|---|
| **Like for like** (measurement unchanged) | 41 | 33 (80%) | 36 (88%) | +3 |
| Measurement changed (see below) | 9 | 3 (33%) | 9 (100%) | +6 |
| **All** | 50 | 36 (72%) | 45 (90%) | +9 |

Re-scored with today's checks (no new answers), the earlier run passes 37 of 50, so changed checks alone account for +1.

| | Before | After |
|---|---|---|
| Cases passing expected | 44 | 48 |
| Cases passing figures | 44 | 44 |
| Cases passing judge | 39 | 45 |
| Cases passing run | 49 | 50 |
| Judge averages (grounded, clear) | 4.82, 4.92 | 4.98, 4.98 |
| Time per answer (median, longest) | 12.5 s, 35.5 s | 19.1 s, 50.6 s |

## Cases that changed

| Case | Before | After | Measurement changed? | Still failing on |
|---|---|---|---|---|
| §3 #3 | ❌ Fail | ✅ Pass | no | – |
| §3 #5 | ❌ Fail | ✅ Pass | no | – |
| §4 #9 | ❌ Fail | ❌ Fail | no | judge: meets expected: no; grounded 5/5; clear 5/5. The reply correctly cites the two dips (−9 in Aug, −2 in Sep), labels them as hard inquiries and confirms no late payments, but it missed the expected advice about grouping/submitting any remaining applications within a short shopping window (inste |
| §4 #11 | ❌ Fail | ✅ Pass | no | – |
| §4 #12 | ✅ Pass | ❌ Fail | no | expected: missing 'counsel'; judge: meets expected: no; grounded 4/5; clear 5/5. The reply correctly summarizes the 12‑month decline (746→684, −62), cites repeated utilization spikes and the March hard inquiry, and flags the Instant Loan App; however it omits the explicit recent-step drop wording (− |
| §4 #15 | ✅ Pass | ❌ Fail | no | judge: meets expected: no; grounded 5/5; clear 4/5. Numbers match the account-summary data exactly, but the reply omitted explicitly noting that education and auto loans are excluded from utilization and why (installment loans have no credit limit), which the expected behavior required. |
| §4 #16 | ❌ Fail | ✅ Pass | no | – |
| §4 #21 | ✅ Pass | ❌ Fail | no | expected: missing 'payment plan' / 'emi'; judge: meets expected: no; grounded 5/5; clear 5/5. The reply correctly reports 83.1%, links the high utilization to the recent score drops and gives practical timing and payment steps, but it omits explicitly advising the user to talk to the card issuer abo |
| §4 #22 | ❌ Fail | ✅ Pass | no | – |
| §4 #23 | ❌ Fail | ✅ Pass | the goal its row assumes is now stored first | – |
| §4 #25 | ❌ Fail | ✅ Pass | the goal its row assumes is now stored first | – |
| §4 #27 | ❌ Fail | ✅ Pass | no | – |
| §4 #28 | ✅ Pass | ❌ Fail | no | judge: meets expected: no; grounded 5/5; clear 5/5. The reply correctly uses the user's score (795) and card utilization (~27.2%) and gives 1–3 prioritized, accurate steps, but it goes beyond the requirement by proposing a specific goal/timeframe (keeping utilization under 15% for three cycles) whic |
| §4 #36 | ❌ Fail | ✅ Pass | the goal its row assumes is now stored first | – |
| §4 #37 | ❌ Fail | ✅ Pass | the goal its row assumes is now stored first | – |
| §4 #38 | ❌ Fail | ✅ Pass | the goal its row assumes is now stored first | – |
| §4 #41 | ❌ Fail | ✅ Pass | the check also accepts "within a cycle" and "statement date" | – |
| §4 #46 | ❌ Fail | ✅ Pass | no | – |
