"""The sign-up form's questions, in the wording ``data/users.csv`` uses for the same interview answers.

The questions are the interview questionnaire's (``docs/research/interview-questionnaire.md``), without Q23, which
the dataset doesn't hold. Ten are required: the ones that decide a person's accounts and score history
(``creditcoach.signup.generate``). The other fourteen are optional and only fill in the profile.

Each question is ``(column, kind, label, options, required)``. ``column`` is the ``users.csv`` column the answer
goes to, except ``q7`` to ``q12`` (the credit quiz), which together become ``knowledge_score``.
"""

RADIO, MULTI = "radio", "multi"

PRIVACY = """
### Your answers stay private

- **No name, phone number, PAN, bank login or email is needed.** You answer in ranges, never exact amounts.
- CreditCoach is a **financial-literacy project**. Your answers are used only to build a practice credit profile
  for you (sample accounts and a sample score history) so the coaching feels personal.
- We **never sell your answers or pass them** to lenders, banks, credit bureaus, employers or advertisers.
- To write an answer, your question and practice profile are processed by the AI model service CreditCoach runs
  on and kept in CreditCoach's own database. Nothing in them says who you are.
- The scores and balances you'll see are **synthetic**: they are generated from your answers and are not your real
  bureau data.
"""

NO_CARD_ANSWERS = {"pays_card": "Not applicable (no credit card)", "card_usage": "I don't know / not applicable"}

# (section title, open and required?, questions)
SECTIONS = [
    ("About you", True, [
        ("age_band", RADIO, "Which age group are you in?", ["21 to 25", "26 to 30", "31 to 35", "Above 35"], True),
        ("years_working", RADIO, "How long have you been working full-time?",
         ["Less than 1 year", "1 to 3 years", "4 to 8 years", "More than 8 years"], True),
        ("credit_cards", RADIO, "How many credit cards do you currently have?", ["0", "1", "2 to 3", "4 or more"], True),
        ("self_reported_score", RADIO, "Which best describes your current credit score?",
         ["I don't know it", "Below average / poor", "Average / fair", "Good", "Excellent"], True),
    ]),
    ("Cards and loans", True, [
        ("pays_card", RADIO, "How do you usually pay your credit card bill?",
         ["The full amount, every month", "More than the minimum, but not the full amount",
          "Only the minimum amount due", "I sometimes miss or pay late", "Not applicable (no credit card)"], True),
        ("card_usage", RADIO, "In a typical month, how much of your total card limit do you use?",
         ["Less than 10%", "10 to 30%", "31 to 70%", "More than 70%", "I don't know / not applicable"], True),
        ("late_payments_12m", RADIO,
         "In the last 12 months, how many times have you paid a card bill or loan payment late?",
         ["Never", "Once", "2 or more times", "Prefer not to say"], True),
        ("loans", MULTI, "Which of these do you currently have? (select all that apply)",
         ["No loans", "Education / student loan", "Car loan", "Home loan", "Personal loan", "Buy-now-pay-later plan",
          "Payday loan or instant cash app loan"], True),
        ("risky_product_exposure", RADIO,
         "Have you ever considered a payday loan, an instant cash app loan, or a paid \"credit repair\" service?",
         ["Never considered one", "Considered it, but decided not to", "Yes, I've used one",
          "I'm not sure what these are"], True),
        ("goals_2yr", MULTI, "What is your biggest financial goal for the next 2 years?",
         ["Buying a car", "Buying or renting a home", "Paying off existing debt",
          "Higher education or a career break", "Wedding, travel, or another big expense",
          "No specific goal right now"], True),
    ]),
    ("Optional: how you follow your score", False, [
        ("checks_score", RADIO, "How often do you check your credit score?",
         ["Never", "Once a year or less", "Every few months", "Monthly or more often"], False),
        ("learns_from", MULTI, "Where do you mostly learn about credit scores?",
         ["Social media or YouTube", "My bank's or card issuer's app or website", "Friends, family, or colleagues",
          "Search engines and blogs", "I don't really look it up"], False),
        ("unexplained_drop", RADIO, "Have you ever seen your credit score drop and not known why?",
         ["Yes, and I never found out why", "Yes, but I figured out the reason",
          "No, it has never dropped as far as I know", "I've never checked closely enough to know"], False),
        ("knows_apr", RADIO, "Do you know the interest rate (APR) on your main credit card?",
         ["Yes, roughly", "No", "I didn't know credit cards charge interest on unpaid balances",
          "Not applicable (no credit card)"], False),
    ]),
    ("Optional: a 6-question credit quiz", False, [
        ("q7", RADIO, "Which of these has the biggest effect on most credit scores?",
         ["Your salary", "Paying bills on time", "How many bank accounts you have", "Your age", "I don't know"], False),
        ("q8", RADIO, "What does \"credit utilization\" mean?",
         ["How many credit cards you have", "The share of your credit card limit you're currently using",
          "How often you swipe your card", "Your total spending in a year", "I don't know"], False),
        ("q9", RADIO, "Above roughly what level of utilization do scores commonly start to drop?",
         ["Above 10%", "Above 30%", "Above 70%", "Only when the card is maxed out (100%)", "I don't know"], False),
        ("q10", RADIO, "What usually happens to your score when you apply for a new credit card or loan?",
         ["Nothing happens", "A small, temporary dip", "A large, permanent drop", "It goes up", "I don't know"], False),
        ("q11", RADIO, "What might happen if you close your oldest credit card?",
         ["Your score goes up because you have less credit", "Nothing, because closed cards don't count",
          "Your score may go down because your credit history looks shorter", "I don't know"], False),
        ("q12", RADIO, "A company offers to raise your credit score by 100 points within 30 days, for a fee paid "
                       "upfront. What is this most likely to be?",
         ["A good deal if you can afford the fee", "A standard service that most banks offer",
          "A red flag for a possible scam", "I don't know"], False),
    ]),
    ("Optional: saving and how you split your salary", False, [
        ("invests_in", MULTI, "Where do you currently invest or save? (select all that apply)",
         ["I don't invest or save regularly", "Savings account or fixed / term deposits",
          "Mutual funds or index funds (including monthly SIPs)", "Individual stocks",
          "Retirement or provident fund (beyond any mandatory employer deduction)",
          "Gold, property, or other assets", "Crypto"], False),
        ("emergency_fund", RADIO,
         "If your income stopped tomorrow, how many months of expenses could your savings cover?",
         ["Less than 1 month", "1 to 3 months", "4 to 6 months", "More than 6 months", "I'm not sure"], False),
        ("emi_pct", RADIO, "About what percentage of your take-home pay goes to loan repayments (EMIs)?",
         ["0%, no loans", "1 to 10%", "11 to 20%", "21 to 35%", "More than 35%"], False),
        ("invest_pct", RADIO, "About what percentage goes into investments and savings?",
         ["0%", "1 to 10%", "11 to 20%", "21 to 35%", "More than 35%"], False),
    ]),
]
FIELDS = [q for _, _, questions in SECTIONS for q in questions]
GENDERS = ["Male", "Female", "Prefer not to say"]


def clean(first_name, gender, values) -> dict:
    """The form's values as an answers dict, keeping only options the form offers.

    Someone with no credit card gets the two card questions answered "not applicable" for them. Anything that
    isn't one of a question's options (a hand-made request, not the form) is dropped, so it counts as unanswered.
    """
    answers = {"first_name": " ".join(str(first_name or "").split())[:30],
               "gender": gender if gender in GENDERS else ""}
    for (column, kind, _, options, _), value in zip(FIELDS, values):
        if kind == MULTI:
            answers[column] = [v for v in options if v in (value or [])]
        else:
            answers[column] = value if value in options else ""
    if answers["credit_cards"] == "0":
        answers.update({k: answers[k] or v for k, v in NO_CARD_ANSWERS.items()})
    return answers


def missing(answers: dict) -> list[str]:
    """The labels of the required questions that have no answer yet. Empty means the form can be submitted."""
    return [label for column, _, label, _, required in FIELDS if required and not answers.get(column)]
