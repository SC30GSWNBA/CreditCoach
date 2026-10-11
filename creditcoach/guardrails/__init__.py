"""CreditCoach's guardrail layer (Task 20): every question and every answer passes through it.

The rules are in ``docs/guardrails.md``. The layer is built with NVIDIA NeMo Guardrails:

    ``config/config.yml``  Which rails run on the question (input) and on the draft answer (output).
    ``config/rails.co``    The Colang flows: one per rail, each executing one check.
    ``checks.py``          The checks: fixed patterns and number tracing, plus one small-model wording review.
    ``rails.py``           The engine, the checks registered as NeMo actions, and the pass / reframe / block decision.

Example:
    >>> from creditcoach import guardrails
    >>> s = guardrails.screen(question)                       # input rails
    >>> text, decision = guardrails.review(draft, question=s.text, sources=sources, user_id=user_id, screen=s,
    ...                                    rewrite=rewrite)   # output rails
    >>> decision.action                                       # "passed", "reframed" or "blocked"
"""

from creditcoach.guardrails.checks import Finding
from creditcoach.guardrails.rails import Decision, Screen, mask, review, rewrite_instruction, screen

__all__ = ["Decision", "Finding", "Screen", "mask", "review", "rewrite_instruction", "screen"]
