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

    # Filled by planner
    requirements: str = ""

    # Filled in parallel by brainstormer + critic + market_researcher
    brainstorm: str = ""
    critique: str = ""
    market_research: str = ""

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

    def context_for_agents(self) -> str:
        parts = [f"Domain: {self.domain}"]
        if self.app_name:
            parts.append(f"App Name: {self.app_name}")
        parts.append(f"User Goal: {self.goal}")
        if self.interview:
            parts += ["", "Interview Transcript:", self.interview_summary()]
        if self.requirements:
            parts += ["", "Requirements Draft:", self.requirements]
        if self.market_research:
            parts += ["", "Market Research:", self.market_research]
        if self.qc_report:
            parts += ["", "Quality Check Report:", self.qc_report]
        if self.brainstorm:
            parts += ["", "Brainstorm Suggestions:", self.brainstorm]
        if self.critique:
            parts += ["", "Critique / Flaws Found:", self.critique]
        return "\n".join(parts)
