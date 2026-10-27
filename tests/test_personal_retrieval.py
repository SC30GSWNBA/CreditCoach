"""Task 30: data-aware retrieval searches the library for what the user's own data says the question is about.

Found by the Task 29 error analysis: #9, #11 and #27 missed the library's key fact because only the user's data, not
the question, named it. No API key needed: the probes are fixed rules, and the pipeline test stubs retrieval.

Run:
    uv run pytest tests/test_personal_retrieval.py -v
"""

import pytest

from creditcoach.evals import golden
from creditcoach.rag import personal
from creditcoach.user_data import load_user_data


def probes(qid: int) -> list[str]:
    q = golden.by_id()[qid]
    d = load_user_data(q.user_id)
    return personal.probes(q.query, d["get_score_history"]["points"], d["get_account_summary"]["accounts"])


@pytest.mark.parametrize("qid, expected", [
    (11, ["Late payment (30+ days)"]),               # "crash in April": the month's factor, "+" inside kept
    (9, ["Hard inquiry"]),                           # "dip the last two months": the last two falls
    (1, ["Hard inquiry", "utilization spike"]),      # one label, two factors
    (27, [personal.CARD_INTEREST]),                  # paying off a loan faster while a card carries a balance
])
def test_the_cases_that_missed_get_the_search_their_data_points_to(qid, expected):
    assert probes(qid) == expected


@pytest.mark.parametrize("qid, why", [
    (46, "January 2025 isn't January 2026"),
    (38, '"change my target" is not the score moving'),
    (41, '"pay my card down" is not the score moving'),
    (4, "payday-loan questions get the product-risk passages instead"),
    (26, "a home loan to apply for is not a loan to pay off"),
    (35, "December 2027 is a target, and stable months explain nothing"),
])
def test_questions_their_data_doesnt_explain_get_no_extra_search(qid, why):
    assert probes(qid) == [], why


def test_most_questions_retrieve_exactly_as_before():
    assert sum(bool(probes(q.id)) for q in golden.load()) == 9  # of 50


def test_may_is_a_month_only_when_it_reads_as_one():
    assert personal.named_months("What was my score in May?") == {(5, None)}
    assert personal.named_months("May I ask about May 2026?") == {(5, 2026)}
    assert personal.named_months("May I see my score?") == set()


def test_the_pipeline_adds_one_new_passage_per_probe(monkeypatch):
    from creditcoach.agent import pipeline
    from creditcoach.rag.retrieve import Result

    def result(id_):
        return Result(rank=1, id=id_, score=0.5, title=id_, category="scoring_factor", text="t", metadata={})
    searched = []

    def fake_retrieve(query, k=3, where=None):
        searched.append(query)
        return {"Late payment (30+ days)": [result("why-scores-drop#00"), result("factor-payment-history#00")]}.get(
            query, [result("why-scores-drop#00"), result("why-scores-drop#01"), result("score-impact-reference#02")])
    monkeypatch.setattr(pipeline, "retrieve", fake_retrieve)
    passages, probes_ = pipeline.gather_passages(golden.by_id()[11].query, 3, "USR-009", product=False)
    assert probes_ == ["Late payment (30+ days)"] and searched[-1] == "Late payment (30+ days)"
    # why-scores-drop#00 is already in the list, so the probe's first new passage is the one added
    assert [p.id for p in passages] == ["why-scores-drop#00", "why-scores-drop#01", "score-impact-reference#02",
                                        "factor-payment-history#00"]
    assert pipeline.gather_passages("Why did it drop?", 3, None, product=False)[1] == []  # no user, no data searches
