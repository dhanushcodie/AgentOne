"""
Interviewer agent: generates structured questions, collects answers from user.
Uses MCQ / yes-no format to minimise speculation. Stops when enough info is gathered.
"""

import json
import anthropic
from state import PipelineState, QAPair
from config import PipelineConfig

_client = anthropic.Anthropic()

_SYSTEM = """\
You are a requirements interviewer. Your job is to gather just enough information \
to define a clear product scope — no more. Follow these rules strictly:

1. Ask ONE question at a time.
2. Prefer multiple-choice or yes/no questions. Only ask open-ended when necessary.
3. Never assume or speculate. If something is unclear, ask.
4. Do not suggest features — only gather information.
5. You MUST cover all four topics before signalling done:
   (a) core users — who is this for?
   (b) core problem — what pain does it solve?
   (c) key constraints — platform, data source, team size, timeline
   (d) business model — how will this make money, or is it intentionally free?
   Do NOT output {"done": true} until all four topics have been addressed.

Always respond with valid JSON in one of these two shapes:
  {"question": "...", "options": ["A", "B", "C"]}   <- MCQ
  {"question": "...", "options": null}               <- free text
  {"done": true}                                     <- all four topics covered
"""


def _ask_claude(state: PipelineState, max_rounds: int, config: PipelineConfig) -> dict:
    history = []
    for qa in state.interview:
        history.append({"role": "assistant", "content": json.dumps(
            {"question": qa.question, "options": qa.options}
        )})
        history.append({"role": "user", "content": qa.answer})

    history.append({"role": "user", "content": (
        f"Domain: {state.domain}\n"
        f"User goal: {state.goal}\n"
        f"Questions asked so far: {len(state.interview)} / {max_rounds}\n"
        "Generate the next question, or {\"done\": true} if you have enough."
    )})

    response = _client.messages.create(
        model=config.model,
        max_tokens=config.tokens_interview,
        system=_SYSTEM,
        messages=history,
    )
    return json.loads(response.content[0].text)


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

    for round_num in range(1, config.max_interview_rounds + 1):
        data = _ask_claude(state, config.max_interview_rounds, config)

        if data.get("done"):
            print("\n[Interviewer] I have enough information to proceed.")
            break

        answer = _display_question(round_num, data)
        state.interview.append(QAPair(
            question=data["question"],
            options=data.get("options"),
            answer=answer,
        ))

    return state
