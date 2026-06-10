# Requirements Engineering Pipeline

A multi-agent CLI tool that interviews you about what you want to build, confirms it understood you, researches the real market, lets you pick which competitor-inspired features to adopt, then produces a structured requirements plan — critiqued and quality-checked before you approve it.

## How it works

```
Interview (uncapped, drill-downs)
   → Confirm understanding (you approve a summary before anything runs)
   → Wave 1: [Planner ‖ Market Researcher]          (research uses web search)
   → Wave 2: [Brainstormer ‖ Critic]                (both grounded in the research)
   → Feature Gate (you pick hook features + ideas)
   → Synthesize → Quality Check → Confirm
            ↑________________________________|  (loop on rejection)
```

| Agent | What it does |
|---|---|
| **Interviewer** | Asks specific, scenario-grounded questions — no cap, drills down on vague answers, checks in every 8 questions. Ends with a "here is my understanding" summary you must confirm or correct. |
| **Planner** | Converts your answers + confirmed understanding into a structured requirements doc. |
| **Market Researcher** | Web-searches competitors, indie products, user complaints, pricing, revenue comparables, and **standout/hook features users love** — then self-verifies its own report. |
| **Brainstormer** | Suggests features grounded in confirmed market gaps, real complaints, or competitor hook features (runs after research, in parallel with Critic). |
| **Critic** | Derives domain-specific critique lenses, then finds flaws — judged against the real market, not hypotheticals. |
| **Feature Gate** | Shows you a menu of competitor hook features + brainstorm ideas with evidence and tradeoffs. You pick; your choices become hard constraints. |
| **Synthesizer** | Merges everything into a final plan. Every feature is tagged with provenance: (interview), (market gap), (inspired by X), (brainstorm). |
| **Quality Checker** | Audits the plan for completeness, consistency with your confirmed understanding and feature choices, and factual correctness (targeted web searches). Failures trigger corrective passes. |

You can approve, give feedback and re-plan (up to `max_plan_iterations` times), or quit.

## Setup

```bash
pip install anthropic
export ANTHROPIC_API_KEY=your_key_here
```

## Usage

```bash
cd PlanningAgent

# Interactive (prompts for domain):
python3 pipeline.py

# With domain upfront:
python3 pipeline.py --domain "Visa tracking app"

# Custom output folder:
python3 pipeline.py --domain "Visa tracking app" --output /path/to/folder
```

The session asks for your app name and a one-line goal first, then runs the interview.
On approval, the final plan is saved to `output/output_plan_<AppName>_v<N>.md`.

## Configuration

All behavior is controlled from `config.py`. Edit `DEFAULT_CONFIG` — no other file needs touching.

Key knobs:

```python
DEFAULT_CONFIG = PipelineConfig(
    model                          = "claude-opus-4-8",  # model used by all agents
    interview_checkin_every        = 8,     # ask "keep going or proceed?" every N questions
    require_understanding_confirmation = True,  # confirm summary before research
    max_plan_iterations            = 3,     # how many times you can reject and re-plan
    brainstorm_count               = 5,     # feature suggestions from Brainstormer
    critic_lenses                  = [...], # universal baselines (Critic adds domain-specific)
    output_dir                     = "output",

    enable_market_research         = True,  # False = skip web search (offline/dev)
    market_research_max_searches   = 24,    # total web-search budget
    market_research_collect_ratio  = 2/3,   # share of budget for collection vs self-verify
    hook_features_min              = 3,     # min evidenced hook features researcher must find

    enable_feature_gate            = True,  # menu of hook features + ideas you pick from
    enable_quality_check           = True,
    qc_max_searches                = 3,
    max_qc_iterations              = 2,
)
```

Token budgets per agent are also in `config.py` (`tokens_*`) if outputs get cut off.

### Common tweaks

**Faster / cheaper runs:**
```python
DEFAULT_CONFIG = PipelineConfig(model="claude-haiku-4-5-20251001")
```

**Offline / no web search:**
```python
DEFAULT_CONFIG = PipelineConfig(enable_market_research=False)
```

**Skip the feature menu:**
```python
DEFAULT_CONFIG = PipelineConfig(enable_feature_gate=False)
```

**Always check something extra in every critique:**
```python
DEFAULT_CONFIG = PipelineConfig(
    critic_lenses=[
        "technical feasibility",
        "scope creep risk",
        "missing user value",
        "edge cases and failure modes",
        "accessibility",  # added
    ]
)
```

## Output

Saved as a versioned markdown file in `output_dir`:

```
output/
└── output_plan_VisaTrack_v1.md
```

The file contains, in order: the final requirements plan, your confirmed understanding summary, your feature-gate decisions (selected and rejected), the QC report, and the full interview transcript.

## Project structure

```
PlanningAgent/
├── pipeline.py          # coordinator — runs the full loop
├── config.py            # all tunable parameters (edit this)
├── state.py             # shared document passed between agents
├── utils.py
└── agents/
    ├── interviewer.py
    ├── planner.py
    ├── market_researcher.py
    ├── brainstormer.py
    ├── critic.py
    ├── feature_gate.py
    ├── synthesizer.py
    └── quality_checker.py
```
