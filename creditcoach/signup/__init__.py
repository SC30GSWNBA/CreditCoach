"""Self-service sign-up: a new person answers the interview questions and gets a practice profile and a login.

    questions   The sign-up form: the interview questions (docs/research/interview-questionnaire.md) in the
                dataset's wording, which ones are required, and the privacy text shown above them.
    generate    Answers -> one users row, the accounts they reported, and a 12-month score history, under the same
                rules as ``scripts/synthetic/step2_accounts_scores.py``. Also the random 16-character password.
    store       Writes the new user to Neon (``dataset_users``, ``dataset_accounts``, ``dataset_score_history``) and
                the login to ``app_logins``, in one transaction.
    mailer      Optionally emails the new login to the person, once, without keeping the address.

The 15 original users, their logins in ``creditcoach/app/logins.json`` and ``data/*.csv`` are never changed by a
sign-up: new users exist only in Neon, marked ``source = 'Sign-up'``.
"""
