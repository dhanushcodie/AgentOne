"""
Market Researcher agent: uses web search to build a grounded picture of the
competitive landscape, user pain points, market size, and monetisation models.

Runs in wave 1, in parallel with the planner; brainstormer and critic run afterwards
with this research in context. Skipped if config.enable_market_research is False
(useful for offline dev or cost control).

Two-phase design:
  Phase 1 — Collect: mandated search categories ensure no category is skipped.
  Phase 2 — Self-verify: agent reviews its own output for gaps before finalising.

run_targeted() is called by the QC loop to fill specific gaps identified post-synthesis.
"""

import anthropic
from state import PipelineState
from config import PipelineConfig
from utils import run_search_loop

_client = anthropic.Anthropic()

_COLLECT_SYSTEM = """\
You are a product market researcher. Use web search to build a real, grounded market
picture. Do not guess or rely on training data — search for current information.

EVIDENCE RULE — overrides every minimum and section requirement below:
Evidence quality outranks quota. If a domain genuinely lacks public chatter (niche
B2B, new categories), say "not found in public sources" for that item and move on.
A shorter honest report is worth more than a padded one — never stretch weak or
tangential evidence to hit a number, and never present inference as a finding.
Honest "not found" statements will PASS quality checks; stretched evidence will FAIL.

MANDATORY SEARCH CATEGORIES — you must run at least one search per category (aim for
two) before synthesising. Formulate queries based on the product domain in the context.

  Category 1: Direct competitors (broad landscape search)
  Category 2: Indie/solo competitors — search indiehackers.com and producthunt.com explicitly
  Category 3: User complaints — Reddit, App Store reviews, or Trustpilot
  Category 4: Pricing and monetisation of discovered competitors
  Category 5: Revenue or MRR data for any solo-built products found (to find the right comparable)
  Category 6: Standout/hook features — what users LOVE about each major competitor.
              Search App Store / Play Store reviews, Product Hunt launch comments, and
              Reddit praise threads for the specific features users rave about, the ones
              that drive retention and word-of-mouth.

After completing all six categories, produce your research report with these sections:

## Competitor Landscape
At least 3 competitors (aim for 5). For each: name, URL, what they do well, what they
are missing, pricing model, target user. Explicitly call out any indie/solo-built products
found — these are the most relevant revenue comparables.

## Standout / Hook Features
Aim for {hook_features_min}+ features (across competitors) that users demonstrably love,
each with: feature name, which competitor, why users love it (quote or paraphrase real
praise with source), and whether/how it would transfer to this product. These are
candidates the user will be asked to adopt — evidence quality matters. If you cannot
find real praise for a feature, do not list it. If the domain has little public praise
to find, list fewer (or none) and say so explicitly — do not pad to hit the number.

## Market Gaps
Specific unserved or underserved problems. Not "better UX" — concrete missing features
or user segments.

## User Pain Points
Real complaints from real users. Quote or paraphrase with source. Do not invent pain
points — only report what you found.

## Market Size Signal
Any data on market size, user volume, or demand. Note confidence level. Say "not found"
if nothing was found — do not fabricate.

## Monetisation Models That Work
What competitors charge and what users pay for vs. expect free. Include price points.
Identify the closest comparable in the SAME market — not an analogy from adjacent markets.

## Verdict
2-3 sentences: real gap or not? Strongest single opportunity?
If the market is well-served, say so — do not suppress negative findings.

Be factual. Cite sources. Do not pad.
"""

_VERIFY_SYSTEM = """\
You are reviewing your own market research output for gaps and errors before it is
used to build a product plan. Be self-critical.

Check each item below. For any item that fails, run a targeted web search to fix it.

SELF-VERIFICATION CHECKLIST:
  1. Did I find at least one solo/indie-built competitor from Indie Hackers or Product Hunt?
     If no — search now.
  2. Can I verify the revenue figure I plan to cite with a direct source?
     If no — search for it, or mark it as unverified.
  3. Is my chosen monetisation comparable actually in the same market (not adjacent)?
     If not — search for a better one.
  4. Did I find real user complaints from Reddit or a review site (not assumed pain points)?
     If no — search now.
  5. Did I miss any major product category of competitor (e.g. API providers, B2B tools,
     government tools, app-store products)?
     If yes — search for it.
  6. Did I capture at least {hook_features_min} standout/hook features with cited evidence
     of real user praise (reviews, Product Hunt comments, Reddit)?
     If no — search now. Asserted-but-unevidenced hook features do not count.
     If the searches confirm the domain genuinely lacks public praise, keep the honest
     shorter list and state that explicitly — do NOT stretch weak evidence to hit the number.
  7. Is every claim in my report backed by something I actually found (not inferred,
     not generalised from an adjacent market)? Downgrade or remove anything stretched.

After any additional searches, output your COMPLETE, CORRECTED research report using
the same section headings as the original. Do not summarise — output the full report.
"""


def _search(system: str, messages: list, max_searches: int, config: PipelineConfig) -> str:
    """web_search agentic loop with correct pause_turn continuation (see utils)."""
    return run_search_loop(
        _client,
        system=system,
        messages=messages,
        max_searches=max_searches,
        model=config.model_for("market_researcher"),
        max_tokens=config.tokens_market_research,
        agent_name="market_research",
    )


def _build_prompt(state: PipelineState) -> str:
    parts = [
        f"Domain: {state.domain}",
        f"App: {state.app_name}" if state.app_name else "",
        f"Goal: {state.goal}" if state.goal else "",
        "",
        "Interview context:",
        state.interview_summary() if state.interview else "(no interview yet)",
    ]
    return "\n".join(p for p in parts if p is not None)


_REVISION_SYSTEM = """\
You are updating an existing market research report after the user revised the
product direction. Do NOT redo the research from scratch.

1. Read the existing report and the user's feedback.
2. Decide which findings are invalidated or missing under the new direction.
3. Run ONLY the targeted web searches needed to fill those gaps. If the feedback
   does not change the market picture (e.g. wording, scope trims), run no searches.
4. Output the COMPLETE updated report using the same section headings as the
   original — carry forward everything still valid verbatim, replace what changed.

Be factual. Cite sources. Do not pad.
"""


def run(state: PipelineState, config: PipelineConfig) -> PipelineState:
    if not config.enable_market_research:
        state.market_research = "(market research disabled in config)"
        return state

    # Revision loop: update the existing report with targeted searches instead
    # of re-burning the full research budget.
    if state.market_research and state.user_feedback:
        return _run_revision_update(state, config)

    # Phase 1: collect research across all mandatory categories
    # Most of the budget goes to collection; the rest to the self-verify pass
    collect_budget = max(1, round(config.market_research_max_searches
                                  * config.market_research_collect_ratio))
    verify_budget = max(1, config.market_research_max_searches - collect_budget)

    collect_system = _COLLECT_SYSTEM.format(hook_features_min=config.hook_features_min)
    collect_messages = [{"role": "user", "content": _build_prompt(state)}]
    collected = _search(collect_system, collect_messages, collect_budget, config)

    # Phase 2: self-verification pass
    verify_system = _VERIFY_SYSTEM.format(hook_features_min=config.hook_features_min)
    verify_messages = [{"role": "user", "content": (
        f"Here is the market research you collected:\n\n{collected}\n\n"
        "Now run the self-verification checklist and output the corrected, complete report."
    )}]
    verified = _search(verify_system, verify_messages, verify_budget, config)

    state.market_research = verified or collected
    return state


def _run_revision_update(state: PipelineState, config: PipelineConfig) -> PipelineState:
    print("  (revision: updating existing research with targeted searches only)")
    messages = [{"role": "user", "content": (
        f"{_build_prompt(state)}\n\n"
        f"User feedback driving this revision:\n{state.user_feedback}\n\n"
        f"Existing market research report:\n\n{state.market_research}"
    )}]
    updated = _search(_REVISION_SYSTEM, messages,
                      config.revision_research_max_searches, config)
    if updated:
        state.market_research = updated
    return state


def run_targeted(state: PipelineState, config: PipelineConfig, queries: list[str]) -> PipelineState:
    """
    Called by the QC loop to fill specific gaps identified after synthesis.
    Runs the given queries and appends new findings to state.market_research.
    """
    if not queries or not config.enable_market_research:
        return state

    query_list = "\n".join(f"  - {q}" for q in queries)
    prompt = (
        f"The quality checker identified gaps in the market research. "
        f"Run these targeted searches and report ONLY what you find:\n\n{query_list}\n\n"
        f"Existing research for context:\n\n{state.market_research}"
    )

    targeted_system = """\
You are filling specific gaps in market research identified by a quality audit.
Run the provided searches. Report only what you find — do not repeat existing research.
Be factual. Cite sources. If a search returns nothing useful, say so.
"""

    messages = [{"role": "user", "content": prompt}]
    new_findings = _search(targeted_system, messages, len(queries) + 1, config)

    if new_findings:
        state.market_research = (
            state.market_research.rstrip()
            + "\n\n## QC-Targeted Research (additional findings)\n\n"
            + new_findings
        )
    return state
