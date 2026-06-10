"""
Requirements Engineering Pipeline
----------------------------------
Interview (+ confirmed understanding)
  → Wave 1: [Plan || Market Research]
  → Wave 2: [Brainstorm || Critique]  (both see the research)
  → Feature Gate (user picks hook features + brainstorm ideas)
  → Synthesize → QC → Confirm

QC loop behaviour:
  - "synthesis" failures  → synthesizer corrective pass (sees qc_report in context)
  - "reresearch" failures → market_researcher.run_targeted() then re-synthesize
  Unresolved failures after max_qc_iterations are surfaced to the user before Confirm.

State is checkpointed to disk after every phase (config.checkpoint_file), so a
crash or API error never loses the interview or paid research.

Usage:
    python pipeline.py
    python pipeline.py --domain "Healthcare scheduling app"
    python pipeline.py --domain "Visa lookup" --output /path/to/output/folder
    python pipeline.py --resume        # continue after a crash/interrupt
"""

import os
import sys
import json
import threading
import argparse
from state import PipelineState
from config import PipelineConfig, DEFAULT_CONFIG

from agents import (interviewer, planner, brainstormer, critic, market_researcher,
                    feature_gate, synthesizer, quality_checker)


def _clone_state(state: PipelineState) -> PipelineState:
    clone = PipelineState.__new__(PipelineState)
    clone.__dict__.update(state.__dict__)
    return clone


def _run_wave1(state: PipelineState, config: PipelineConfig) -> PipelineState:
    """Wave 1: planner and market researcher in parallel (interview-driven)."""
    plan_state = _clone_state(state)
    research_state = _clone_state(state)

    t1 = threading.Thread(target=lambda: planner.run(plan_state, config))
    t2 = threading.Thread(target=lambda: market_researcher.run(research_state, config))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    state.requirements = plan_state.requirements
    state.market_research = research_state.market_research
    return state


def _run_wave2(state: PipelineState, config: PipelineConfig) -> PipelineState:
    """Wave 2: brainstormer and critic in parallel — both see wave-1 research."""
    brainstorm_state = _clone_state(state)
    critic_state = _clone_state(state)

    t1 = threading.Thread(target=lambda: brainstormer.run(brainstorm_state, config))
    t2 = threading.Thread(target=lambda: critic.run(critic_state, config))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    state.brainstorm = brainstorm_state.brainstorm
    state.critique = critic_state.critique
    return state


def _run_qc_loop(state: PipelineState, config: PipelineConfig) -> PipelineState:
    """
    Post-synthesis QC loop. Runs up to config.max_qc_iterations times.
    Branches corrective action based on failure type.
    """
    if not config.enable_quality_check:
        return state

    for iteration in range(1, config.max_qc_iterations + 1):
        print(f"\n[Quality Checker running (pass {iteration}/{config.max_qc_iterations})...]")
        passed, summary, failures = quality_checker.run(state, config)

        if passed:
            print(f"[QC passed: {summary}]")
            return state

        print(f"[QC failed: {summary}]")
        for f in failures:
            print(f"  [{f['type'].upper()}] {f['description']}")

        if iteration == config.max_qc_iterations:
            # Surface unresolved failures to user — do not silently pass
            print("\n[QC WARNING] The following issues could not be auto-resolved:")
            for f in failures:
                print(f"  - [{f['type'].upper()}] {f['description']}")
            print("  Review these before treating the plan as final.\n")
            return state

        # Corrective path: reresearch failures first, then synthesis failures
        reresearch_queries = []
        for f in failures:
            if f["fix"] == "reresearch":
                reresearch_queries.extend(f.get("targeted_queries", []))

        if reresearch_queries:
            print(f"[Market Researcher: running {len(reresearch_queries)} targeted queries...]")
            state = market_researcher.run_targeted(state, config, reresearch_queries)

        # Synthesizer corrective pass — it sees qc_report in context via context_for_agents()
        print("[Synthesizer: corrective pass...]")
        state = synthesizer.run(state, config)

    return state


def _display_plan(state: PipelineState) -> None:
    width = 60
    print("\n" + "=" * width)
    print("FINAL PLAN (iteration {})".format(state.iteration))
    print("=" * width)
    print(state.final_plan)

    if state.brainstorm:
        print("\n" + "-" * width)
        print("BRAINSTORM SUGGESTIONS (for your consideration)")
        print("-" * width)
        print(state.brainstorm)

    if state.critique:
        print("\n" + "-" * width)
        print("CRITIQUE / RISKS IDENTIFIED")
        print("-" * width)
        print(state.critique)


def _confirm(state: PipelineState, max_iterations: int) -> tuple[bool, str]:
    print("\n" + "=" * 60)
    print("REVIEW")
    print("=" * 60)
    print("Options:")
    print("  1. Approve — looks good, proceed")
    print("  2. Revise  — give feedback, re-plan")
    print("  3. Quit    — exit without saving")

    while True:
        choice = input("\nYour choice (1/2/3): ").strip()
        if choice == "1":
            return True, ""
        if choice == "2":
            if state.iteration >= max_iterations:
                print(f"Max iterations ({max_iterations}) reached. Approving as-is.")
                return True, ""
            feedback = input("What should change? Be specific:\n> ").strip()
            return False, feedback
        if choice == "3":
            print("Exiting.")
            sys.exit(0)


_PIPELINE_DIR = os.path.dirname(os.path.abspath(__file__))

# Phase progression for checkpoint/resume. state.phase records the last
# COMPLETED phase; each step in run() only executes if not yet past it.
_PHASES = ["", "interview", "wave1", "wave2", "gate", "synthesize", "qc"]


def _phase_idx(phase: str) -> int:
    return _PHASES.index(phase) if phase in _PHASES else 0


def _checkpoint_path(config: PipelineConfig) -> str:
    path = config.checkpoint_file
    return path if os.path.isabs(path) else os.path.join(_PIPELINE_DIR, path)


def _save_checkpoint(state: PipelineState, config: PipelineConfig) -> None:
    if not config.enable_checkpoints:
        return
    path = _checkpoint_path(config)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(state.to_dict(), f, indent=2)


def _load_checkpoint(config: PipelineConfig) -> PipelineState | None:
    path = _checkpoint_path(config)
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return PipelineState.from_dict(json.load(f))
    except (json.JSONDecodeError, TypeError, KeyError) as err:
        print(f"[Checkpoint at {path} could not be read ({err}) — starting fresh.]")
        return None


def _clear_checkpoint(config: PipelineConfig) -> None:
    path = _checkpoint_path(config)
    if os.path.exists(path):
        os.remove(path)


def _save_plan(state: PipelineState, config: PipelineConfig, output_dir: str | None = None) -> None:
    save_dir = output_dir or config.output_dir
    save_dir = save_dir if os.path.isabs(save_dir) else os.path.join(_PIPELINE_DIR, save_dir)
    os.makedirs(save_dir, exist_ok=True)
    label = (state.app_name or state.domain)[:24].replace(" ", "_")
    version = 1
    while os.path.exists(os.path.join(save_dir, f"output_plan_{label}_v{version}.md")):
        version += 1
    path = os.path.join(save_dir, f"output_plan_{label}_v{version}.md")
    with open(path, "w") as f:
        title = state.app_name or state.domain
        f.write(f"# Requirements Plan: {title}\n\n")
        f.write(state.final_plan)
        if state.understanding:
            f.write("\n\n---\n## Confirmed Understanding\n\n")
            f.write(state.understanding)
        if state.selected_features or state.rejected_features:
            f.write("\n\n---\n## Feature Gate Decisions\n\n")
            if state.selected_features:
                f.write("**Selected:**\n")
                for feat in state.selected_features:
                    f.write(f"- {feat.get('name', '?')} ({feat.get('source', 'unknown')})\n")
            if state.rejected_features:
                f.write("\n**Rejected:**\n")
                for feat in state.rejected_features:
                    f.write(f"- {feat.get('name', '?')} ({feat.get('source', 'unknown')})\n")
        if state.qc_report:
            f.write("\n\n---\n## QC Report\n\n")
            f.write(state.qc_report)
        f.write("\n\n---\n## Interview Transcript\n\n")
        for i, qa in enumerate(state.interview, 1):
            f.write(f"**Q{i}:** {qa.question}\n")
            if qa.options:
                f.write(f"*(Options: {', '.join(qa.options)})*\n")
            f.write(f"**A:** {qa.answer}\n\n")
    print(f"\nPlan saved to: {path}")


def run(domain: str, config: PipelineConfig = DEFAULT_CONFIG,
        output_dir: str | None = None, resume: bool = False) -> PipelineState:
    state = None
    if resume:
        state = _load_checkpoint(config)
        if state is None:
            print("[No checkpoint found — starting fresh.]")
        else:
            print(f"[Resuming '{state.app_name or state.domain}' from checkpoint "
                  f"(last completed phase: {state.phase or 'none'}, iteration {state.iteration})]")
    if state is None:
        state = PipelineState(domain=domain)

    # Phase 1: Interview + confirmed understanding
    if _phase_idx(state.phase) < _phase_idx("interview"):
        state = interviewer.run(state, config)
        state.phase = "interview"
        _save_checkpoint(state, config)

    while True:
        # phase == "interview" means a planning round is starting (fresh or revision)
        if state.phase == "interview":
            if state.iteration >= config.max_plan_iterations:
                break
            state.iteration += 1

        # Phase 2 — Wave 1: Plan + Market Research in parallel
        if _phase_idx(state.phase) < _phase_idx("wave1"):
            research_note = " + Market Researcher" if config.enable_market_research else ""
            print(f"\n[Wave 1: Planner{research_note} running in parallel...]")
            if config.enable_market_research:
                print("  (market research uses web search and a self-verify pass — takes longer)")
            state = _run_wave1(state, config)
            state.phase = "wave1"
            _save_checkpoint(state, config)

        # Phase 3 — Wave 2: Brainstorm + Critique, grounded in the research
        if _phase_idx(state.phase) < _phase_idx("wave2"):
            print("[Wave 2: Brainstormer + Critic running in parallel (with research in context)...]")
            state = _run_wave2(state, config)
            state.phase = "wave2"
            _save_checkpoint(state, config)

        # Phase 4: Feature gate — user picks which candidate features to include.
        # On revision loops, prior selections carry forward instead of re-asking.
        if _phase_idx(state.phase) < _phase_idx("gate"):
            if state.iteration == 1 or not (state.selected_features or state.rejected_features):
                state = feature_gate.run(state, config)
            state.phase = "gate"
            _save_checkpoint(state, config)

        # Phase 5: Synthesize
        if _phase_idx(state.phase) < _phase_idx("synthesize"):
            print("\n[Synthesizer merging results...]")
            state = synthesizer.run(state, config)
            state.phase = "synthesize"
            _save_checkpoint(state, config)

        # Phase 6: Quality Check loop
        if _phase_idx(state.phase) < _phase_idx("qc"):
            state = _run_qc_loop(state, config)
            state.phase = "qc"
            _save_checkpoint(state, config)

        # Phase 7: Present and confirm
        _display_plan(state)
        approved, feedback = _confirm(state, config.max_plan_iterations)

        if approved:
            print("\nPlan approved!")
            _save_plan(state, config, output_dir)
            _clear_checkpoint(config)
            return state

        # Revision: reset QC state and rewind the phase so the next round
        # re-runs both waves and synthesis with the feedback in context.
        state.qc_report = ""
        state.qc_passed = False
        state.user_feedback = feedback
        state.phase = "interview"
        _save_checkpoint(state, config)
        print(f"\n[Re-planning with your feedback... (iteration {state.iteration + 1})]")

    return state


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Requirements Engineering Pipeline")
    parser.add_argument("--domain", type=str, default=None,
                        help="Problem domain (e.g. 'Visa tracking app')")
    parser.add_argument("--output", type=str, default=None,
                        help="Output folder for the saved plan (overrides config.output_dir)")
    parser.add_argument("--resume", action="store_true",
                        help="Resume from the last checkpoint instead of starting fresh")
    args = parser.parse_args()

    if args.resume:
        run(args.domain or "", output_dir=args.output, resume=True)
    else:
        domain = args.domain or input("What are you building? (describe in a few words)\n> ").strip()
        run(domain, output_dir=args.output)
