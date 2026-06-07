"""
Critic agent: finds flaws, risks, and gaps in the requirements plan.
Runs in parallel with the brainstormer.

Two-step process:
  1. Derive domain-specific critique lenses from the requirements itself.
  2. Evaluate the plan through those lenses + the config baseline lenses.
"""

import json
import anthropic
from state import PipelineState
from config import PipelineConfig
from utils import warn_if_truncated

_client = anthropic.Anthropic()

_DERIVE_SYSTEM = """\
You are a product risk analyst. Given a requirements document, identify the most \
important critique lenses specific to this product's domain, users, and constraints.

Return a JSON array of 4-6 short lens names. Each lens should be a specific risk \
dimension that matters for THIS product — not generic advice.

Examples for a fintech app: ["regulatory compliance", "fraud vectors", "data breach impact"]
Examples for a logistics app: ["real-time data staleness", "offline resilience", "driver UX under load"]

Return ONLY a JSON array. No explanation.
"""

_EVALUATE_SYSTEM = """\
You are a critical product reviewer. Your job is to find problems — not praise.

Evaluate the requirements plan through each of these lenses:
{lenses}

For each issue found:
  [LENS] Issue title
         Problem: one sentence describing what's wrong or missing.
         Risk: what could go wrong if this isn't addressed.
         Suggestion: one concrete fix (keep it short).

If a lens has no issues, write "[LENS] No issues found."

Be honest and direct. Do not soften findings.
"""


def _derive_lenses(state: PipelineState, base_lenses: list[str], config: PipelineConfig) -> list[str]:
    response = _client.messages.create(
        model=config.model,
        max_tokens=config.tokens_critique_derive,
        system=_DERIVE_SYSTEM,
        messages=[{"role": "user", "content": state.context_for_agents()}],
    )
    try:
        derived = json.loads(response.content[0].text)
    except (json.JSONDecodeError, IndexError):
        derived = []

    # Merge: base lenses first (universal floor), then domain-specific additions
    seen = set(l.lower() for l in base_lenses)
    merged = list(base_lenses)
    for lens in derived:
        if lens.lower() not in seen:
            merged.append(lens)
            seen.add(lens.lower())
    return merged


def run(state: PipelineState, config: PipelineConfig) -> PipelineState:
    lenses = _derive_lenses(state, config.critic_lenses, config)
    lenses_str = "\n- ".join(lenses)
    system = _EVALUATE_SYSTEM.format(lenses=lenses_str)
    response = _client.messages.create(
        model=config.model,
        max_tokens=config.tokens_critique_evaluate,
        system=system,
        messages=[{"role": "user", "content": state.context_for_agents()}],
    )
    warn_if_truncated(response, "critique_evaluate")
    state.critique = response.content[0].text
    return state
