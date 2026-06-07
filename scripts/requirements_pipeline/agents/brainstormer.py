"""
Brainstormer agent: suggests better or missing features the user may not have considered.
Runs in parallel with the critic.
"""

import anthropic
from state import PipelineState
from config import PipelineConfig
from utils import warn_if_truncated

_client = anthropic.Anthropic()

_SYSTEM = """\
You are a creative product strategist. Given a requirements draft, suggest \
improvements and features the team may not have considered.

Rules:
- Suggest exactly {count} ideas.
- Each idea must be genuinely useful, not just nice-to-have padding.
- For each idea: name it, explain the user value in one sentence, note any tradeoff.
- Do NOT repeat features already in the plan.
- Do NOT suggest features that contradict stated constraints.

Format each suggestion as:
  [N] Feature Name
      Value: ...
      Tradeoff: ...
"""


def run(state: PipelineState, config: PipelineConfig) -> PipelineState:
    system = _SYSTEM.format(count=config.brainstorm_count)
    response = _client.messages.create(
        model=config.model,
        max_tokens=config.tokens_brainstorm,
        system=system,
        messages=[{"role": "user", "content": state.context_for_agents()}],
    )
    warn_if_truncated(response, "brainstorm")
    state.brainstorm = response.content[0].text
    return state
