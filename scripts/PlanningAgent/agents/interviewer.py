"""
Interviewer agent: generates specific, scenario-grounded questions and collects
answers from the user. Uncapped — keeps probing until every mandatory topic has
a concrete answer, with a periodic check-in so the user can cut it short.

Ends with an understanding checkpoint: a "here is my understanding" summary the
user must confirm or correct before the pipeline moves on to planning/research.
"""

import json
import anthropic
from state import PipelineState, QAPair
from config import PipelineConfig
from utils import create_json_with_retry

_client = anthropic.Anthropic()

_SYSTEM = """\
You are a requirements interviewer. Your job is to deeply understand what the user \
wants to build before any planning or research happens. Follow these rules strictly:

QUESTION STYLE — this is the most important rule set:
1. Ask ONE question at a time.
2. Before your first question, silently derive 3-5 question areas specific to THIS \
product's domain (e.g. for a fitness app: workout data sources, offline gym use, \
social pressure mechanics). Plan concrete questions for them.
3. Every question must be specific and scenario-grounded. BANNED: vague questions \
like "give me a brief about your app", "tell me more about your users", "what \
features do you want?". GOOD: "Walk me through what a user does in their first \
5 minutes after opening the app", "When a user misses a deadline, should the app \
notify them immediately, daily digest, or stay silent?".
4. Reference the user's previous answers in later questions — build on what you know.
5. Prefer multiple-choice or yes/no questions. Only ask open-ended when necessary.
6. DRILL DOWN: if an answer is generic or ambiguous (e.g. "everyone", "make it easy", \
"the usual features"), ask exactly ONE follow-up to make it concrete before moving on.
7. Never assume or speculate. Do not suggest features — only gather information.

MANDATORY TOPICS — a topic counts as covered only when it has a CONCRETE answer:
  (a) core users — who specifically is this for? (not "everyone")
  (b) core problem — what pain does it solve, and why do current solutions fail?
  (c) key constraints — platform, data source, team size, timeline, technical limits
  (d) business model — how does this make money, or is it intentionally free and why?
  (e) success criteria — what does "working" look like in 3 months? Measurable if possible.
  (f) core user journey — the primary workflow end-to-end, step by step
  (g) feature priorities — must-have vs nice-to-have vs explicitly-not
  (h) prior art reactions — tools the user has tried or seen; what they loved and hated

There is no question limit. Do NOT signal done to save questions — only when every \
topic above has a concrete, unambiguous answer.

Always respond with valid JSON in one of these shapes:
  {"question": "...", "options": ["A", "B", "C"]}   <- MCQ
  {"question": "...", "options": null}               <- free text
  {"done": true}                                     <- all eight topics concretely covered
"""

_SUMMARY_SYSTEM = """\
You are a requirements interviewer wrapping up an interview. Produce a structured \
"here is my understanding" summary of what the user wants to build, based ONLY on \
their actual answers — do not invent or embellish.

Format:
## My Understanding
- **Product:** one sentence
- **Core users:** ...
- **Core problem & why current solutions fail:** ...
- **Key constraints:** ...
- **Business model:** ...
- **Success criteria (3 months):** ...
- **Core user journey:** ...
- **Feature priorities:** must-have / nice-to-have / explicitly out
- **Prior art reactions:** what they loved/hated in existing tools

Mark anything still ambiguous with [UNCLEAR]. If the user has provided corrections \
to a previous summary, incorporate them exactly — do not reword approved content.

Output the summary as plain markdown. No JSON, no preamble.
"""


def _interview_history(state: PipelineState) -> list:
    history = []
    for qa in state.interview:
        history.append({"role": "assistant", "content": json.dumps(
            {"question": qa.question, "options": qa.options}
        )})
        history.append({"role": "user", "content": qa.answer})
    return history


def _ask_claude(state: PipelineState, config: PipelineConfig) -> dict:
    history = _interview_history(state)
    history.append({"role": "user", "content": (
        f"Domain: {state.domain}\n"
        f"App name: {state.app_name}\n"
        f"User goal: {state.goal}\n"
        f"Questions asked so far: {len(state.interview)}\n"
        "Generate the next question, or {\"done\": true} only if every mandatory "
        "topic has a concrete answer."
    )})

    # Retries on malformed JSON so one glitchy response doesn't kill the interview.
    return create_json_with_retry(
        _client,
        model=config.model_for("interviewer"),
        max_tokens=config.tokens_interview,
        system=_SYSTEM,
        messages=history,
    )


def _generate_summary(state: PipelineState, config: PipelineConfig,
                      corrections: list[str]) -> str:
    prompt_parts = [
        f"Domain: {state.domain}",
        f"App name: {state.app_name}",
        f"User goal: {state.goal}",
        "",
        "Interview transcript:",
        state.interview_summary(),
    ]
    if corrections:
        prompt_parts += ["", "User corrections to previous summary (apply all of these):"]
        prompt_parts += [f"- {c}" for c in corrections]

    response = _client.messages.create(
        model=config.model_for("interviewer"),
        max_tokens=config.tokens_interview_summary,
        system=_SUMMARY_SYSTEM,
        messages=[{"role": "user", "content": "\n".join(prompt_parts)}],
    )
    return response.content[0].text


def _display_question(idx: int, data: dict) -> str:
    print(f"\n[Question {idx}] {data['question']}")
    options = data.get("options")
    if options:
        for i, opt in enumerate(options, 1):
            print(f"  {i}. {opt}")
        while True:
            raw = input("Your answer (number or type): ").strip()
            if raw.isdigit() and 1 <= int(raw) <= len(options):
                return options[int(raw) - 1]
            # allow typing the option directly too
            if raw in options:
                return raw
            print(f"  Please enter a number 1–{len(options)} or the option text.")
    else:
        return input("Your answer: ").strip()


def _checkin(question_count: int) -> bool:
    """Periodic guardrail — returns True if the user wants to keep going."""
    print(f"\n[Interviewer] We're {question_count} questions in. I still have gaps to fill.")
    choice = input("Keep going for better accuracy, or proceed with what we have? (k = keep going / p = proceed): ").strip().lower()
    return choice != "p"


def _confirm_understanding(state: PipelineState, config: PipelineConfig) -> None:
    corrections: list[str] = []
    while True:
        summary = _generate_summary(state, config, corrections)
        print("\n" + "-" * 60)
        print(summary)
        print("-" * 60)
        raw = input(
            "\nIs this understanding correct? (y = yes / or type what's wrong): "
        ).strip()
        if raw.lower() in ("y", "yes", ""):
            state.understanding = summary
            return
        corrections.append(raw)
        print("\n[Interviewer] Got it — updating my understanding...")


def run(state: PipelineState, config: PipelineConfig) -> PipelineState:
    print("\n" + "=" * 60)
    print("PHASE 1 — INTERVIEW")
    print("=" * 60)

    if not state.app_name:
        state.app_name = input("\nWhat is the name of your app (or working title)?\n> ").strip()

    if not state.goal:
        state.goal = input(
            f"\nIn one sentence, what do you want to build? ({state.domain})\n> "
        ).strip()

    question_num = 0
    while True:
        if question_num > 0 and question_num % config.interview_checkin_every == 0:
            if not _checkin(question_num):
                print("[Interviewer] Proceeding — remaining gaps will be marked [UNCLEAR].")
                break

        data = _ask_claude(state, config)

        if data.get("done"):
            print("\n[Interviewer] I have enough information to proceed.")
            break

        question_num += 1
        answer = _display_question(question_num, data)
        state.interview.append(QAPair(
            question=data["question"],
            options=data.get("options"),
            answer=answer,
        ))

    if config.require_understanding_confirmation:
        _confirm_understanding(state, config)

    return state
