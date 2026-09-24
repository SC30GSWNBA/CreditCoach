"""Setup check: confirms a fresh clone is ready to run. Usage: uv run python -m creditcoach.check"""

import importlib
import sys

from creditcoach import config

REQUIRED_PACKAGES = ["openai", "dotenv", "pandas", "openpyxl", "chromadb", "sentence_transformers", "gradio"]


def main() -> int:
    ok = True

    def report(passed: bool, label: str, detail: str = "") -> None:
        nonlocal ok
        ok = ok and passed
        print(f"[{'PASS' if passed else 'FAIL'}] {label}{f' - {detail}' if detail else ''}")

    version = sys.version_info
    report(version >= (3, 11), "Python >= 3.11", f"{version.major}.{version.minor}.{version.micro}")

    for name in REQUIRED_PACKAGES:
        try:
            importlib.import_module(name)
            report(True, f"import {name}")
        except ImportError as exc:
            report(False, f"import {name}", str(exc))

    key = config.OPENROUTER_API_KEY
    key_set = bool(key) and not key.startswith("sk-or-your-key")
    report(key_set, "OPENROUTER_API_KEY set in .env", f"{key[:8]}..." if key_set else "copy .env.example to .env and add your key")
    print(f"       models: chat={config.CHAT_MODEL} small={config.SMALL_MODEL} fallback={config.FALLBACK_MODEL}")

    try:
        import pandas as pd

        users = pd.read_csv(config.DATA_DIR / "users.csv", dtype=str, keep_default_na=False)
        accounts = pd.read_csv(config.DATA_DIR / "accounts.csv")
        scores = pd.read_csv(config.DATA_DIR / "score_history.csv")
        consistent = set(accounts.user_id) | set(scores.user_id) <= set(users.user_id) and scores.score.between(300, 900).all()
        latest = scores[scores.user_id == "USR-001"].iloc[-1]
        report(consistent, "Dataset readable (data/)", f"{len(users)} users, {len(accounts)} accounts, {len(scores)} score rows; "
               f"USR-001 latest score {latest['score']} ({latest['primary_factor_change']})")
    except Exception as exc:
        report(False, "Dataset readable (data/)", str(exc))

    try:  # informational: the vector store is built by a separate step, so a missing store is not a failure
        import chromadb

        client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
        count = client.get_collection(config.CORPUS_COLLECTION).count()
        print(f"[INFO] Vector store built - {count} chunks in '{config.CORPUS_COLLECTION}'")
    except Exception:
        print("[INFO] Vector store not built yet - run: uv run python -m creditcoach.rag.ingest")

    print("\nAll checks passed. Ready to build." if ok else "\nSome checks failed. See README > Troubleshooting.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
