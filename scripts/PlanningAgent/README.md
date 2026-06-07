# Requirements Engineering Pipeline

A multi-agent CLI tool that interviews you about what you want to build, then produces a structured requirements plan — reviewed, critiqued, and refined before you approve it.

## How it works

```
Interview → Plan → [Brainstorm ‖ Critic] → Synthesize → Confirm
                         ↑__________________________|  (loop on rejection)
```

| Agent | What it does |
|---|---|
| **Interviewer** | Asks structured MCQ / yes-no questions. Never speculates. Stops when it has enough. |
| **Planner** | Converts your answers into a structured requirements doc. |
| **Brainstormer** | Suggests features you may not have considered (runs in parallel with Critic). |
| **Critic** | Derives domain-specific critique lenses from the requirements, then finds flaws through them. |
| **Synthesizer** | Merges all three outputs into a final plan for your approval. |

You can approve, give feedback and re-plan (up to `max_plan_iterations` times), or quit.

## Setup

```bash
pip install anthropic
export ANTHROPIC_API_KEY=your_key_here
```

## Usage

```bash
cd requirements_pipeline

# Interactive (prompts for domain):
python3 pipeline.py

# With domain upfront:
python3 pipeline.py --domain "Visa tracking app"
```

The session asks for your app name and a one-line goal first, then runs the interview.  
On approval, the final plan is saved to `output/output_plan_<AppName>.md`.

## Configuration

All behavior is controlled from `config.py`. Edit `DEFAULT_CONFIG` — no other file needs touching.

```python
DEFAULT_CONFIG = PipelineConfig(
    model                  = "claude-opus-4-8",  # model used by all agents
    max_interview_rounds   = 3,    # questions asked before moving to planning
    max_plan_iterations    = 3,    # how many times user can reject and re-plan
    brainstorm_count       = 5,    # number of feature suggestions from Brainstormer
    critic_lenses          = [...],# universal baseline lenses (Critic adds domain-specific ones on top)
    output_dir             = "output",  # relative to pipeline.py, or absolute path
    tokens_interview       = 512,  # one question at a time
    tokens_plan            = 1500, # full requirements doc
    tokens_brainstorm      = 1200, # N suggestions with value + tradeoff
    tokens_critique_derive = 256,  # JSON array of lens names
    tokens_critique_evaluate = 1500, # full critique across all lenses
    tokens_synthesize      = 2000, # final plan — largest output
)
```

### Common tweaks

**Faster / cheaper runs:**
```python
DEFAULT_CONFIG = PipelineConfig(model="claude-haiku-4-5-20251001")
```

**Deeper interviews:**
```python
DEFAULT_CONFIG = PipelineConfig(max_interview_rounds=6)
```

**Custom output folder:**
```python
DEFAULT_CONFIG = PipelineConfig(output_dir="/Users/you/Documents/plans")
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

Saved as a markdown file in `output_dir`:

```
output/
└── output_plan_VisaTrack.md
```

The file contains the final requirements plan followed by the full interview transcript.

## Project structure

```
requirements_pipeline/
├── pipeline.py          # coordinator — runs the full loop
├── config.py            # all tunable parameters (edit this)
├── state.py             # shared document passed between agents
└── agents/
    ├── interviewer.py
    ├── planner.py
    ├── brainstormer.py
    ├── critic.py
    └── synthesizer.py
```
