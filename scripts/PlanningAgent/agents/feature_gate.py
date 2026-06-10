"""
Feature gate: the user decides which candidate features make it into the plan.

After wave 2 (brainstorm + critique), one LLM call merges the competitor hook
features from the market research and the brainstorm ideas into a normalized
menu. The user picks any subset; selections and rejections are stored in state
and become hard constraints for the synthesizer.
"""

import json
import anthropic
from state import PipelineState
from config import PipelineConfig

_client = anthropic.Anthropic()

_SYSTEM = """\
You build a feature decision menu for a product planning session.

You receive market research (with a "Standout / Hook Features" section) and a list
of brainstorm suggestions. Merge them into one deduplicated menu of candidate
features the user could add to their product.

Rules:
- Include every hook feature from the research and every brainstorm idea, unless
  two entries are clearly the same feature — then merge them into one.
- Do NOT include features already required by the interview/requirements draft.
- Do NOT invent new features.
- Keep each field to one sentence.

Output valid JSON only — an array, no markdown fences:
[
  {
    "name": "feature name",
    "source": "inspired by <Competitor> — users rave about it" | "brainstorm — exploits <gap>" | "original idea — the system's own suggestion",
    "value": "one-line user value",
    "evidence": "the user praise / market gap / complaint backing this, with source — for original ideas, the reasoning why it fits this product",
    "tradeoff": "one-line cost or risk"
  }
]

Brainstorm entries marked ORIGINAL have no market evidence by design — keep them,
label their source "original idea — ...", and put the reasoning in "evidence".
"""


def _build_menu(state: PipelineState, config: PipelineConfig) -> list[dict]:
    parts = [
        f"Domain: {state.domain}",
        f"App: {state.app_name}",
        f"Goal: {state.goal}",
        "",
        "Requirements Draft (features here are ALREADY planned — exclude them):",
        state.requirements,
        "",
        "Market Research:",
        state.market_research,
        "",
        "Brainstorm Suggestions:",
        state.brainstorm,
    ]
    response = _client.messages.create(
        model=config.model_for("feature_gate"),
        max_tokens=config.tokens_feature_menu,
        system=_SYSTEM,
        messages=[{"role": "user", "content": "\n".join(parts)}],
    )
    text = response.content[0].text.strip()
    if "```" in text:
        for part in text.split("```"):
            candidate = part.strip()
            if candidate.startswith("json"):
                candidate = candidate[4:].strip()
            if candidate.startswith("["):
                text = candidate
                break
    try:
        menu = json.loads(text)
        return menu if isinstance(menu, list) else []
    except json.JSONDecodeError:
        return []


def _display_menu(menu: list[dict]) -> None:
    print("\n" + "=" * 60)
    print("FEATURE DECISION GATE")
    print("=" * 60)
    print("These candidate features came from competitor research and brainstorming.")
    print("Pick the ones you want in the plan — the rest will be kept out.\n")
    for i, feat in enumerate(menu, 1):
        print(f"  [{i}] {feat.get('name', '?')}")
        print(f"      Source:   {feat.get('source', '?')}")
        print(f"      Value:    {feat.get('value', '?')}")
        if feat.get("evidence"):
            print(f"      Evidence: {feat['evidence']}")
        print(f"      Tradeoff: {feat.get('tradeoff', '?')}")
        print()


def _collect_selection(menu: list[dict]) -> tuple[list[dict], list[dict]]:
    while True:
        raw = input(
            "Which features should be included? (numbers like 1,3,5 / 'all' / 'none'): "
        ).strip().lower()
        if raw == "all":
            return list(menu), []
        if raw == "none":
            return [], list(menu)
        try:
            picks = {int(tok) for tok in raw.replace(",", " ").split()}
        except ValueError:
            print(f"  Please enter numbers 1–{len(menu)}, 'all', or 'none'.")
            continue
        if picks and all(1 <= p <= len(menu) for p in picks):
            selected = [feat for i, feat in enumerate(menu, 1) if i in picks]
            rejected = [feat for i, feat in enumerate(menu, 1) if i not in picks]
            return selected, rejected
        print(f"  Please enter numbers 1–{len(menu)}, 'all', or 'none'.")


def run(state: PipelineState, config: PipelineConfig) -> PipelineState:
    if not config.enable_feature_gate:
        return state

    menu = _build_menu(state, config)
    if not menu:
        print("\n[Feature gate] No candidate features to choose from — continuing.")
        return state

    _display_menu(menu)
    selected, rejected = _collect_selection(menu)
    state.selected_features = selected
    state.rejected_features = rejected
    print(f"\n[Feature gate] {len(selected)} feature(s) selected, {len(rejected)} rejected.")
    return state
