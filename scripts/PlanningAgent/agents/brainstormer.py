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

Suggest TWO kinds of ideas:

PART 1 — {count} MARKET-GROUNDED ideas:
- Ground every idea in evidence from the market research: a confirmed market gap, \
a real user complaint, or an adaptation of a competitor hook feature. Cite which.
- Do NOT simply restate hook features already listed in the market research's \
"Standout / Hook Features" section — those are presented to the user separately. \
Your ideas must be additive: novel combinations, adaptations, or gap-fillers.

PART 2 — up to {original_count} ORIGINAL ideas:
- Your own inventions — features no competitor has and the research doesn't point to, \
but that you genuinely believe would delight or hook THIS product's users.
- Quality bar is higher: only include an original idea if you would fight for it. \
Fewer (or zero) is fine; padding is not.
- Since there is no market evidence, the Grounding line must instead give your \
reasoning: why this fits this specific user, problem, and journey.

Rules for ALL ideas:
- Each idea must be genuinely useful, not just nice-to-have padding.
- For each idea: name it, explain the user value in one sentence, note any tradeoff.
- Do NOT repeat features already in the plan.
- Do NOT suggest features that contradict stated constraints.

Format each suggestion as:
  [N] Feature Name
      Value: ...
      Grounding: which gap / complaint / competitor feature this builds on
                 — or "ORIGINAL: <why this fits this user and problem>"
      Tradeoff: ...
"""


def run(state: PipelineState, config: PipelineConfig) -> PipelineState:
    system = _SYSTEM.format(count=config.brainstorm_count,
                            original_count=config.brainstorm_original_count)
    response = _client.messages.create(
        model=config.model_for("brainstormer"),
        max_tokens=config.tokens_brainstorm,
        system=system,
        messages=[{"role": "user", "content": state.context_for_agents()}],
    )
    warn_if_truncated(response, "brainstorm")
    state.brainstorm = response.content[0].text
    return state
