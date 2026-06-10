"""
Brainstormer agent: suggests better or missing features the user may not have considered.
Runs in wave 2 (parallel with the critic), after market research — so every idea can be
grounded in a confirmed market gap, a real user complaint, or a competitor hook feature.
"""

import anthropic
from state import PipelineState
from config import PipelineConfig
from utils import warn_if_truncated

_client = anthropic.Anthropic()

_SYSTEM = """\
You are a creative product strategist. Given a requirements draft and market \
research, suggest improvements and features the team may not have considered.

Rules:
- Suggest exactly {count} ideas.
- Ground every idea in evidence from the market research: a confirmed market gap, \
a real user complaint, or an adaptation of a competitor hook feature. Cite which.
- Each idea must be genuinely useful, not just nice-to-have padding.
- For each idea: name it, explain the user value in one sentence, note any tradeoff.
- Do NOT repeat features already in the plan.
- Do NOT simply restate hook features already listed in the market research's \
"Standout / Hook Features" section — those are presented to the user separately. \
Your ideas must be additive: novel combinations, adaptations, or gap-fillers.
- Do NOT suggest features that contradict stated constraints.

Format each suggestion as:
  [N] Feature Name
      Value: ...
      Grounding: which gap / complaint / competitor feature this builds on
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
