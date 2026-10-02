# Task 16 Evidence: Memory Record Written and Read Back

*2026-10-02 · Schema: [docs/memory.md](../../memory.md) · Code: `creditcoach/memory/store.py`, `creditcoach/memory/dream.py` · Tests: `tests/test_memory.py` · Script: `uv run python scripts/task16_memory_record.py --live`*

**Definition of Done:** schema documented; a record can be written and read back correctly.

The script uses a temporary memory folder, so these sessions aren't added to the shared `memory/`.

**Result: ✅ PASS** (13/13 checks)

| Check | Result | Detail |
|---|---|---|
| Read back `target_score` | ✅ | `720` |
| Read back `target_date` | ✅ | `'2027-09'` |
| Read back `purpose` | ✅ | `'buy a car'` |
| Read back `quote` | ✅ | `"Remember that I'm saving for a car and want to hit a 720 score by next year."` |
| Read back `session` | ✅ | `'20261002T161642Z-02035d'` |
| Read back `set_at` | ✅ | `'2026-10-02T16:16:42.253Z'` |
| Read back from a different session than the one that wrote it | ✅ | written in 20261002T161642Z-02035d, read in 20261002T161642Z-d8f3e4 |
| A change keeps the purpose and date and records the previous goal (§4 #38) | ✅ | 720 → 750; history [720, 750] |
| Another user's memory is empty | ✅ | USR-002: no goal, no episodes |
| Invalid goals are refused | ✅ | 4 cases |
| Dreaming ran and wrote a new dream file | ✅ | openai/gpt-5-mini; covers 3 sessions |
| Dreaming didn't change the goal (§4 #40: 'Should I aim for 800?') | ✅ | goal stays 750 |
| No credit figure stored as a fact or preference | ✅ | 3 facts, 1 preferences |

## 1. The record written (requirements.md §3 #5)

Session `20261002T161642Z-02035d`, signed in as USR-001 (Aravind). The user says: *"Remember that I'm saving for a car and want to hit a 720 score by next year."*

The `goal_set` line appended to `memory/USR-001/episodes/20261002T161642Z-02035d.jsonl`:

```json
{"v": 1, "ts": "2026-10-02T16:16:42.253Z", "user_id": "USR-001", "session": "20261002T161642Z-02035d", "type": "goal_set", "text": "Remember that I'm saving for a car and want to hit a 720 score by next year.", "meta": {"goal": {"target_score": 720, "target_date": "2027-09", "purpose": "buy a car"}, "previous": null}}
```

The whole episode file:

```json
{"v": 1, "ts": "2026-10-02T16:16:42.244Z", "user_id": "USR-001", "session": "20261002T161642Z-02035d", "type": "login", "text": "", "meta": {"source": "evidence", "recorded_by": "Sudip Roy"}}
{"v": 1, "ts": "2026-10-02T16:16:42.252Z", "user_id": "USR-001", "session": "20261002T161642Z-02035d", "type": "user_message", "text": "Remember that I'm saving for a car and want to hit a 720 score by next year.", "meta": {}}
{"v": 1, "ts": "2026-10-02T16:16:42.253Z", "user_id": "USR-001", "session": "20261002T161642Z-02035d", "type": "goal_set", "text": "Remember that I'm saving for a car and want to hit a 720 score by next year.", "meta": {"goal": {"target_score": 720, "target_date": "2027-09", "purpose": "buy a car"}, "previous": null}}
{"v": 1, "ts": "2026-10-02T16:16:42.254Z", "user_id": "USR-001", "session": "20261002T161642Z-02035d", "type": "assistant_message", "text": "Saved: a 720 score by September 2027, to buy a car.", "meta": {}}
{"v": 1, "ts": "2026-10-02T16:16:42.255Z", "user_id": "USR-001", "session": "20261002T161642Z-02035d", "type": "logout", "text": "", "meta": {}}
```

## 2. The record read back (session `20261002T161642Z-d8f3e4`)

`store.load("USR-001").goal` before the change:

```python
Goal(target_score=720, target_date='2027-09', purpose='buy a car', set_at='2026-10-02T16:16:42.253Z', session='20261002T161642Z-02035d', quote="Remember that I'm saving for a car and want to hit a 720 score by next year.")
```

After *"Actually, change my target to 750."* (§4 #38), the new line keeps the previous goal:

```json
{"v": 1, "ts": "2026-10-02T16:16:42.258Z", "user_id": "USR-001", "session": "20261002T161642Z-d8f3e4", "type": "goal_set", "text": "Actually, change my target to 750.", "meta": {"goal": {"target_score": 750, "target_date": "2027-09", "purpose": "buy a car"}, "previous": {"target_score": 720, "target_date": "2027-09", "purpose": "buy a car", "set_at": "2026-10-02T16:16:42.253Z", "session": "20261002T161642Z-02035d", "quote": "Remember that I'm saving for a car and want to hit a 720 score by next year."}}}
```

### Invalid goals

| Goal | Quote | Result |
|---|---|---|
| `{"target_score": 950}` | the user’s words | ✅ refused: target_score must be an integer from 300 to 900, got 950 |
| `{"target_date": "next year"}` | the user’s words | ✅ refused: target_date must be YYYY-MM, got 'next year' |
| `{"lender": "X", "target_score": 720}` | the user’s words | ✅ refused: unknown goal fields ['lender'] |
| `{"target_score": 720, "target_date": "2027-09", "purpose": "buy a car"}` | (empty) | ✅ refused: a goal needs the user's own words (quote) that set it |

## 3. Dreaming: consolidating the sessions (live)

A third session adds a preference, a life event, a score question and a "should I aim for 800?" question. Dreaming then consolidates all three sessions with `openai/gpt-5-mini`. The dream file it wrote:

```json
{
 "v": 1,
 "user_id": "USR-001",
 "created": "2026-10-02T16:17:10.434Z",
 "model": "openai/gpt-5-mini",
 "recorded_by": "Sudip Roy",
 "covers": [
  "20261002T161642Z-02035d",
  "20261002T161642Z-09ec09",
  "20261002T161642Z-d8f3e4"
 ],
 "semantic": {
  "facts": [
   {
    "text": "saving for a car",
    "sources": [
     "20261002T161642Z-02035d",
     "20261002T161642Z-09ec09"
    ]
   },
   {
    "text": "getting married in March 2027",
    "sources": [
     "20261002T161642Z-09ec09"
    ]
   },
   {
    "text": "wants a car before March 2027",
    "sources": [
     "20261002T161642Z-09ec09"
    ]
   }
  ],
  "goal_candidates": []
 },
 "procedural": {
  "preferences": [
   {
    "text": "prefers short answers",
    "sources": [
     "20261002T161642Z-09ec09"
    ]
   }
  ]
 },
 "episodic": {
  "sessions": [
   {
    "session": "20261002T161642Z-02035d",
    "started": "2026-10-02T16:16:42.244Z",
    "ended": "2026-10-02T16:16:42.255Z",
    "turns": 2,
    "logged_out": true,
    "recorded_by": "Sudip Roy",
    "summary": "User asked to remember they're saving for a car and set a 720 credit-score target for next year."
   },
   {
    "session": "20261002T161642Z-d8f3e4",
    "started": "2026-10-02T16:16:42.256Z",
    "ended": "2026-10-02T16:16:42.258Z",
    "turns": 1,
    "logged_out": false,
    "recorded_by": "Sudip Roy",
    "summary": "User changed their score target from 720 to 750."
   },
   {
    "session": "20261002T161642Z-09ec09",
    "started": "2026-10-02T16:16:42.259Z",
    "ended": "2026-10-02T16:16:42.264Z",
    "turns": 4,
    "logged_out": true,
    "recorded_by": "Sudip Roy",
    "summary": "User requested short answers, said they're getting married in March 2027, want a car before then, and asked about aiming for 800."
   }
  ]
 },
 "changes": [
  {
   "action": "added",
   "kind": "fact",
   "text": "saving for a car",
   "reason": "User stated they are saving for a car in sessions 20261002T161642Z-02035d and 20261002T161642Z-09ec09; memory was previously empty."
  },
  {
   "action": "added",
   "kind": "fact",
   "text": "getting married in March 2027",
   "reason": "User said they are getting married in March 2027 in session 20261002T161642Z-09ec09."
  },
  {
   "action": "added",
   "kind": "fact",
   "text": "wants a car before March 2027",
   "reason": "User said they want a car before their March 2027 wedding in session 20261002T161642Z-09ec09."
  },
  {
   "action": "added",
   "kind": "preference",
   "text": "prefers short answers",
   "reason": "User requested short answers in session 20261002T161642Z-09ec09."
  },
  {
   "action": "added",
   "kind": "fact",
   "text": "720 score target (quoted)",
   "reason": "User explicitly set a 720 target in session 20261002T161642Z-02035d; stored as a goal_candidate instead of a numeric fact."
  },
  {
   "action": "added",
   "kind": "fact",
   "text": "750 score target (quoted)",
   "reason": "User explicitly changed their target to 750 in session 20261002T161642Z-d8f3e4; recorded as a goal_candidate."
  },
  {
   "action": "added",
   "kind": "preference",
   "text": "session summaries",
   "reason": "Added one-line summaries for each new session to aid future context."
  }
 ],
 "rejected": [
  {
   "kind": "goal_candidate",
   "item": {
    "target_score": 720,
    "target_date": null,
    "purpose": "car",
    "quote": "Remember that I'm saving for a car and want to hit a 720 score by next year.",
    "session": "20261002T161642Z-02035d"
   },
   "reason": "already saved as a goal_set"
  },
  {
   "kind": "goal_candidate",
   "item": {
    "target_score": 750,
    "target_date": null,
    "purpose": "car",
    "quote": "Actually, change my target to 750.",
    "session": "20261002T161642Z-d8f3e4"
   },
   "reason": "already saved as a goal_set"
  }
 ]
}
```
