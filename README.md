# AI Product Manager (AIPM)

AI Product Manager (AIPM) is a capstone prototype for automating core product management work through a multi-agent pipeline. The system takes either a local **Product Bundle** or tracker-derived input, normalizes the evidence, runs a sequence of specialized PM agents, and produces structured decision artifacts such as a PRD, roadmap, experiment plan, decision log, and backlog.

This repository is built around the capstone idea of an **Autonomous AI Product Manager**: a workflow that ingests product context, analyzes customer and market evidence, checks feasibility and risk, and then consolidates everything into actionable product artifacts.

## What this project does

At a high level, the project turns raw product inputs into PM deliverables.

You provide either:

- a local **Product Bundle** containing a request, tickets, customer notes, metrics, and competitor notes, or
- a Jira-derived bundle created through the optional integration layer.

The pipeline then:

1. builds a shared product context,
2. analyzes customer signals,
3. analyzes competition and positioning,
4. proposes metrics and instrumentation,
5. translates findings into requirements and backlog candidates,
6. evaluates delivery feasibility,
7. checks privacy, compliance, and accessibility guardrails,
8. produces a final PM recommendation and written artifacts.

The output is a run folder containing JSON findings plus presentation-ready markdown and CSV files.

## Capstone alignment

This implementation follows the capstone direction closely:

- a multi-agent architecture,
- structured JSON outputs per agent,
- a Lead PM orchestration layer,
- end artifacts such as `prd.md`, `roadmap.json`, `experiment_plan.md`, `decision_log.md`, and `backlog.csv`,
- bonus-oriented integrations for Jira ingest and GitHub PR commenting.

In the current repo, the core pipeline, schema validation, sample bundles, Jira ingest module, GitHub PR posting utility, and automated tests are already present. Some folders, such as `api/`, `docs/`, and `templates/`, are still scaffolding placeholders for future expansion.

## Repository structure

```text
ai-product-manager/
├── agents/                # Specialized PM agents
├── bundles/               # Local and imported product bundles
├── cli/                   # CLI entrypoints: run / validate
├── integrations/
│   ├── github/            # GitHub PR comment posting utility
│   └── jira/              # Jira client + bundle ingest
├── orchestration/         # Pipeline orchestration
├── policies/              # Guardrails, ignore rules, risk keywords
├── schemas/               # JSON schemas for bundles and outputs
├── tests/                 # Smoke, end-to-end, Jira, GitHub tests
├── tools/                 # Writers, validators, IO helpers
├── main.py                # Project entrypoint
├── requirements.txt
└── README.md
```

## Agent pipeline

The system is organized as a sequence of specialized agents.

### 1. Intake & Context Agent

Builds `context_packet.json` from the input bundle. It loads request data, reads tickets and supporting material, normalizes ticket fields, deduplicates issues, applies ignore rules, detects missing information, tags risk hotspots, and writes an evidence index.

### 2. Customer Insights Agent

Synthesizes user pain points, segments, JTBD-style insights, and validation gaps from tickets and customer notes.

### 3. Competitive & Positioning Agent

Summarizes parity gaps, differentiation opportunities, and positioning directions from the competitor pack.

### 4. Metrics & Analytics Agent

Produces North Star candidates, input metrics, guardrails, instrumentation ideas, and metric integrity checks.

### 5. UX & Requirements Agent

Converts evidence into journeys, requirements, edge cases, acceptance criteria, and backlog-ready thinking.

### 6. Tech Feasibility & Delivery Agent

Evaluates complexity, constraints, dependencies, and phased delivery options such as MVP, V1, and V2.

### 7. Risk / Privacy / Compliance Guardrails Agent

Applies policy rules and surfaces privacy, accessibility, security, and compliance concerns.

### 8. Lead PM Agent

Consolidates the findings, resolves tensions between growth, feasibility, and risk, and produces the final recommendation plus final artifacts.

## Inputs: Product Bundle format

The main unit of execution is a **Product Bundle**. A bundle is a folder that contains a manifest plus supporting evidence files.

A typical manifest looks like this:

```json
{
  "bundle_id": "sample_01",
  "created_at": "2026-03-02",
  "source": "local",
  "files": {
    "request": "product_request.md",
    "tickets": "tickets.json",
    "customer_notes": "customer_notes.md",
    "metrics_snapshot": "metrics_snapshot.json",
    "competitors": "competitors.md"
  },
  "docs_dir": "docs"
}
```

### Minimum expected bundle contents

A practical bundle usually includes:

- `bundle_manifest.json`
- `product_request.md`
- `tickets.json`
- `customer_notes.md`
- `metrics_snapshot.json`
- `competitors.md`

The repository already includes example bundles under `bundles/`, including:

- `sample_01`
- `jira_C3APM_20260309_1144`

The `sample_01` example focuses on SaaS checkout and billing improvements, with issues related to checkout friction, billing clarity, GDPR requirements, and WCAG accessibility concerns.

## Outputs

A successful pipeline run creates a run directory containing both intermediate findings and final PM artifacts.

### Core structured outputs

- `context_packet.json`
- `findings_customer.json`
- `findings_competition.json`
- `findings_metrics.json`
- `findings_requirements.json`
- `findings_feasibility.json`
- `findings_risk.json`
- `final_recommendation.json`

### Final deliverables

- `prd.md`
- `roadmap.json`
- `experiment_plan.md`
- `decision_log.md`
- `backlog.csv`

These outputs are designed to match the capstone expectation of producing traceable PM deliverables from a single product request.

## Installation

Create and activate a virtual environment first, then install the project dependencies.

### Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Git Bash

```bash
python -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt
```

### Optional dependency for Jira integration

The Jira client imports `requests`, so if you plan to use Jira ingest you should also install:

```bash
pip install requests
```

## How to run the project

The repository exposes two CLI commands through `main.py`.

### 1. Validate a bundle

```bash
python main.py validate --bundle bundles/sample_01
```

This checks the bundle manifest and validates key files such as tickets and metrics against the JSON schemas.

### 2. Run the pipeline

```bash
python main.py run --bundle bundles/sample_01
```

On success, the pipeline writes outputs into a timestamped folder under `runs/` and logs the output path.

## Example execution flow

A typical local workflow looks like this:

```bash
python main.py validate --bundle bundles/sample_01
python main.py run --bundle bundles/sample_01
```

Then inspect the generated run directory for:

- `final_recommendation.json`
- `prd.md`
- `roadmap.json`
- `experiment_plan.md`
- `decision_log.md`
- `backlog.csv`

## Jira integration

The repo includes a Jira ingest module that can fetch Jira issues using JQL and convert them into a local Product Bundle.

### Supported behavior

The ingest flow:

- connects to Jira through a lightweight client,
- runs a JQL search,
- maps returned issues into the local ticket schema,
- creates a new bundle in `bundles/`,
- optionally summarizes comments into `customer_notes.md`.

### Environment variables

For Jira ingest, set:

```bash
JIRA_BASE_URL=
JIRA_EMAIL=
JIRA_API_TOKEN=
```

### Example usage

```python
from integrations.jira.ingest import ingest_jira_to_bundle

bundle_path = ingest_jira_to_bundle(
    jql="project = C3APM",
    include_comment_notes=True,
)

print(bundle_path)
```

After that, run the standard pipeline on the generated bundle:

```bash
python main.py run --bundle bundles/jira_C3APM_20260309_1144
```

## GitHub PR comment posting

The repository also includes a GitHub utility for posting a run summary back to a pull request.

This is useful for the bonus requirement where generated PM reviews are automatically posted to GitHub.

### What it does

- reads `final_recommendation.json` from a run directory,
- builds a markdown PR summary,
- posts it as a PR comment,
- can update an existing AIPM comment on reruns.

### How to Use the GitHub Bonus Feature

To make the GitHub bonus feature work correctly, the following procedure must be followed.

First, a pull request must be created in GitHub. After that, the pull request number should be copied and added to the `.env` file together with the required GitHub configuration. Once this is set, the pipeline can be executed normally.

If the pipeline runs successfully, the system will automatically post the generated comment to the corresponding pull request.

### Example usage

```python
import os
from integrations.github.pr_poster import build_pr_message, post_pr_comment

run_dir = "runs/2026-03-05_1638_sample_01"
body = build_pr_message(run_dir)

result = post_pr_comment(
    repo="owner/repo",
    pr_number=42,
    body=body,
    token=os.environ["GITHUB_TOKEN"],
    update_if_exists=True,
)

print(result.get("html_url"))
```

## Validation and schemas

Schema-first validation is a central part of this project.

The `schemas/` folder contains JSON schemas for:

- bundle manifests,
- tickets,
- metrics snapshots,
- context packets,
- each findings file,
- final recommendation output.

The validation workflow is handled by `tools/validate_bundle.py`, which checks the manifest, required files, ticket schema, and metrics schema before the main run starts.

## Testing

The test suite covers the most important functional paths.

Run all tests with:

```bash
pytest -q
```

The current tests cover:

- intake/context generation,
- pipeline smoke execution,
- end-to-end final output creation,
- Jira ingest,
- GitHub PR posting behavior.

## Current implementation notes

This project is already in a strong prototype state, but it is still intentionally lightweight.

A few practical notes:

1. The core flow is implemented around local bundles and schema-driven agents.
2. Jira integration exists and is test-covered, but `requests` is not currently listed in `requirements.txt`, so install it separately when using Jira.
3. GitHub PR posting is available as a Python utility module rather than a dedicated CLI command.
4. `api/`, `docs/`, and `templates/` are currently placeholders and can be expanded in future iterations.
5. The capstone brief mentions ADO or Jira; this repository currently includes Jira integration.

## Why this repository matters

This project is more than a simple script runner. It is a reproducible PM workflow prototype that shows how structured inputs, policy checks, and specialized agents can produce end-to-end product artifacts in a consistent and traceable way.

For a capstone, that makes it valuable in two ways: it demonstrates technical implementation, and it also demonstrates product thinking, because the generated outputs mirror the actual work a PM team would need to review, prioritize, and ship product changes responsibly.

## Suggested next improvements

Natural next steps for the project would be:

- add a small API or Streamlit UI on top of the existing pipeline,
- expose Jira ingest and GitHub posting through CLI commands,
- add ADO ingestion for parity with the original capstone brief,
- enrich artifact templates for more polished final outputs,
- add real LLM-backed reasoning behind individual agents if desired.

## License / note

This repository was created as a capstone prototype inspired by the Autonomous AI Product Manager proposal. Review the original capstone materials and your organization requirements before using it in a production setting.
