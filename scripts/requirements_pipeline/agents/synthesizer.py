"""
Synthesizer agent: merges planner output, market research, brainstorm suggestions,
and critique into a final plan presented to the user for confirmation.
"""

import anthropic
from state import PipelineState
from config import PipelineConfig
from utils import warn_if_truncated

_client = anthropic.Anthropic()

_SYSTEM = """\
You are a product lead synthesizing inputs from four sources:
1. A requirements plan
2. Market research (competitor landscape, gaps, user pain points, monetisation)
3. Brainstorm suggestions (optional improvements)
4. A critique (flaws and risks)

Produce a final, clean requirements document with these sections in order:

## Final Requirements Plan

### Problem Statement
### Target Users
### Market Opportunity
From market research: gap, named competitors, demand signal.
If market research found no real gap, say so directly — do not hide negative findings.

### Competitive Differentiation
What this product does that confirmed competitors do not.
Name the competitors specifically. Do not use vague language like "existing tools."

### Core Features (MVP)
Include brainstorm ideas worth keeping. Flag which features address market gaps.

### Out of Scope (v1)
### Key Constraints

### Monetisation Direction
1-2 sentences grounded in what actually works in this market.
Cite comparable products and their revenue models.
Do not reference analogies from adjacent markets.

### Open Questions
Anything still [UNCLEAR] or flagged by critique as unresolved.

### Risks to Watch
Top 2-3 from critique.

---

Guidelines:
- Market Opportunity, Competitive Differentiation, and Monetisation Direction are mandatory — never omit.
- Incorporate brainstorm ideas only if they clearly add user value and fit scope.
- For each critique finding: fix it in the plan, add it to Risks, or add it to Open Questions.
- Do not pad. Keep tone direct and decision-ready.
- If a section has nothing meaningful, write one sentence explaining why rather than omitting.

SELF-AUDIT — before outputting, verify all three:
  (1) At least 2 specific competitors are named with URLs or descriptions.
  (2) Monetisation Direction cites a real comparable product with a data point.
  (3) Every [UNCLEAR] from the requirements draft is resolved or in Open Questions.
Fix any failures before outputting. A plan that fails this audit is not done.

CORRECTIVE PASS — if a Quality Check Report is present in the context:
  Read each failure in the report and fix it in your output.
  Do not reproduce failures the QC agent flagged. Address them specifically.
"""


def run(state: PipelineState, config: PipelineConfig) -> PipelineState:
    response = _client.messages.create(
        model=config.model,
        max_tokens=config.tokens_synthesize,
        system=_SYSTEM,
        messages=[{"role": "user", "content": state.context_for_agents()}],
    )
    warn_if_truncated(response, "synthesize")
    state.final_plan = response.content[0].text
    return state
