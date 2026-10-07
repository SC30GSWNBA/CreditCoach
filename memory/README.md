# CreditCoach memory (archive)

**Memory now lives in Neon Postgres** (set `DATABASE_URL` in `.env`). This folder is the archive of what was recorded before that move, and it has been imported into Neon. It is also where the files backend writes when `DATABASE_URL` isn't set. The schema and rules are in [docs/memory.md](../docs/memory.md).

To copy sessions recorded on your machine as files into Neon: `uv run python scripts/memory_import.py` (safe to re-run).

```
USR-001/episodes/<session>.jsonl   one file per chat session: sign-in, every question and reply, goal changes, sign-out
USR-001/dreams/<timestamp>.json    consolidated memory (facts, preferences, session summaries); the newest is current
```

- **Never edit or rename these files.** They are append-only, which is why `git pull` never conflicts. A new session or dream always gets a new file.
- **Don't type real personal information in the chat.** Everything here becomes public once merged.
- **Share your sessions (files backend only):** `uv run python scripts/memory_sync.py` commits only this folder on a new branch and opens a pull request. Once it merges, teammates who pull see your sessions in the app's "Your memory and past conversations" panel.
- **Consolidate by hand:** `uv run python -m creditcoach.memory.dream --all`. This normally runs in the background when a user signs in.
