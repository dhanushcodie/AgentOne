from dataclasses import dataclass, field
from typing import Optional


@dataclass
class QAPair:
    question: str
    options: Optional[list[str]]  # None means free-text
    answer: str


@dataclass
class PipelineState:
    domain: str
    goal: str = ""
    app_name: str = ""  # gathered by interviewer as question 0

    # Filled by interviewer
    interview: list[QAPair] = field(default_factory=list)
    # Confirmed "here is my understanding" summary — user-approved before research
    understanding: str = ""

    # Filled by planner
    requirements: str = ""

    # Filled by market_researcher (wave 1) and brainstormer + critic (wave 2)
    brainstorm: str = ""
    critique: str = ""
    market_research: str = ""

    # Filled by feature gate (user picks from hook features + brainstorm ideas)
    selected_features: list[dict] = field(default_factory=list)
    rejected_features: list[dict] = field(default_factory=list)

    # Filled by synthesizer
    final_plan: str = ""

    # Filled by quality checker
    qc_report: str = ""
    qc_passed: bool = False

    # Loop control
    iteration: int = 0
    user_feedback: str = ""

    def interview_summary(self) -> str:
        lines = []
        for qa in self.interview:
            lines.append(f"Q: {qa.question}")
            if qa.options:
                lines.append(f"   Options: {', '.join(qa.options)}")
            lines.append(f"A: {qa.answer}")
        return "\n".join(lines)

    @staticmethod
    def _format_features(features: list[dict]) -> str:
        lines = []
        for feat in features:
            lines.append(f"- {feat.get('name', '?')} (source: {feat.get('source', 'unknown')})")
            if feat.get("value"):
                lines.append(f"  Value: {feat['value']}")
        return "\n".join(lines)

    def context_for_agents(self) -> str:
        parts = [f"Domain: {self.domain}"]
        if self.app_name:
            parts.append(f"App Name: {self.app_name}")
        parts.append(f"User Goal: {self.goal}")
        if self.interview:
            parts += ["", "Interview Transcript:", self.interview_summary()]
        if self.understanding:
            parts += ["", "Confirmed Understanding (user-approved summary of expectations):",
                      self.understanding]
        if self.requirements:
            parts += ["", "Requirements Draft:", self.requirements]
        if self.market_research:
            parts += ["", "Market Research:", self.market_research]
        if self.selected_features:
            parts += ["", "User-Selected Features (MUST be included in the plan):",
                      self._format_features(self.selected_features)]
        if self.rejected_features:
            parts += ["", "User-Rejected Features (MUST NOT be included in the plan):",
                      self._format_features(self.rejected_features)]
        if self.qc_report:
            parts += ["", "Quality Check Report:", self.qc_report]
        if self.brainstorm:
            parts += ["", "Brainstorm Suggestions:", self.brainstorm]
        if self.critique:
            parts += ["", "Critique / Flaws Found:", self.critique]
        return "\n".join(parts)
