from dataclasses import dataclass, field


@dataclass
class PipelineConfig:
    # Model used by all agents. Swap here to change for the entire pipeline.
    model: str = "claude-opus-4-8"

    # Interview is uncapped — it continues until every mandatory topic has a
    # concrete answer. Every `interview_checkin_every` questions, the user is
    # asked whether to keep going or proceed with what's been gathered.
    interview_checkin_every: int = 8

    # After the interview, the interviewer presents a "here is my understanding"
    # summary the user must confirm or correct before research starts.
    require_understanding_confirmation: bool = True

    # How many times can user reject and re-plan?
    max_plan_iterations: int = 3

    # Universal baseline lenses — critic agent adds domain-specific ones on top.
    # Edit these if you want to always check something extra across all your runs.
    critic_lenses: list[str] = field(default_factory=lambda: [
        "technical feasibility",
        "scope creep risk",
        "missing user value",
        "edge cases and failure modes",
    ])

    # How many alternative features should brainstormer suggest?
    brainstorm_count: int = 5

    # Where to save the final plan markdown file.
    output_dir: str = "output"

    # Market researcher: set to False to skip web search (saves cost, use for offline/dev)
    enable_market_research: bool = True
    # Max number of web searches the market researcher may perform in one run (incl. self-verify pass)
    market_research_max_searches: int = 24
    # Fraction of the search budget spent on the collect pass; the rest goes to self-verify.
    market_research_collect_ratio: float = 2 / 3
    # Minimum number of competitor hook/standout features the researcher must find with cited evidence.
    hook_features_min: int = 3

    # Feature decision gate: after research + brainstorm, present a menu of
    # competitor hook features and brainstorm ideas for the user to pick from
    # before the plan is synthesized.
    enable_feature_gate: bool = True

    # Quality checker: runs post-synthesis to audit completeness, consistency, and factual correctness
    enable_quality_check: bool = True
    # Max targeted web searches the QC agent may use to verify claims
    qc_max_searches: int = 3
    # Max QC + corrective-pass cycles before surfacing unresolved failures to the user
    max_qc_iterations: int = 2

    # Token budgets per agent — tune if responses are getting cut off or you want to save cost.
    tokens_interview: int = 512          # one question at a time, short output
    tokens_interview_summary: int = 1024 # "here is my understanding" checkpoint summary
    tokens_plan: int = 2000              # full structured requirements doc
    tokens_brainstorm: int = 1500        # N feature suggestions with value + tradeoff each
    tokens_critique_derive: int = 256    # just a JSON array of lens names
    tokens_critique_evaluate: int = 2000 # full critique across all lenses
    tokens_market_research: int = 6000   # market researcher needs room for search + hook features + synthesis
    tokens_feature_menu: int = 2000      # JSON menu of candidate features for the decision gate
    tokens_synthesize: int = 4000        # final plan — bumped to accommodate market research section
    tokens_quality_check: int = 2000     # QC report is structured JSON — doesn't need much room


# Default behavioral config — edit this to change how the pipeline works.
# Do NOT put domain/app names here; those are passed at runtime via --domain.
DEFAULT_CONFIG = PipelineConfig()
