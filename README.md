# Requirement Pipeline

A multi-agent requirements engineering pipeline that interviews you about what you want to build, then produces a structured, market-researched, and critiqued requirements plan.

---

## What's in here

```
requirement-pipeline/
├── scripts/
│   └── requirements_pipeline/   # Standalone Python CLI — runs without Claude Code
└── skills/
    └── requirements.md          # Claude Code skill — runs inside Claude Code as /requirements
```

---

## Option 1 — Claude Code skill (`/requirements`)

The skill in `skills/requirements.md` runs the full pipeline **inside Claude Code** using its native multi-agent system. No Python setup needed.

### Install

Copy `skills/requirements.md` into your Claude Code commands folder:

```bash
# macOS / Linux
cp skills/requirements.md ~/.claude/commands/requirements.md
```

### Use

Open any project in Claude Code and type:

```
/requirements
```

Claude Code will conduct the interview, then run planner, market researcher, brainstormer, and critic agents in parallel before synthesizing a final plan. On approval, the plan is saved as `requirements_<AppName>.md` in your working directory.

---

## Option 2 — Python CLI (`scripts/requirements_pipeline`)

The Python pipeline runs standalone via the Anthropic SDK — no Claude Code required.

### Setup

```bash
pip install anthropic
export ANTHROPIC_API_KEY=your_key_here
```

### Use

```bash
cd scripts/requirements_pipeline

# Interactive (prompts for domain):
python3 pipeline.py

# With domain upfront:
python3 pipeline.py --domain "Visa tracking app"
```

On approval, the final plan is saved to `output/output_plan_<AppName>.md`.

### Configure

All tunable parameters live in `config.py` — model, token limits, interview depth, output folder. No other file needs touching.

---

## How the pipeline works

```
Interview → Plan → [Market Research ‖ Brainstorm ‖ Critic] → Synthesize → QC → Confirm
                                    ↑_______________________________________________|
                                                  (loop on rejection, up to 3×)
```

| Agent | What it does |
|---|---|
| **Interviewer** | Asks one question at a time (MCQ preferred). Covers users, problem, constraints, and business model. |
| **Planner** | Converts interview answers into a structured requirements doc. |
| **Market Researcher** | Searches for real competitors, user pain points, pricing, and market gaps. |
| **Brainstormer** | Suggests features the user may not have considered. |
| **Critic** | Derives domain-specific risk lenses, then evaluates the plan through each one. |
| **Synthesizer** | Merges all inputs into a final plan with market grounding. |
| **Quality Checker** | Audits the plan for completeness, consistency, and factual accuracy before showing it to you. |

---

## License

MIT
