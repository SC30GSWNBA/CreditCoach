# Task 11 Follow-up: Per-User Logins and Data Isolation

*2026-09-30 · Code: `creditcoach/auth.py`, `creditcoach/user_data.py`, `creditcoach/app/main.py` · Script: `uv run python scripts/task11_login_isolation.py`*

**What changed:** every visitor signs in as one of the 15 dataset users (`creditcoach_user1` → USR-001 … `creditcoach_user15` → USR-015), and answers use that user's own profile, score history and accounts from `data/`. Passwords are stored only as salted PBKDF2-SHA256 hashes in `creditcoach/app/logins.json`, so every clone can check logins but no password is in git.

**How one user is kept out of another's data:**
1. The user id comes only from the signed-in Gradio session (`request.username` → `auth.user_id_for`), never from the message text.
2. `user_data.load_user_data` filters all three CSVs by that id and checks every row again before returning it, so another user's rows never reach the model.
3. The system prompt's rule 6 tells the model it has only the signed-in user's data and to decline requests about anyone else or to switch users.
4. Each question is answered on its own, and nothing is shared between sessions.

**Result: ✅ PASS** (offline checks; live checks not run)

## 1. Logins

| Check | Result | Detail |
|---|---|---|
| One login per dataset user | ✅ | 15 logins, 15 distinct users, 15 in data/ |
| creditcoach_userN signs in as USR-00N | ✅ | all 15 |
| No plain-text password in logins.json | ✅ | only salt + PBKDF2-SHA256 hash per login |
| Empty, wrong and unknown logins refused | ✅ | 31 attempts, all refused |

## 2. Each user's TOOL RESULTS hold only their own data

Built with `pipeline.build_context`, exactly as sent to the model. *Other users' data found* searches for every other user's id, account ids, first name and balance/limit amounts.

| User | Accounts | Score months | Other users' data found | Result |
|---|---|---|---|---|
| USR-001 | 5 | 12 | none | ✅ |
| USR-002 | 2 | 12 | none | ✅ |
| USR-003 | 2 | 12 | none | ✅ |
| USR-004 | 0 | 0 | none | ✅ |
| USR-005 | 1 | 12 | none | ✅ |
| USR-006 | 2 | 12 | none | ✅ |
| USR-007 | 0 | 0 | none | ✅ |
| USR-008 | 1 | 12 | none | ✅ |
| USR-009 | 2 | 12 | none | ✅ |
| USR-010 | 2 | 12 | none | ✅ |
| USR-011 | 2 | 12 | none | ✅ |
| USR-012 | 4 | 12 | none | ✅ |
| USR-013 | 2 | 12 | none | ✅ |
| USR-014 | 2 | 12 | none | ✅ |
| USR-015 | 1 | 12 | none | ✅ |

USR-004 and USR-007 have no credit file, so their TOOL RESULTS say so and the model is told not to state or estimate a score.

## 3. The session, not the message, decides the user

| Check | Result | Detail |
|---|---|---|
| Signed-in user decides whose data is used | ✅ | creditcoach_user1 -> ['USR-001'] |
| Message claiming another user is ignored | ✅ | still ['USR-001'] |
| Unknown or missing session gets no data | ✅ | pipeline calls: 2; reply: 'Please sign in again to continue.' |
