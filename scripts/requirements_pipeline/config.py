from dataclasses import dataclass, field


@dataclass
class PipelineConfig:
    # Model used by all agents. Swap here to change for the entire pipeline.
    model: str = "claude-opus-4-8"

    # How many interview rounds before moving to planning?
    # 5 is the minimum to reliably cover: users, problem, platform, data source, business model.
    max_interview_rounds: int = 5

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
    market_research_max_searches: int = 10

    # Quality checker: runs post-synthesis to audit completeness, consistency, and factual correctness
    enable_quality_check: bool = True
    # Max targeted web searches the QC agent may use to verify claims
    qc_max_searches: int = 3
    # Max QC + corrective-pass cycles before surfacing unresolved failures to the user
    max_qc_iterations: int = 2

    # Token budgets per agent — tune if responses are getting cut off or you want to save cost.
    tokens_interview: int = 512          # one question at a time, short output
    tokens_plan: int = 2000              # full structured requirements doc
    tokens_brainstorm: int = 1500        # N feature suggestions with value + tradeoff each
    tokens_critique_derive: int = 256    # just a JSON array of lens names
    tokens_critique_evaluate: int = 2000 # full critique across all lenses
    tokens_market_research: int = 4000   # market researcher needs room for search + synthesis
    tokens_synthesize: int = 4000        # final plan — bumped to accommodate market research section
    tokens_quality_check: int = 2000     # QC report is structured JSON — doesn't need much room


# Default behavioral config — edit this to change how the pipeline works.
# Do NOT put domain/app names here; those are passed at runtime via --domain.
DEFAULT_CONFIG = PipelineConfig()
