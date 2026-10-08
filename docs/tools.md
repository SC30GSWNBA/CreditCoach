# CreditCoach: Tool Specs

*Week 2 · Task #12 · Last updated: 2026-09-30 · Status: Draft for team review*

This spec defines the two tools the agent calls for a user's credit data:

- `get_score_history(user_id, period)` returns monthly scores and the factor behind each change.
- `get_account_summary(user_id)` returns balances, limits and utilization.

Task #13 builds the first tool, Task #14 the second, and Task #15 exposes both through an MCP server (FastMCP, see [team.md](team.md) §2). Both tools serve the synthetic dataset in [data/](../data/README.md) and replace the score and account parts of `creditcoach/user_data.py`, the Week 1 stand-in. The output keeps that module's field names (`points`, `factor_change`, `accounts`), so the system prompt needs no changes.

## 1. Rules for Both Tools

These rules come from requirements.md §6 and the edge cases in §4.7.

1. **The tools do the arithmetic.** Every score change, total and utilization ratio the agent might quote is computed by the tool and returned as a field. The model copies figures and never calculates them. This is how we meet "never fabricate figures" (§6).
2. **`user_id` comes from the signed-in session, never from the model or the user's text.** The MCP host (Task #15) fills `user_id` from the session before each call. If the model passes any other id, the host refuses the call with `USER_MISMATCH` and the tool doesn't run. This covers "What's Vikram's credit score?" (§4 #49). Inside the tool, every row is filtered by `user_id` and checked again before it's returned, as `user_data.py` does today.
3. **No credit file is a normal result, not an error.** A user with no accounts and no score history (USR-004, USR-007) gets `ok: true`, `has_credit_file: false`, empty lists and a `note`. The agent must say "no credit history yet", not show an error or invent a score (§4 #14, #20).
4. **Errors are structured and never partly filled.** A failed call returns the error envelope in §4 and no data. The agent explains the error in plain language and never fills the gap with an estimate.
5. **"Now" is the dataset's latest month, not today's date.** The dataset is a static snapshot (read from `data/*.csv`, or from its copy in Neon when `DATABASE_URL` is set; see `creditcoach/dataset.py`). Both tools return `as_of`, the latest month in `score_history.csv` (today `2026-09-01`). "This month" means that month.
6. **Read-only.** Neither tool writes anything. Goal memory is a separate component (Task #16).
7. **Amounts are whole rupees (`int`).** Ratios are decimals from 0 to 1, rounded to 3 places (0.374 = 37.4%).

## 2. `get_score_history(user_id, period)`

Returns the user's monthly credit scores for a period, with each month's change and its main factor.

### Inputs

| Name | Type | Required | Description |
|---|---|---|---|
| `user_id` | `str` | Yes | Dataset id such as `"USR-001"`. Filled by the host from the session (rule 2). |
| `period` | `str` | Yes | Which months to return. One of the forms below. Case-insensitive; surrounding spaces are ignored. |

**`period` forms.** Every window is anchored to `as_of`, not to today's date.

| Form | Example | Months returned | Typical question |
|---|---|---|---|
| `latest` | `"latest"` | The latest month only | "Why did my score drop this month?" (§3 #1) |
| `last_N_months` (N = 1–24) | `"last_3_months"` | The N months ending at `as_of` | "What happened over the last two months?" (§4 #7) |
| `YYYY-MM` | `"2026-03"` | That one month | "What was my score in March?" (§4 #22) |
| `YYYY-MM:YYYY-MM` | `"2026-07:2026-09"` | Start to end, both included | "Why did my score crash in April?" |
| `all` | `"all"` | Every month on file | "Why does my score keep falling?" (§4 #12) |

The agent turns relative wording into one of these forms. It resolves "March" or "April" to the most recent such month on or before `as_of`.

**Partial overlap.** If the window runs past the months on file (for example `last_24_months` against 12 months of history), the tool returns the months it has and sets `period.clipped: true`. The agent should say the history starts in `available.start`. A window with no months on file at all is an error (`PERIOD_OUT_OF_RANGE`).

### Output

| Field | Type | Description |
|---|---|---|
| `ok` | `bool` | `true` |
| `user_id` | `str` | Echo of the session user |
| `as_of` | `str` (date) | Latest month in the dataset |
| `has_credit_file` | `bool` | `false` if the user has no score history |
| `period` | object | `requested` (the input as given), `start` and `end` (`YYYY-MM`, the months actually returned), `clipped` (`bool`) |
| `available` | object | `start` and `end` (`YYYY-MM`): every month on file for this user. `null` if there is no credit file. |
| `points` | list | One entry per month, oldest first (below) |
| `summary` | object | `start_score`, `end_score`, `net_change`, `lowest`, `highest` (below). `null` if `points` is empty. |
| `note` | `str` | Present only when `has_credit_file` is `false` |

Each entry in `points`:

| Field | Type | Description |
|---|---|---|
| `date` | `str` | First of the month, `YYYY-MM-DD` |
| `score` | `int` | 300–900 |
| `change` | `int` or `null` | Score minus the previous month's score, even when the previous month is outside the window. `null` for the first month on file (the `Baseline` row). |
| `factor_change` | `str` | The `primary_factor_change` label, unchanged, such as `"Utilization spike"` or `"Hard inquiry + utilization spike"` |

`summary` fields:

| Field | Meaning |
|---|---|
| `start_score` | Score in the month before the window, or the first score in the window if the window starts at the baseline |
| `end_score` | Score in the last month of the window |
| `net_change` | `end_score − start_score`, which equals the sum of the non-null `change` values |
| `lowest`, `highest` | `{"date", "score"}` of the lowest and highest month in the window |

`factor_change` is the single label in the dataset for that month. A combined label such as `"Hard inquiry + utilization spike"` has no split between its parts, and the agent must not invent one (§4 #8).

### Example 1: "Why did my score drop 20 points this month?" (USR-001, §3 #1)

Request:

```json
{"user_id": "USR-001", "period": "latest"}
```

Response:

```json
{
  "ok": true,
  "user_id": "USR-001",
  "as_of": "2026-09-01",
  "has_credit_file": true,
  "period": {"requested": "latest", "start": "2026-09", "end": "2026-09", "clipped": false},
  "available": {"start": "2025-10", "end": "2026-09"},
  "points": [
    {"date": "2026-09-01", "score": 650, "change": -20, "factor_change": "Hard inquiry + utilization spike"}
  ],
  "summary": {
    "start_score": 670, "end_score": 650, "net_change": -20,
    "lowest": {"date": "2026-09-01", "score": 650},
    "highest": {"date": "2026-09-01", "score": 650}
  }
}
```

### Example 2: "My score went from 690 to 650. What happened over the last two months?" (USR-001, §4 #7)

Request:

```json
{"user_id": "USR-001", "period": "last_2_months"}
```

Response:

```json
{
  "ok": true,
  "user_id": "USR-001",
  "as_of": "2026-09-01",
  "has_credit_file": true,
  "period": {"requested": "last_2_months", "start": "2026-08", "end": "2026-09", "clipped": false},
  "available": {"start": "2025-10", "end": "2026-09"},
  "points": [
    {"date": "2026-08-01", "score": 670, "change": -20, "factor_change": "Utilization spike"},
    {"date": "2026-09-01", "score": 650, "change": -20, "factor_change": "Hard inquiry + utilization spike"}
  ],
  "summary": {
    "start_score": 690, "end_score": 650, "net_change": -40,
    "lowest": {"date": "2026-09-01", "score": 650},
    "highest": {"date": "2026-08-01", "score": 670}
  }
}
```

`start_score` is 690, the July score just before the window, so the user's "690 to 650" matches `net_change` exactly.

### Example 3: "What was my score in March?" (USR-001, §4 #22)

Request: `{"user_id": "USR-001", "period": "2026-03"}`

Response `points` (other fields as above):

```json
[{"date": "2026-03-01", "score": 678, "change": 5, "factor_change": "On-time payments"}]
```

### Example 4: No credit file (USR-004 Ananya, §4 #14)

Request: `{"user_id": "USR-004", "period": "latest"}`

```json
{
  "ok": true,
  "user_id": "USR-004",
  "as_of": "2026-09-01",
  "has_credit_file": false,
  "period": {"requested": "latest", "start": null, "end": null, "clipped": false},
  "available": null,
  "points": [],
  "summary": null,
  "note": "This user has no credit file yet: no credit accounts and no credit score. Don't state or estimate a score."
}
```

A user with no credit file never gets `PERIOD_OUT_OF_RANGE`, because there is no range to be outside of. The no-credit-file answer is the more useful one.

### Errors

| Code | When | `retryable` | What the agent says |
|---|---|---|---|
| `INVALID_PERIOD` | `period` doesn't match any form: `"last quarter"`, `"2026-13"`, `"last_0_months"`, `"last_30_months"`, or a range whose start is after its end | `false` | Nothing to the user. The agent retries once with a valid form. If it still can't express the request, it asks the user which months they mean. |
| `PERIOD_OUT_OF_RANGE` | The period is valid but no month in it is on file, such as `"2025-01"` | `false` | "I don't have your score for January 2025. Your history on file runs from October 2025 to September 2026." It gives no estimate or nearby month (§4 #46). |
| `UNKNOWN_USER` | `user_id` is empty, malformed, or not in `users.csv` | `false` | "I can't find your account data." This points to a session bug, since the host sets `user_id`. |
| `USER_MISMATCH` | Raised by the host, not the tool: the model asked for a `user_id` other than the session user | `false` | Declines to look up another person's data (§4 #49) |
| `DATA_UNAVAILABLE` | The data source can't be read, or the call takes longer than 5 seconds | `true` | "I can't pull your latest score history right now." It may repeat a figure a tool confirmed earlier this session, labeled as last confirmed (§4 #45). |

Example error, `period: "2025-01"` for USR-001:

```json
{
  "ok": false,
  "error": {
    "code": "PERIOD_OUT_OF_RANGE",
    "message": "No score history for 2025-01. History on file runs from 2025-10 to 2026-09.",
    "retryable": false,
    "details": {"requested": "2025-01", "available": {"start": "2025-10", "end": "2026-09"}}
  }
}
```

## 3. `get_account_summary(user_id)`

Returns every account the user holds, with balances, limits, per-card utilization and ready-made totals.

### Inputs

| Name | Type | Required | Description |
|---|---|---|---|
| `user_id` | `str` | Yes | Dataset id such as `"USR-001"`. Filled by the host from the session (rule 2). |

### Output

| Field | Type | Description |
|---|---|---|
| `ok` | `bool` | `true` |
| `user_id` | `str` | Echo of the session user |
| `as_of` | `str` (date) | Latest month in the dataset. Balances are a snapshot at this date. |
| `has_credit_file` | `bool` | `false` if the user has no accounts |
| `accounts` | list | One entry per account, in `account_id` order (below) |
| `totals` | object | Sums and the overall ratio (below) |
| `note` | `str` | Present only when there is something the agent must not misread: no credit file, or no credit card (so no utilization ratio) |

Each entry in `accounts`:

| Field | Type | Description |
|---|---|---|
| `account_id` | `str` | Such as `"ACC-01"` |
| `type` | `str` | `account_type` from the dataset: `Credit Card`, `Education Loan`, `Auto Loan`, `Home Loan`, `Personal Loan` or `Instant Loan App` |
| `category` | `str` | `"revolving"` for `Credit Card`, `"installment"` for every loan type |
| `balance_inr` | `int` | Current balance |
| `credit_limit_inr` | `int` or `null` | Revolving accounts only |
| `utilization_ratio` | `float` or `null` | Revolving accounts only: `balance_inr ÷ credit_limit_inr`, rounded to 3 places |
| `high_risk_product` | `bool` | `true` for `Instant Loan App`, the dataset's payday-loan equivalent. The agent flags these proactively (§6, §4 #12, #29). |

The tool computes `utilization_ratio` from the balance and limit. It does not read the `utilization_ratio` column in `accounts.csv`, which is rounded to 2 places. For ACC-01 the tool returns 0.787 (₹59,000 ÷ ₹75,000), where the CSV has 0.79.

`totals`:

| Field | Type | Description |
|---|---|---|
| `revolving_balance_inr` | `int` | Sum of credit card balances |
| `revolving_limit_inr` | `int` | Sum of credit card limits |
| `overall_utilization_ratio` | `float` or `null` | `revolving_balance_inr ÷ revolving_limit_inr`, rounded to 3 places. `null` when the user has no credit card, never `0`. |
| `installment_balance_inr` | `int` | Sum of loan balances. Loans don't count toward utilization. |
| `total_balance_inr` | `int` | Revolving plus installment: total debt (§4 #17) |
| `revolving_count`, `installment_count` | `int` | Number of accounts of each kind |

### Example 1: "What's my current credit utilization ratio?" (USR-001, §3 #2)

Request:

```json
{"user_id": "USR-001"}
```

Response:

```json
{
  "ok": true,
  "user_id": "USR-001",
  "as_of": "2026-09-01",
  "has_credit_file": true,
  "accounts": [
    {"account_id": "ACC-01", "type": "Credit Card", "category": "revolving", "balance_inr": 59000, "credit_limit_inr": 75000, "utilization_ratio": 0.787, "high_risk_product": false},
    {"account_id": "ACC-02", "type": "Credit Card", "category": "revolving", "balance_inr": 11000, "credit_limit_inr": 100000, "utilization_ratio": 0.11, "high_risk_product": false},
    {"account_id": "ACC-03", "type": "Education Loan", "category": "installment", "balance_inr": 420000, "credit_limit_inr": null, "utilization_ratio": null, "high_risk_product": false},
    {"account_id": "ACC-04", "type": "Auto Loan", "category": "installment", "balance_inr": 305000, "credit_limit_inr": null, "utilization_ratio": null, "high_risk_product": false},
    {"account_id": "ACC-05", "type": "Credit Card", "category": "revolving", "balance_inr": 4750, "credit_limit_inr": 25000, "utilization_ratio": 0.19, "high_risk_product": false}
  ],
  "totals": {
    "revolving_balance_inr": 74750,
    "revolving_limit_inr": 200000,
    "overall_utilization_ratio": 0.374,
    "installment_balance_inr": 725000,
    "total_balance_inr": 799750,
    "revolving_count": 3,
    "installment_count": 2
  }
}
```

### Example 2: Loan only, no credit card (USR-005 Kavya, §4 #19)

Request: `{"user_id": "USR-005"}`

```json
{
  "ok": true,
  "user_id": "USR-005",
  "as_of": "2026-09-01",
  "has_credit_file": true,
  "accounts": [
    {"account_id": "ACC-10", "type": "Education Loan", "category": "installment", "balance_inr": 330000, "credit_limit_inr": null, "utilization_ratio": null, "high_risk_product": false}
  ],
  "totals": {
    "revolving_balance_inr": 0,
    "revolving_limit_inr": 0,
    "overall_utilization_ratio": null,
    "installment_balance_inr": 330000,
    "total_balance_inr": 330000,
    "revolving_count": 0,
    "installment_count": 1
  },
  "note": "This user has no credit card, so there is no utilization ratio. Don't report 0% or invent a limit."
}
```

### Example 3: High-risk product (USR-012 Aditya, §4 #12, #29)

Request: `{"user_id": "USR-012"}`. The response lists ACC-20 (card, 0.831), ACC-21 (home loan), ACC-22 (personal loan) and:

```json
{"account_id": "ACC-23", "type": "Instant Loan App", "category": "installment", "balance_inr": 24000, "credit_limit_inr": null, "utilization_ratio": null, "high_risk_product": true}
```

with `totals.overall_utilization_ratio` 0.831 (₹3,78,100 ÷ ₹4,55,000) and `totals.total_balance_inr` 4237100.

### Example 4: No credit file (USR-007 Karthik, §4 #20)

```json
{
  "ok": true,
  "user_id": "USR-007",
  "as_of": "2026-09-01",
  "has_credit_file": false,
  "accounts": [],
  "totals": {
    "revolving_balance_inr": 0, "revolving_limit_inr": 0, "overall_utilization_ratio": null,
    "installment_balance_inr": 0, "total_balance_inr": 0, "revolving_count": 0, "installment_count": 0
  },
  "note": "This user has no credit file yet: no credit accounts and no credit score. Don't state or estimate a score."
}
```

### Errors

| Code | When | `retryable` | What the agent says |
|---|---|---|---|
| `UNKNOWN_USER` | `user_id` is empty, malformed, or not in `users.csv`, such as `"USR-999"` | `false` | "I can't find your account data." |
| `USER_MISMATCH` | Raised by the host: the model asked for a `user_id` other than the session user | `false` | Declines to look up another person's data (§4 #49) |
| `DATA_UNAVAILABLE` | The data source can't be read, or the call takes longer than 5 seconds | `true` | "I can't pull your latest account data right now." It may repeat a figure a tool confirmed earlier this session, labeled as last confirmed (§4 #45). |

Example error, `user_id: "USR-999"`:

```json
{
  "ok": false,
  "error": {
    "code": "UNKNOWN_USER",
    "message": "No user with id USR-999.",
    "retryable": false,
    "details": {"user_id": "USR-999"}
  }
}
```

## 4. Error Envelope and MCP Mapping

Both tools share one error shape:

```json
{"ok": false, "error": {"code": "<CODE>", "message": "<one sentence for logs>", "retryable": <bool>, "details": {}}}
```

- `code` is the stable field. Tests, guardrails and the Week 4 dashboard match on `code`, never on `message`.
- `message` is for logs and traces, not for showing to the user as written.
- Over MCP (Task #15), a success returns the JSON object as the tool result. An error returns the envelope with the MCP result's `isError` set to `true`, so the host can count failures for the §6 tool-failure rate without parsing text.
- The host retries a `retryable` error once. If the retry fails, the agent degrades as described in the tables above.
- Every call, success or error, is logged with the tool name, `user_id`, arguments, `ok`, error `code` and latency. Task #26 adds the trace id.

**As built (Task 15):** the server is `creditcoach/tools/server.py` and the host is `creditcoach/agent/mcp_host.py`. The host adds two codes of its own: `UNKNOWN_TOOL` (the model named a tool that doesn't exist) and `INVALID_ARGUMENTS` (the model's arguments weren't valid JSON or failed the server's validation). Neither is retryable. `USER_MISMATCH` and the 5-second timeout are enforced there, as §1 and the error tables describe.

**My credit tab (2026-10-06):** the chat UI's My credit tab (`creditcoach/app/charts.py`, wired in `creditcoach/app/main.py`) calls both tools directly, in process, not over MCP: it has no model in the loop, so there is no model-supplied `user_id` to check. It passes only the signed-in session's user id (§1 rule 2), and `tests/test_charts.py` checks that a page load reads no other user's rows.

**Prefetch (2026-10-02):** for every signed-in question, the host calls `get_score_history(period="last_12_months")` and `get_account_summary()` over MCP before the model's first turn, and passes both results to the model as tool results (`PREFETCH` in `creditcoach/agent/pipeline.py`). The model can still call either tool for other periods. The 50-query run showed the model skipping the tools on plan, product and goal questions; prefetching removes that failure and saves a model turn. A prefetched call follows the same rules, timeout, retry and error envelope as any other.

## 5. Test Cases for Tasks #13 and #14

Each task's Definition of Done asks for a known case and an error case. These are the minimum; the implementing task may add more. T1–T8 and T15 for `get_score_history` are automated in `tests/test_score_history.py` (Task 13), and T9–T15 for `get_account_summary` in `tests/test_account_summary.py` (Task 14). The latter also checks that every complete JSON example in §3 is exactly what the tool returns, so this spec and the code can't drift apart.

Beyond T1–T15, every figure that an expected answer in requirements.md §3 and §4 relies on (146 values across the 50 queries, from `creditcoach/evals/golden_queries.json`) is read from the tools and compared on every pull request by `tests/test_golden_queries.py`. The Task 13 and Task 14 test logs list each one.

| # | Tool | Input | Expected |
|---|---|---|---|
| T1 | `get_score_history` | USR-001, `latest` | One point: 650, change −20, `Hard inquiry + utilization spike` |
| T2 | `get_score_history` | USR-001, `last_2_months` | 670 (−20, `Utilization spike`), 650 (−20); `start_score` 690, `net_change` −40 |
| T3 | `get_score_history` | USR-001, `2026-03` | 678, change +5, `On-time payments` |
| T4 | `get_score_history` | USR-012, `all` | 12 points, 746 → 684, `net_change` −62; first point's `change` is `null` |
| T5 | `get_score_history` | USR-001, `last_24_months` | 12 points, `clipped: true` |
| T6 | `get_score_history` | USR-004, `latest` | `ok: true`, `has_credit_file: false`, no points |
| T7 | `get_score_history` | USR-001, `2025-01` | `PERIOD_OUT_OF_RANGE`, `available` 2025-10 to 2026-09 |
| T8 | `get_score_history` | USR-001, `last quarter` | `INVALID_PERIOD` |
| T9 | `get_account_summary` | USR-001 | 5 accounts; ACC-01 0.787; overall 0.374 (₹74,750 ÷ ₹2,00,000); total ₹7,99,750 |
| T10 | `get_account_summary` | USR-013 | 2 cards at 0.089 each; overall 0.089 (₹59,200 ÷ ₹6,65,000) |
| T11 | `get_account_summary` | USR-005 | 1 loan; `overall_utilization_ratio` `null` with a note |
| T12 | `get_account_summary` | USR-012 | ACC-23 `high_risk_product: true`; overall 0.831 |
| T13 | `get_account_summary` | USR-007 | `ok: true`, `has_credit_file: false`, no accounts |
| T14 | `get_account_summary` | USR-999 | `UNKNOWN_USER` |
| T15 | Both | Any user | No row in the output has another user's `user_id` |

## 6. Open Questions for Team Review

1. **Rounding.** The tools return ratios to 3 places, so ACC-01 is 78.7%. requirements.md §4 #15 says "79%" and §4 #18 says "9%" for USR-013's cards (8.9% at 3 places). Both are roundings of the tool's figure, but the Task #27 scorers should accept either or check against the tool output. Proposal: keep 3 places, and update the scorers rather than requirements.md. *Done in the golden set (2026-10-02): each figure check accepts both roundings, for example "79%" or "78.7%".*
2. **Timeout.** 5 seconds is a starting value. Local CSV reads take milliseconds, so the timeout only matters when Task #32 simulates a slow API.
3. **More tools.** Profile fields from `users.csv` (such as `pays_card` and `goals_2yr`) are not part of either tool. They stay in the prompt context through `user_data.py` until Task #16 decides whether stored goals replace `goals_2yr`.

## 7. Sign-off

| Member | Reviewed | Date |
|---|---|---|
| Aman | [ ] | |
| Anil | [ ] | |
| Sudip | ✅ Reviewed and Signed Off | 2026-10-02 |
