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

        scores = pd.read_excel(config.SAMPLE_DATA, sheet_name="ScoreHistory")
        accounts = pd.read_excel(config.SAMPLE_DATA, sheet_name="Accounts")
        latest = scores.iloc[-1]
        report(True, "Sample data readable", f"{scores['user_id'].nunique()} user(s), {len(scores)} score rows, {len(accounts)} accounts; "
               f"latest {latest['user_id']} score {latest['score']} ({latest['primary_factor_change']})")
    except Exception as exc:
        report(False, "Sample data readable", str(exc))

    print("\nAll checks passed. Ready to build." if ok else "\nSome checks failed. See README > Troubleshooting.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
