"""The synthetic dataset (users, accounts, score history), read from ``data/*.csv`` or from Neon Postgres.

Two backends, chosen by ``config.DATA_BACKEND`` at call time (like memory's ``config.MEMORY_BACKEND``):

    files     ``data/users.csv``, ``data/accounts.csv``, ``data/score_history.csv``: the committed, reviewed copy
              that ``scripts/synthetic/`` writes. Tests always use it (``tests/conftest.py``).
    postgres  Three tables in the same Neon database as memory (``DATABASE_URL``): ``dataset_users``,
              ``dataset_accounts`` and ``dataset_score_history``, loaded from the CSVs by ``scripts/data_import.py``.

Neon is a copy of the CSVs, not a second source: to change the data, regenerate the CSVs and re-run the import.
The one exception is people who sign up in the app (``creditcoach.signup``): their rows exist only in Neon, after
the CSVs' rows, with ``source = 'Sign-up'``. The import keeps them and ``drift()`` leaves them out.
Postgres hands each table back as CSV (``COPY ... TO STDOUT``), parsed with the same ``read_csv`` options as the
files, so ``load()`` returns identical DataFrames from either backend and the tools can't tell them apart.
``drift()`` names the tables where Neon and the CSVs differ (used by ``creditcoach.check`` and the import).

Example:
    >>> from creditcoach import dataset
    >>> users, accounts, scores = dataset.load()
    >>> len(users), len(accounts), len(scores)
    (15, 28, 169)
"""

import io

import pandas as pd

from creditcoach import config

TABLES = ("users", "accounts", "score_history")
SIGNUP_SOURCE = "Sign-up"  # users.source for people who signed up in the app; their rows are in Neon only
READ_OPTIONS = {"users": {"dtype": str, "keep_default_na": False},
                "accounts": {},
                "score_history": {"dtype": {"date": str}}}

USER_COLUMNS = ["user_id", "first_name", "gender", "age", "age_band", "years_working", "credit_cards",
                "checks_score", "learns_from", "self_reported_score", "knowledge_score", "unexplained_drop",
                "pays_card", "card_usage", "knows_apr", "late_payments_12m", "loans", "risky_product_exposure",
                "invests_in", "emergency_fund", "emi_pct", "invest_pct", "goals_2yr", "source"]
ACCOUNT_COLUMNS = ["account_id", "user_id", "account_type", "balance_inr", "credit_limit_inr", "utilization_ratio"]
SCORE_COLUMNS = ["user_id", "date", "score", "primary_factor_change"]
COLUMNS = {"users": USER_COLUMNS, "accounts": ACCOUNT_COLUMNS, "score_history": SCORE_COLUMNS}

# ``pos`` keeps each CSV's row order. Users' answers are all text, as in the CSV, with blank as '' (never NULL).
SCHEMA = f"""
CREATE TABLE IF NOT EXISTS dataset_users (
    pos      bigint GENERATED ALWAYS AS IDENTITY,
    user_id  text PRIMARY KEY CHECK (user_id ~ '^USR-[0-9]{{3,4}}$'),
    {", ".join(f"{c} text NOT NULL DEFAULT ''" for c in USER_COLUMNS[1:])}
);
CREATE TABLE IF NOT EXISTS dataset_accounts (
    pos                bigint GENERATED ALWAYS AS IDENTITY,
    account_id         text PRIMARY KEY,
    user_id            text NOT NULL REFERENCES dataset_users (user_id),
    account_type       text NOT NULL,
    balance_inr        bigint NOT NULL,
    credit_limit_inr   bigint,
    utilization_ratio  double precision
);
CREATE TABLE IF NOT EXISTS dataset_score_history (
    pos                    bigint GENERATED ALWAYS AS IDENTITY,
    user_id                text NOT NULL REFERENCES dataset_users (user_id),
    date                   date NOT NULL,
    score                  integer NOT NULL CHECK (score BETWEEN 300 AND 900),
    primary_factor_change  text NOT NULL,
    PRIMARY KEY (user_id, date)
);
"""

# What COPY writes out, column for column in each CSV's order (dates as YYYY-MM-DD whatever the DateStyle).
SELECTS = {"users": ", ".join(USER_COLUMNS),
           "accounts": ", ".join(ACCOUNT_COLUMNS),
           "score_history": "user_id, to_char(date, 'YYYY-MM-DD') AS date, score, primary_factor_change"}


class DatasetError(Exception):
    """The dataset couldn't be read: a file is missing or unreadable, Neon is unreachable, or Neon is empty."""


def parse(table: str, source) -> pd.DataFrame:
    """Read one table's CSV (a path or a file-like object) with that table's ``READ_OPTIONS``."""
    return pd.read_csv(source, **READ_OPTIONS[table])


def latest_month(scores: pd.DataFrame) -> str:
    """The latest month in ``scores`` (``YYYY-MM-01``), or the dataset-wide one a per-user read kept in its attrs."""
    return scores.attrs.get("as_of") or str(scores.date.max())[:10]


def read_files(user_id: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Users, accounts and score history from ``config.DATA_DIR``; only ``user_id``'s rows when given.

    Raises:
        DatasetError: A file is missing, unreadable or malformed.
    """
    try:
        frames = tuple(parse(t, config.DATA_DIR / f"{t}.csv") for t in TABLES)
    except (OSError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise DatasetError(exc.__class__.__name__) from exc
    if user_id is None:
        return frames
    as_of = latest_month(frames[2])
    frames = tuple(f[f.user_id == user_id].reset_index(drop=True) for f in frames)
    frames[2].attrs["as_of"] = as_of
    return frames


def create_schema(conn) -> None:
    """Create the three tables if they don't exist yet (serialized, so two processes can start at once)."""
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(hashtext('creditcoach_dataset_schema'))")
        conn.execute(SCHEMA)


def read_postgres(user_id: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Users, accounts and score history from Neon, in CSV row order; only ``user_id``'s rows when given.

    A per-user read (each answer's tool server, 2026-11-21) keeps its cost flat as sign-ups grow toward 1,000, and
    keeps the dataset's latest month, "now" for the tools, in the score history's ``attrs["as_of"]``.

    One plain connection, without memory's pool or ``create_schema``: the import and sign-up create the tables. Each
    answer's tool server reads the dataset once, and in a load test of 100 questions on Railway (2026-11-21) 50
    servers at once queued on the pool's and the schema's locks, so a first tool call took over the 5 s limit.

    Raises:
        DatasetError: Neon is unreachable or not configured, or holds no users yet (run the import).
    """
    import psycopg  # imported only for this backend

    try:
        if not config.DATABASE_URL:
            raise RuntimeError("DATABASE_URL is not set")
        # prepare_threshold=None: Neon's pooled (PgBouncer) endpoint doesn't support prepared statements
        with psycopg.connect(config.DATABASE_URL, autocommit=True, prepare_threshold=None, connect_timeout=15) as conn:
            frames = []
            where, params = ("WHERE user_id = %s ", (user_id,)) if user_id else ("", None)
            for table in TABLES:
                buffer = io.BytesIO()
                with conn.cursor().copy(f"COPY (SELECT {SELECTS[table]} FROM dataset_{table} {where}ORDER BY pos) "
                                        "TO STDOUT WITH (FORMAT csv, HEADER)", params) as copy:
                    for chunk in copy:
                        buffer.write(chunk)
                buffer.seek(0)
                frames.append(parse(table, buffer))
            if user_id:
                latest = conn.execute("SELECT to_char(max(date), 'YYYY-MM-DD') FROM dataset_score_history").fetchone()
                frames[2].attrs["as_of"] = latest[0]
    except Exception as exc:  # psycopg, pool timeout, or DATABASE_URL missing: all mean "can't read it now"
        raise DatasetError(exc.__class__.__name__) from exc
    if frames[0].empty and not user_id:  # one user's read finds no rows when the user is unknown (UNKNOWN_USER)
        raise DatasetError("Neon has no dataset yet (run: uv run python scripts/data_import.py)")
    return tuple(frames)


def load(user_id: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Users, accounts and score history from the configured backend (``config.DATA_BACKEND``); only ``user_id``'s
    rows when given (``read_postgres``).

    Not cached here: the callers (``tools.common.tables``, ``user_data``) cache once per process.

    Raises:
        DatasetError: The backend couldn't be read (see ``read_files`` and ``read_postgres``).
        ValueError: ``config.DATA_BACKEND`` is neither "files" nor "postgres".
    """
    if config.DATA_BACKEND == "postgres":
        return read_postgres(user_id)
    if config.DATA_BACKEND == "files":
        return read_files(user_id)
    raise ValueError(f"unknown data backend {config.DATA_BACKEND!r} (use 'postgres' or 'files')")


def without_signups(frames: tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]) -> tuple:
    """``(users, accounts, scores)`` without the rows of people who signed up in the app."""
    users = frames[0]
    signed_up = set(users.user_id[users.source == SIGNUP_SOURCE])
    if not signed_up:
        return frames
    return tuple(f[~f.user_id.isin(signed_up)].reset_index(drop=True) for f in frames)


def drift() -> list[str]:
    """Tables whose Neon copy differs from the CSV in any row, column, value or order. Empty means in sync.

    Sign-up users are in Neon only, by design, so their rows are left out of the comparison.

    Raises:
        DatasetError: Either side couldn't be read.
    """
    return [t for t, f, p in zip(TABLES, read_files(), without_signups(read_postgres())) if not f.equals(p)]
