"""
Requirements Engineering Pipeline
----------------------------------
Interview → Plan → [Brainstorm || Critique || Market Research] → Synthesize → QC → Confirm

QC loop behaviour:
  - "synthesis" failures  → synthesizer corrective pass (sees qc_report in context)
  - "reresearch" failures → market_researcher.run_targeted() then re-synthesize
  Unresolved failures after max_qc_iterations are surfaced to the user before Confirm.

Usage:
    python pipeline.py
    python pipeline.py --domain "Healthcare scheduling app"
    python pipeline.py --domain "Visa lookup" --output /path/to/output/folder
"""

import os
import sys
import threading
import argparse
from state import PipelineState
from config import PipelineConfig, DEFAULT_CONFIG

from agents import interviewer, planner, brainstormer, critic, market_researcher, synthesizer, quality_checker


def _run_parallel(state: PipelineState, config: PipelineConfig) -> PipelineState:
    """Run brainstormer, critic, and market_researcher concurrently."""
    brainstorm_state = PipelineState.__new__(PipelineState)
    brainstorm_state.__dict__.update(state.__dict__)
    critic_state = PipelineState.__new__(PipelineState)
    critic_state.__dict__.update(state.__dict__)
    research_state = PipelineState.__new__(PipelineState)
    research_state.__dict__.update(state.__dict__)

    def _brainstorm():
        brainstormer.run(brainstorm_state, config)

    def _critique():
        critic.run(critic_state, config)

    def _research():
        market_researcher.run(research_state, config)

    t1 = threading.Thread(target=_brainstorm)
    t2 = threading.Thread(target=_critique)
    t3 = threading.Thread(target=_research)
    t1.start()
    t2.start()
    t3.start()
    t1.join()
    t2.join()
    t3.join()

    state.brainstorm = brainstorm_state.brainstorm
    state.critique = critic_state.critique
    state.market_research = research_state.market_research
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


def run(domain: str, config: PipelineConfig = DEFAULT_CONFIG, output_dir: str | None = None) -> PipelineState:
    state = PipelineState(domain=domain)

    # Phase 1: Interview
    state = interviewer.run(state, config)

    while state.iteration < config.max_plan_iterations:
        state.iteration += 1

        # Phase 2: Plan
        state = planner.run(state, config)

        # Phase 3: Brainstorm + Critique + Market Research in parallel
        research_note = " + Market Researcher" if config.enable_market_research else ""
        print(f"\n[Brainstormer + Critic{research_note} running in parallel...]")
        if config.enable_market_research:
            print("  (market research uses web search and a self-verify pass — takes longer)")
        state = _run_parallel(state, config)

        # Phase 4: Synthesize
        print("[Synthesizer merging results...]")
        state = synthesizer.run(state, config)

        # Phase 5: Quality Check loop
        state = _run_qc_loop(state, config)

        # Phase 6: Present and confirm
        _display_plan(state)
        approved, feedback = _confirm(state, config.max_plan_iterations)

        if approved:
            print("\nPlan approved!")
            _save_plan(state, config, output_dir)
            return state

        # Reset QC state for next iteration
        state.qc_report = ""
        state.qc_passed = False
        state.user_feedback = feedback
        print(f"\n[Re-planning with your feedback... (iteration {state.iteration + 1})]")

    return state


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Requirements Engineering Pipeline")
    parser.add_argument("--domain", type=str, default=None,
                        help="Problem domain (e.g. 'Visa tracking app')")
    parser.add_argument("--output", type=str, default=None,
                        help="Output folder for the saved plan (overrides config.output_dir)")
    args = parser.parse_args()

    domain = args.domain or input("What are you building? (describe in a few words)\n> ").strip()
    run(domain, output_dir=args.output)
