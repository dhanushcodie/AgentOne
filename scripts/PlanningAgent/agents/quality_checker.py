"""
Quality Checker agent: post-synthesis audit of the final requirements plan.

Two audit phases:
  Phase 1 — Deterministic checks (no web search): completeness and internal consistency.
  Phase 2 — Targeted verification (web search, 3 max): factual correctness of key claims.

Returns (passed: bool, summary: str, failures: list[dict]).

Failure dict shape:
  {
    "type": "completeness" | "consistency" | "factual" | "coverage_gap",
    "description": str,       # what specifically is wrong
    "fix": "synthesis" | "reresearch",  # which corrective path to take
    "targeted_queries": list[str]       # only populated for reresearch failures
  }

Pipeline behaviour on failure:
  - "synthesis" failures  -> synthesizer corrective pass (sees qc_report in context)
  - "reresearch" failures -> market_researcher.run_targeted() then re-synthesize
  If still failing after max_qc_iterations, failures are surfaced to the user verbatim.
"""

import json
import anthropic
from state import PipelineState
from config import PipelineConfig
from utils import run_search_loop, strip_json_fences

_client = anthropic.Anthropic()

_SYSTEM = """\
You are a quality auditor for product requirements plans. Find failures — not praise.

You receive the final plan, market research, and critique that produced it.

EVIDENCE-HONESTY RULE — applies to every check below:
An explicit, reasoned "not found in public sources" statement PASSES the
corresponding check. Stretched, fabricated, or adjacent-market evidence presented
as a finding FAILS it. Do not punish honest absence; punish false precision.

PHASE 1 — DETERMINISTIC CHECKS (run without web search first):

Completeness — mark PASS or FAIL:
  C1. At least 2 competitors named with URLs in the plan.
  C2. Monetisation Direction cites a specific comparable product with a revenue figure —
      or explicitly states that no same-market comparable with public revenue data was
      found, naming the closest signal available with a clear caveat. An adjacent-market
      figure presented WITHOUT that caveat is a FAIL.
  C3. Every [UNCLEAR] from the requirements draft is resolved or in Open Questions.
  C4. Market Opportunity section exists and is not a placeholder.
  C5. Competitive Differentiation names specific products (not vague "existing tools").
  C6. Every user-selected feature (from the "User-Selected Features" list in context)
      appears in the plan's Core Features (or an explicitly labelled post-MVP section).
      Skip if no user-selected features are listed.
  C7. The market research's Standout / Hook Features are backed by cited sources
      (reviews, Product Hunt, Reddit) — not just asserted. A shorter list with an
      explicit "little public praise found in this domain" note PASSES; padded
      entries with stretched evidence FAIL. Skip if section absent.

Consistency — mark PASS or FAIL:
  K1. Core features logically address the problem statement.
  K2. Out of Scope items are not contradicted by Core Features.
  K3. The monetisation comparable is in the SAME market as the product being planned.
      (e.g. citing NomadList for a visa lookup tool = FAIL — different market)
  K4. Competitive Differentiation claims are consistent with the competitor descriptions.
  K5. The problem statement is grounded in real evidence (not just assumed pain points).
  K6. The plan does not contradict the Confirmed Understanding summary — success
      criteria, feature priorities, and user corrections are respected, and no
      user-rejected feature appears in Core Features.

PHASE 2 — TARGETED VERIFICATION (use web search only for failed items):

For each FAIL that requires factual verification, run ONE targeted web search:
  - Named competitors: do they exist and do what the plan claims?
  - Revenue figures: can they be verified from a public source?
  - Monetisation comparable: is it actually in the same market?
  - Coverage gaps: are there major competitors the market research missed?

Maximum 3 web searches. Only search for items that actually failed Phase 1.

OUTPUT — respond with valid JSON only, no markdown fences:
{
  "passed": true | false,
  "summary": "one sentence overall verdict",
  "failures": [
    {
      "type": "completeness" | "consistency" | "factual" | "coverage_gap",
      "description": "specific description of what is wrong",
      "fix": "synthesis" | "reresearch",
      "targeted_queries": ["query 1", "query 2"]
    }
  ]
}

fix = "synthesis" for completeness and consistency failures the synthesizer can fix
      by revising the plan text.
fix = "reresearch" for factual errors or coverage gaps that require new web searches
      to get correct data before the plan can be fixed.

targeted_queries is populated only for "reresearch" failures — these queries will be
run by the market researcher to fill the gaps.

If all checks pass: {"passed": true, "summary": "...", "failures": []}
Be honest. Do not pass a plan that has real failures.
"""


def _run_agentic_loop(messages: list, max_searches: int, config: PipelineConfig) -> str:
    """web_search agentic loop with correct pause_turn continuation (see utils)."""
    return run_search_loop(
        _client,
        system=_SYSTEM,
        messages=messages,
        max_searches=max_searches,
        model=config.model_for("quality_checker"),
        max_tokens=config.tokens_quality_check,
        agent_name="quality_check",
    )


def _parse_result(raw: str) -> tuple[bool, str, list[dict]]:
    text = strip_json_fences(raw)
    try:
        result = json.loads(text)
        return (
            result.get("passed", False),
            result.get("summary", ""),
            result.get("failures", []),
        )
    except json.JSONDecodeError:
        return False, "QC output could not be parsed as JSON", [{
            "type": "completeness",
            "description": "QC agent did not return valid JSON",
            "fix": "synthesis",
            "targeted_queries": [],
        }]


def run(state: PipelineState, config: PipelineConfig) -> tuple[bool, str, list[dict]]:
    """
    Returns (passed, summary, failures).
    Also writes qc_report and qc_passed into state.
    """
    if not config.enable_quality_check:
        state.qc_passed = True
        return True, "QC disabled", []

    messages = [{"role": "user", "content": state.context_for_agents()}]
    raw = _run_agentic_loop(messages, config.qc_max_searches, config)

    passed, summary, failures = _parse_result(raw)
    state.qc_report = raw
    state.qc_passed = passed
    return passed, summary, failures
