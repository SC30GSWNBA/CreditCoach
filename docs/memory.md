# CreditCoach: Memory Schema

*Week 2 · Tasks #16 (schema) and #17 (recall) · Last updated: 2026-10-07 (moved to Neon Postgres) · Status: Draft for team review · Code: `creditcoach/memory/`*

CreditCoach remembers each user across sessions, machines and teammates. This document defines what is stored, where, and the rules that keep it trustworthy (Task #16), and how answers use it (Task #17, §7). Task #18 shows it in the agent-trace panel.

## 1. What is remembered

| Kind | What it holds | Example | Written by |
|---|---|---|---|
| **Episodic** | What happened, in order: sign-ins, every question and reply, explicit goal changes, errors, sign-outs | "On 2 Oct, Aravind asked why his score dropped; the reply used `get_score_history`" | The chat UI, live, on every event |
| **Semantic** | What is true about the user: their **goal** (target score, target date, purpose) and facts they've told us | "Saving for a car"; goal 720 by 2027-09 | Goal: only an explicit `goal_set` event. Facts: dreaming |
| **Procedural** | How the user likes to be helped | "Prefers short answers"; "wants amounts in lakh" | Dreaming |

Credit figures (scores, balances, limits, utilization) are **never** stored in memory. They go stale, and system prompt rule 1 requires them to come live from the tools. An episode keeps which tools a reply called, but not what the tools returned.

## 2. Where it lives

Memory lives in a shared **Neon Postgres** database (free plan), so every teammate and every deployment reads and writes the same history as it happens. The connection string is `DATABASE_URL` in `.env`; `CREDITCOACH_MEMORY_BACKEND` (`postgres` or `files`) overrides the choice. The code is `creditcoach/memory/pg.py`, behind the same `store` functions as before.

| Table | Holds | Replaces |
|---|---|---|
| `memory_events` | One row per episode event: `id` (insertion order), `v`, `ts` (`timestamptz`), `user_id`, `session`, `type`, `text`, `meta` (JSONB). An episode is every row with the same `session` | `episodes/<session>.jsonl` |
| `memory_dreams` | One row per dream: `id` (`<timestamp>-<hex>`, as the file name was), `user_id`, `created`, `body` (the whole dream as JSONB). The newest `created` is current | `dreams/<id>.json` |

The tables are created on first use. Both are **append-only**: a trigger refuses every `UPDATE` and `DELETE`, the same guarantee the files gave. The fields and rules in §3 to §5 are unchanged; only the storage moved.

**Why a hosted database now:** the file design existed because a shared SQLite file would conflict on every `git pull` (the kickoff plan in [team.md](team.md) §2). Neon has no such conflicts, needs no pull requests to share sessions, and survives a redeploy (Hugging Face Spaces and Render wipe local disk). Neon's free plan was chosen over Supabase (its free projects pause after a week idle) and MongoDB Atlas (no backups on the free tier). An idle Neon database suspends after 5 minutes, so the first request afterwards waits a moment while it wakes.

**The files backend and the archive.** Without `DATABASE_URL`, memory is written to plain files, as before:

```
memory/
  README.md
  USR-001/
    episodes/20261002T140322Z-a1b2c3.jsonl   # one file per chat session: one JSON event per line
    dreams/20261003T091502Z-0a1b2c.json      # consolidated memory; the newest file is current
```

Tests and the evidence scripts always use files in a temporary folder, so they never write to the shared database. The files committed in `memory/` are the archive from before the move, and they have been imported into Neon. `uv run python scripts/memory_import.py` copies file sessions into Neon; it skips any session or dream that is already there, so anyone can run it. `scripts/memory_sync.py` (sharing files through pull requests) only applies to the files backend.

## 3. Episode files (episodic memory)

Path `memory/<user_id>/episodes/<session>.jsonl`. Each line is one event:

| Field | Type | Meaning |
|---|---|---|
| `v` | int | Schema version, `1` |
| `ts` | string | UTC time, ISO 8601 to the millisecond (`2026-10-02T14:03:22.481Z`), so events in the same second stay in order |
| `user_id` | string | `USR-NNN`. Always the signed-in user; events for anyone else are ignored on read |
| `session` | string | The episode id, the same as the file name |
| `type` | string | One of the event types below |
| `text` | string | The message, reply, quote or error, depending on `type` |
| `meta` | object | Details for that type |

| `type` | `text` | `meta` |
|---|---|---|
| `login` | — | `source` (`chat_ui`, `cli`, `eval`, `evidence`), `recorded_by` (`git config user.name` of the machine), `gradio_session` |
| `user_message` | What the user typed | — |
| `assistant_message` | CreditCoach's answer | `model`, `passages` (chunk ids), `tools` (`tool`, `arguments`, `ok`, `code`; never the result), `seconds` |
| `error` | Short description, e.g. `TimeoutError: answer service failed` | — |
| `goal_set` | The user's own words that set the goal | `goal` (§4), `previous` (the goal it replaced, or `null`) |
| `goal_cleared` | The user's own words that dropped the goal | — |
| `logout` | — | — |
| `session_end` | — (the tab was closed or reloaded) | — |

Example (one session, shortened):

```json
{"v": 1, "ts": "2026-10-02T14:03:22.000Z", "user_id": "USR-001", "session": "20261002T140322Z-a1b2c3", "type": "login", "text": "", "meta": {"source": "chat_ui", "recorded_by": "Sudip Roy", "gradio_session": "k2j3..."}}
{"v": 1, "ts": "2026-10-02T14:03:40.000Z", "user_id": "USR-001", "session": "20261002T140322Z-a1b2c3", "type": "user_message", "text": "Why did my credit score drop 20 points this month?", "meta": {}}
{"v": 1, "ts": "2026-10-02T14:03:55.000Z", "user_id": "USR-001", "session": "20261002T140322Z-a1b2c3", "type": "assistant_message", "text": "Your score fell from 670 to 650 ...", "meta": {"model": "openai/gpt-5", "passages": ["why-scores-drop#01"], "tools": [{"tool": "get_score_history", "arguments": {"period": "latest"}, "ok": true, "code": null}], "seconds": 14.2}}
{"v": 1, "ts": "2026-10-02T14:05:10.000Z", "user_id": "USR-001", "session": "20261002T140322Z-a1b2c3", "type": "logout", "text": "", "meta": {}}
```

A line that isn't valid JSON (for example, the app was killed mid-write) is skipped on read; the rest of the file still loads.

## 4. The goal record (semantic memory)

The record Task #16 specifies. It lives in `goal_set` events, and the current goal is the result of replaying them in time order.

| Field | Type | Rule |
|---|---|---|
| `target_score` | int or `null` | 300 to 900, the Indian bureau range |
| `target_date` | string or `null` | `YYYY-MM`, or `YYYY` when the user named only a year ("by next year", said in 2026, is `2027`) |
| `purpose` | string or `null` | The user's words, 1 to 200 characters ("buy a car") |

At least one field must be set. Read back as a `Goal`, the record also carries `set_at` (when), `session` (where) and `quote` (the user's words), so every goal can be traced to what the user actually said.

**Rules that keep the goal the user's own** (requirements.md §6: "never silently override a user's stated goal"):

1. The goal changes only through `store.set_goal()`, which writes a `goal_set` event. It refuses a goal without the user's own words (`quote`), and it records the previous goal so a change can be shown as old → new (requirements.md §4 #38).
2. Dreaming never writes a goal. It may only list a **goal candidate**, with a quote that must match one of the user's messages word for word. The chat asks the user to confirm a candidate before it becomes a `goal_set` (§7).
3. A question such as "Should I aim for 800 instead?" is not a goal change (§4 #40). The stored goal stays until the user explicitly confirms.
4. Clearing a goal is also an explicit event (`goal_cleared`) with the user's words. Earlier goals stay in the history.

## 5. Dream files (consolidated semantic and procedural memory)

Dreaming is CreditCoach's version of the memory-consolidation technique Anthropic calls "dreaming" for Claude Managed Agents. It's built on our own stack (the OpenRouter `SMALL_MODEL`), because CreditCoach runs on GPT-5 through OpenRouter, not on Managed Agents. Between sessions it reads the episodes the last dream hasn't seen, together with the current consolidated memory, and writes a new dream file. In that file it adds new facts and preferences, merges duplicates, drops what is stale or contradicted (the newer statement wins), and summarises each new session.

**When it runs:** in the background whenever a user signs in to the chat UI, for that user's earlier sessions (the session in progress waits for the next sign-in). It can also be run by hand: `uv run python -m creditcoach.memory.dream --user USR-001` or `--all`.

Path `memory/<user_id>/dreams/<timestamp>-<hex>.json`:

| Field | Meaning |
|---|---|
| `v`, `user_id`, `created`, `model`, `recorded_by` | Version, owner, when, which model consolidated, on whose machine |
| `covers` | Every session id consolidated so far, cumulative. Episodes not listed are consolidated next time |
| `semantic.facts` | `[{"text", "sources": [session ids]}]`, at most 20, each under 200 characters |
| `semantic.goal_candidates` | Goals the user stated but that aren't saved yet: `target_score`, `target_date`, `purpose`, `quote`, `session` |
| `procedural.preferences` | `[{"text", "sources"}]`, at most 10 |
| `episodic.sessions` | One per session: `session`, `started`, `ended`, `turns`, `logged_out`, `recorded_by`, `summary` |
| `changes` | What this dream added, merged, updated or removed, each with a reason |
| `rejected` | Model output the validator dropped, with the reason |

The model's output is validated before it is saved, and anything that breaks a rule goes to `rejected`:
- a fact or preference containing a ₹ amount, a percentage or a score (figures come from the tools);
- an item with no known source session;
- a goal candidate whose quote isn't the user's exact words, or whose fields fail §4.

**Merging teammates' work:** the newest dream is the current memory. If two teammates dreamt at the same time on different sessions, the newest dream may not cover the other's sessions. Those sessions then count as unconsolidated and go into the next dream. Episodes are never deleted, so nothing is lost.

## 6. Reading memory

`store.load(user_id)` returns a `UserMemory` with:
- `episodes`: every session, oldest first;
- `goal`: the current goal, or `None`;
- `goal_history`: every goal set, oldest first;
- `dream`: the newest dream, or `None`.

It reads only that user's folder and drops any event with another `user_id`. In the chat UI, the **Your memory and past conversations** panel shows the goal, the consolidated memory and the latest 5 earlier sessions, including who recorded each one.

## 7. Memory in answers (Task #17)

Every answer in the chat UI uses memory (`creditcoach/memory/recall.py`):

- **MEMORY context.** Before each question, the model reads a MEMORY section. It holds today's date, the stored goal (with the user's words and when they said it), earlier goals, goal candidates newer than the stored goal, consolidated facts and preferences, and where the last conversation left off. That is the dream's summary, or the last few messages if the session isn't consolidated yet. It is labelled as notes about the user, not instructions. It never holds credit figures.
- **This session's turns.** The last 8 chat messages of the current session go in before the question, so follow-ups such as "I only have 6 months now" have context.
- **Unprompted recall.** The system prompt's "Using memory" section tells the model to connect plans and progress to the stored goal without being asked, to read the goal back exactly when asked, and never to present it as a promise.
- **Saving goals: `save_goal` and `clear_goal`.** These tools run in the agent loop for the open session, not on the MCP server, because they write that session's memory. Each call needs a `quote`, and the host accepts it only if it is in something the user typed this session or in an unconfirmed goal candidate, so the model can't save words the user never said (`QUOTE_NOT_FROM_USER`). A goal that fails validation (a score outside 300–900, a date not written as `YYYY-MM` or `YYYY`, a purpose over 200 characters, or no field at all) is refused with `INVALID_GOAL` and the reason, so the model can ask the user again. A partial update keeps the stored fields it doesn't name, so "change my target to 750" keeps the date and purpose. The result names the previous goal so the answer can say "720 → 750". A question such as "Should I aim for 800?" gets a discussion and a question back, not a save.

Evidence: [task-17-goal-recall.md](evidence/week-2/task-17-goal-recall.md), with two users' goals stated in session 1 and recalled, unprompted, in session 2.

## 8. Privacy

Every user is synthetic. Memory is no longer committed to the public repository; it is in the team's Neon database, which only people with `DATABASE_URL` can read. Keep that string out of git, chats and screenshots (`.env` is git-ignored). The files archive in `memory/` stays public. **Testers must still not type real personal information**: not their own name, phone, PAN, account numbers or real credit details. If something real is typed by mistake, the project owner removes it in the Neon SQL editor: `ALTER TABLE memory_events DISABLE TRIGGER memory_events_append_only;`, `DELETE` the rows for that `session`, then `ENABLE TRIGGER` again.

## 9. Open questions for team review

1. **Retention.** Episode files grow with every session. Proposal: keep everything during the 4-week build. Before the demo, decide whether to keep only the dreams for older sessions.
2. **Evaluation runs.** The Week 4 eval harness calls the pipeline directly, so it writes no memory. Should eval sessions also be recorded (with `source: "eval"`), or kept out of users' histories? Proposal: keep them out.
3. **Goal candidates.** *Decided in Task #17:* MEMORY lists candidates newer than the stored goal, and the model may ask "Shall I save that as your goal?". It saves only after the user confirms.
4. **Eval runs with memory.** The 50-query live run starts every query with empty memory, so the goal-memory queries (#3, #5, #23, #25, #35–#40) are still marked "partly deferred" there. Proposal: the Task #27 harness seeds each query's stored goal and earlier session (for example, #36 runs after #35) using a temporary memory folder, as `scripts/task17_goal_recall.py` does.

## 10. Sign-off

| Member | Reviewed | Date |
|---|---|---|
| Aman | [ ] | |
| Anil | [ ] | |
| Sudip | ✅ Reviewed and Signed Off | 2026-10-02 |
