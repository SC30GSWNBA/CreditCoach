"""Files backend only. Share chat memory through GitHub: push your new sessions as a pull request, and pull everyone else's.

``main`` is protected, so memory reaches GitHub like any other change (docs/memory.md §2).

    push (default)  Commits every new file under ``memory/`` on a new branch ``memory/<date>-<you>-<hex>`` made from
                    ``origin/main`` in a temporary git worktree, pushes it, and opens a pull request with ``gh``. Your
                    own folder isn't touched: no branch switch, and your current work stays as it is. Only
                    ``memory/`` is committed.
    pull            ``git pull`` that won't fail on your own sessions. After your memory PR merges, ``main`` contains
                    files that also sit untracked in your folder, and git refuses to overwrite untracked files even
                    when they're identical. This removes each untracked memory file that is byte-identical to the
                    one on ``origin/main``, then runs ``git pull --ff-only``. A file that differs is never removed.

Run:
    uv run python scripts/memory_sync.py              # share your new sessions (opens a PR)
    uv run python scripts/memory_sync.py --dry-run    # list what would be shared
    uv run python scripts/memory_sync.py pull         # get everyone's merged sessions

Episode files can contain anything typed in the chat. Read them before sharing: nothing real should be in them.
"""

import argparse
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

from creditcoach import config

ROOT = config.ROOT
MEMORY = "memory"


def git(*args: str, cwd: Path | None = None, check: bool = True) -> str:
    """Run git (in the repo root unless ``cwd`` is given) and return its stdout, stripped."""
    result = subprocess.run(["git", *args], cwd=cwd or ROOT, capture_output=True, text=True)
    if check and result.returncode:
        sys.exit(f"git {' '.join(args)} failed:\n{result.stderr.strip()}")
    return result.stdout.strip()


def new_files() -> list[str]:
    """Untracked files under memory/ (new sessions and dreams), relative to the repo root."""
    out = git("ls-files", "--others", "--exclude-standard", "--", MEMORY)
    return [f for f in out.splitlines() if f]


def push(dry_run: bool) -> None:
    """Commit new memory files on a fresh branch from origin/main, push it, and open a pull request."""
    files = new_files()
    if not files:
        print("No new memory to share.")
        return
    users = sorted({f.split("/")[1] for f in files if f.count("/") >= 2})
    print(f"{len(files)} new memory file(s) for {', '.join(users) or 'memory/'}:")
    print("\n".join(f"  {f}" for f in files))
    if dry_run:
        return
    git("fetch", "-q", "origin", "main")
    who = re.sub(r"[^a-z0-9]+", "-", (git("config", "user.name", check=False) or "someone").lower()).strip("-")
    branch = f"memory/{date.today().isoformat()}-{who}-{secrets.token_hex(2)}"
    tmp = Path(tempfile.mkdtemp(prefix="creditcoach-memory-"))
    worktree = tmp / "repo"
    try:
        git("worktree", "add", "-q", "-b", branch, str(worktree), "origin/main")
        for f in files:
            (worktree / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / f, worktree / f)
        git("add", "--", MEMORY, cwd=worktree)
        sessions = sum(f.endswith(".jsonl") for f in files)
        dreams = sum(f.endswith(".json") for f in files)
        title = f"Memory: {sessions} session(s), {dreams} dream(s) for {', '.join(users)}"
        git("commit", "-q", "-m", title, cwd=worktree)
        git("push", "-q", "-u", "origin", branch, cwd=worktree)
        body = (f"Chat memory recorded on {git('config', 'user.name', check=False) or 'a teammate'}'s machine "
                f"({sessions} episode file(s), {dreams} dream file(s)). Adds files under `memory/` only; no file is "
                "changed or removed. Schema: docs/memory.md.\n\nAfter merging, pull with "
                "`uv run python scripts/memory_sync.py pull`.")
        url = subprocess.run(["gh", "pr", "create", "--base", "main", "--head", branch, "--title", title,
                              "--body", body], cwd=worktree, capture_output=True, text=True)
        print(url.stdout.strip() or f"Pushed {branch}; open the PR on GitHub ({url.stderr.strip()}).")
    finally:
        git("worktree", "remove", "--force", str(worktree), check=False)
        git("branch", "-D", branch, check=False)  # the branch lives on GitHub; no local copy needed
        shutil.rmtree(tmp, ignore_errors=True)


def pull() -> None:
    """Remove untracked memory files identical to origin/main's, then fast-forward."""
    git("fetch", "-q", "origin")
    upstream = git("rev-parse", "--abbrev-ref", "@{upstream}", check=False) or "origin/main"
    incoming = set(git("ls-tree", "-r", "--name-only", upstream, "--", MEMORY).splitlines())
    removed = kept = 0
    for f in new_files():
        if f not in incoming:
            continue
        theirs = subprocess.run(["git", "show", f"{upstream}:{f}"], cwd=ROOT, capture_output=True).stdout
        if (ROOT / f).read_bytes() == theirs:
            (ROOT / f).unlink()
            removed += 1
        else:
            kept += 1
            print(f"Kept {f}: it differs from {upstream}. Move it aside, then pull again.")
    print(f"Removed {removed} local file(s) already on {upstream}.")
    if kept:
        sys.exit(1)
    print(git("pull", "--ff-only") or "Up to date.")


def main() -> None:
    if config.MEMORY_BACKEND == "postgres":
        sys.exit("Memory is in Neon Postgres (DATABASE_URL is set), so there is nothing to share through git.\n"
                 "To copy file sessions into Neon: uv run python scripts/memory_import.py")
    parser = argparse.ArgumentParser(description="Share chat memory through GitHub.")
    parser.add_argument("command", nargs="?", choices=["push", "pull"], default="push")
    parser.add_argument("--dry-run", action="store_true", help="push: only list the files that would be shared")
    args = parser.parse_args()
    pull() if args.command == "pull" else push(args.dry_run)


if __name__ == "__main__":
    main()
