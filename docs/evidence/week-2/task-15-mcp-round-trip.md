# Task 15 Evidence: MCP Round Trip

*2026-09-30 · Code: `creditcoach/tools/server.py` (MCP server), `creditcoach/agent/mcp_host.py` (MCP host), `creditcoach/agent/pipeline.py` (agent loop) · Tests: `tests/test_mcp.py` · Script: `uv run python scripts/task15_mcp_round_trip.py`*

**Definition of Done:** the agent calls both tools via MCP and uses their results in a live response.

> **Note (2026-10-03): prefetch.** This run predates the prefetch added on 2026-10-02: for every signed-in question the host now calls `get_score_history(period="last_12_months")` and `get_account_summary()` over MCP before the model's first turn, and the model can still call either tool for more (for example `period="latest"`). The run below shows the model choosing both tools itself, which `run_agent(..., prefetch=False)` still does and `tests/test_mcp.py` covers. The prefetched flow is shown live on all 50 queries in [task-15-all-queries.md](task-15-all-queries.md) and is specified in [docs/tools.md](../../tools.md) §4.

**How a question flows:** retrieve 3 corpus passages → the chat model gets the two tools (without `user_id`) → for each tool call it makes, the MCP host fills `user_id` from the signed-in session and calls the CreditCoach MCP server over stdio → each result goes back to the model as a `tool` message → the model answers from those results.

**Result: ✅ PASS**

| Check | Result |
|---|---|
| Both tools called and succeeded | ✅ get_account_summary, get_score_history |
| Every call went through the MCP server (one host log line per call) | ✅ 2 calls, 2 log lines |
| Every call ran for the signed-in user only | ✅ USR-001 |
| The answer states the key figures from the tool output | ✅ 6/6 (table below) |

## 1. Tools the MCP server lists

The server's schemas include `user_id`. The host removes it before showing the tools to the model, and fills it from the session on every call.

| Tool | Parameters (server) | Parameters the model sees |
|---|---|---|
| `get_score_history` | `user_id`, `period` | `period` |
| `get_account_summary` | `user_id` | (none) |

## 2. The question

Signed in as **USR-001** (Aravind). Asked: *"Why did my credit score drop 20 points this month, and what's my credit utilization right now?"*

Retrieved passages: `why-scores-drop#01`, `why-scores-drop#02`, `factor-credit-utilization#01` (14.3s).

## 3. Tool calls, in order

| # | Tool | Model's arguments | `user_id` (from session) | Result | Attempts | Latency |
|---|---|---|---|---|---|---|
| 1 | `get_score_history` | `{"period": "latest"}` | USR-001 | ok | 1 | 8 ms |
| 2 | `get_account_summary` | `{}` | USR-001 | ok | 1 | 3 ms |

MCP host log (one JSON line per call):

```
tool_call {"tool": "get_score_history", "user_id": "USR-001", "arguments": {"period": "latest"}, "ok": true, "code": null, "attempts": 1, "ms": 8}
tool_call {"tool": "get_account_summary", "user_id": "USR-001", "arguments": {}, "ok": true, "code": null, "attempts": 1, "ms": 3}
```

### Call 1: `get_score_history` result (sent back to the model)

```json
{
  "ok": true,
  "user_id": "USR-001",
  "as_of": "2026-09-01",
  "has_credit_file": true,
  "period": {
    "requested": "latest",
    "start": "2026-09",
    "end": "2026-09",
    "clipped": false
  },
  "available": {
    "start": "2025-10",
    "end": "2026-09"
  },
  "points": [
    {
      "date": "2026-09-01",
      "score": 650,
      "change": -20,
      "factor_change": "Hard inquiry + utilization spike"
    }
  ],
  "summary": {
    "start_score": 670,
    "end_score": 650,
    "net_change": -20,
    "lowest": {
      "date": "2026-09-01",
      "score": 650
    },
    "highest": {
      "date": "2026-09-01",
      "score": 650
    }
  }
}
```

### Call 2: `get_account_summary` result (sent back to the model)

```json
{
  "ok": true,
  "user_id": "USR-001",
  "as_of": "2026-09-01",
  "has_credit_file": true,
  "accounts": [
    {
      "account_id": "ACC-01",
      "type": "Credit Card",
      "category": "revolving",
      "balance_inr": 59000,
      "credit_limit_inr": 75000,
      "utilization_ratio": 0.787,
      "high_risk_product": false
    },
    {
      "account_id": "ACC-02",
      "type": "Credit Card",
      "category": "revolving",
      "balance_inr": 11000,
      "credit_limit_inr": 100000,
      "utilization_ratio": 0.11,
      "high_risk_product": false
    },
    {
      "account_id": "ACC-03",
      "type": "Education Loan",
      "category": "installment",
      "balance_inr": 420000,
      "credit_limit_inr": null,
      "utilization_ratio": null,
      "high_risk_product": false
    },
    {
      "account_id": "ACC-04",
      "type": "Auto Loan",
      "category": "installment",
      "balance_inr": 305000,
      "credit_limit_inr": null,
      "utilization_ratio": null,
      "high_risk_product": false
    },
    {
      "account_id": "ACC-05",
      "type": "Credit Card",
      "category": "revolving",
      "balance_inr": 4750,
      "credit_limit_inr": 25000,
      "utilization_ratio": 0.19,
      "high_risk_product": false
    }
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

## 4. The answer

*openai/gpt-5 · 12.9s from the end of retrieval to the answer, including tool calls*

> Short answer
> - Your score fell 20 points this month to 650 because of a hard inquiry plus a utilization spike (a high reported card balance).
> - Your overall credit utilization right now is 37.4%: ₹74,750 ÷ ₹2,00,000 = 37.4%.
>
> What moved this month
> - Latest score: 650 (change: −20). Reason noted in your file: “Hard inquiry + utilization spike.”
> - Card-by-card utilization:
>   - Card ending ACC-01: ₹59,000 ÷ ₹75,000 = 78.7% (this is the main spike)
>   - Card ending ACC-02: ₹11,000 ÷ ₹1,00,000 = 11%
>   - Card ending ACC-05: ₹4,750 ÷ ₹25,000 = 19%
> - Scores commonly dip when utilization goes above ~30% on any card or across all cards, and a hard inquiry adds a few points of drag. Typical impacts: utilization spikes ~10–40 points; a hard inquiry ~2–10 points [1][3].
>
> What to do next
> - Pay down the high card before the next statement date. To get ACC-01 below 30%, aim for a balance under ₹22,500 (₹75,000 × 30%). From ₹59,000, that means about ₹36,500 to clear.
> - Also try to bring overall utilization under 30% (under ₹60,000 across your ₹2,00,000 total limit). From ₹74,750, that’s about ₹14,750 to reduce. Prioritising ACC-01 will likely achieve both.
> - Avoid new credit applications for a while so the recent hard inquiry can age off its impact [1][2].
>
> Good news: utilization-related drops are usually short-lived once the lower balances are reported, often within a cycle after you pay them down [3].

## 5. Figures in the answer, traced to the tool output

| Figure | Tool value | Source | In the answer |
|---|---|---|---|
| Score change this month | -20 (2026-09) | `get_score_history → points[-1].change` | ✅ |
| Factor behind it | Hard inquiry + utilization spike | `get_score_history → points[-1].factor_change` | ✅ |
| Overall utilization | 0.374 | `get_account_summary → totals.overall_utilization_ratio` | ✅ |
| Card balances total | ₹74,750 | `get_account_summary → totals.revolving_balance_inr` | ✅ |
| Card limits total | ₹2,00,000 | `get_account_summary → totals.revolving_limit_inr` | ✅ |
| Highest-utilization card (ACC-01) | ₹59,000 ÷ ₹75,000 = 0.787 | `get_account_summary → accounts[ACC-01]` | ✅ |

Any other figure in the answer (for example a paydown target) must be calculated from these values with its inputs shown, per the system prompt's rule 1.
