"""
Planner agent: converts interview transcript into a structured requirements doc.
"""

import anthropic
from state import PipelineState
from config import PipelineConfig
from utils import warn_if_truncated

_client = anthropic.Anthropic()

_SYSTEM = """\
You are a product requirements planner. Given an interview transcript, produce a \
concise, structured requirements document with these sections:

## Problem Statement
One paragraph.

## Target Users
Bullet list.

## Core Features (MVP)
Numbered list. Each item: feature name + one-line description.

## Out of Scope (v1)
Bullet list of things explicitly excluded.

## Key Constraints
Bullet list (technical, regulatory, time, budget — only what was mentioned).

Be specific. Do not invent requirements not backed by the interview. \
If something is ambiguous, note it with [UNCLEAR].
"""


def run(state: PipelineState, config: PipelineConfig) -> PipelineState:
    print("\n" + "=" * 60)
    print("PHASE 2 — PLANNING")
    print("=" * 60)
    print("Generating requirements from your answers...")

    prompt = state.context_for_agents()
    if state.user_feedback:
        prompt += f"\n\nUser feedback on previous plan:\n{state.user_feedback}\nRevise accordingly."

    response = _client.messages.create(
        model=config.model_for("planner"),
        max_tokens=config.tokens_plan,
        system=_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    warn_if_truncated(response, "plan")
    state.requirements = response.content[0].text
    return state
