# CreditCoach memory

Each synthetic user's memory, recorded by the chat UI and shared through git. The schema and rules are in [docs/memory.md](../docs/memory.md).

```
USR-001/episodes/<session>.jsonl   one file per chat session: sign-in, every question and reply, goal changes, sign-out
USR-001/dreams/<timestamp>.json    consolidated memory (facts, preferences, session summaries); the newest is current
```

- **Never edit or rename these files.** They are append-only, which is why `git pull` never conflicts. A new session or dream always gets a new file.
- **Don't type real personal information in the chat.** Everything here becomes public once merged.
- **Share your sessions:** `uv run python scripts/memory_sync.py` commits only this folder on a new branch and opens a pull request. Once it merges, teammates who pull see your sessions in the app's "Your memory and past conversations" panel.
- **Consolidate by hand:** `uv run python -m creditcoach.memory.dream --all`. This normally runs in the background when a user signs in.
