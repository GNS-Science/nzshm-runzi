# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Code Intelligence

Prefer LSP over Grep/Glob/Read for code navigation:
- `goToDefinition` / `goToImplementation` to jump to source
- `findReferences` to see all usages across the codebase
- `workspaceSymbol` to find where something is defined
- `documentSymbol` to list all symbols in a file
- `hover` for type info without reading the file
- `incomingCalls` / `outgoingCalls` for call hierarchy

Before renaming or changing a function signature, use
`findReferences` to find all call sites first.

Use Grep/Glob only for text/pattern searches (comments,
strings, config values) where LSP doesn't help.

After writing or editing code, check LSP diagnostics before
moving on. Fix any type errors or missing imports immediately.


## Overview

`nzshm-runzi` is a Python CLI application for running, scheduling, and managing NZSHM (New Zealand Seismic Hazard Model) computational jobs across local machines, AWS ECS/Batch, and HPC clusters. It coordinates job creation, argument sweeping, script generation, and result storage via the toshi API.

- **Python**: 3.11 only (`>=3.11,<3.12`)
- **Package manager**: uv
- **CLI framework**: Typer
- **Data validation**: Pydantic v2+

## Commands

```bash
# Run all tests with coverage
pytest --cov=runzi --cov-branch --cov-report=xml --cov-report=term-missing tests runzi

# Run a single test file
pytest tests/test_get_oq_hazard_tasks.py

# Run a single test function
pytest tests/test_get_oq_hazard_tasks.py::test_build_hazard_tasks

# Run tests matching a pattern
pytest -k "hazard"

# Format code
ruff check --select I --fix runzi tests && ruff format runzi tests

# Lint
ruff check runzi tests && mypy runzi tests

# Full tox suite
tox -e py311,format,lint
```

## Architecture

### Execution Flow

The core execution pipeline is:

1. **CLI** (`runzi/cli/`) invokes a **JobRunner** with a config file path
2. **`ArgSweeper`** (`runzi/arguments.py`) parses the JSON config, producing a prototype `*Args` object and a dict of swept arguments
3. **`JobRunner`** (`runzi/job_runner.py`) is an abstract base class; concrete subclasses (e.g., `OQHazardJobRunner`) live in each task module directory
4. **`build_tasks()`** (`runzi/build_tasks.py`) iterates swept args and generates either bash scripts (LOCAL/CLUSTER) or AWS Batch job configs (AWS)
5. **Task scripts** invoke the corresponding `*_task.py` module directly (e.g., `oq_hazard_task.py`), which does the actual computation

### Key Abstractions

**`SubmissionArgs` / `TaskRuntimeArgs`** (`runzi/arguments.py`): the submission↔worker arg split (ADR-0009). `SubmissionArgs` is the submitter-only config (ECS sizing, job definition, queue/compute env, task language) that each task module declares as a module-level `default_submission_args` instance and is **not** serialized to the worker. `TaskRuntimeArgs` is the small per-task context the worker needs (`general_task_id`, `task_count`, `use_api`, `java_threads`, `allocated_vcpu`); it's assembled in `build_tasks` and is the only args model shipped to the container. Its `java_gateway_port` is a compute-on-read property (not a shipped field): the launcher that starts the JVM exports `NZSHM22_APP_PORT` (a free port per container on AWS Batch, where forced host networking makes a fixed port collide across concurrent jobs; the per-task port in the generated bash script on LOCAL/CLUSTER) and the property reads it, keeping the JVM and Python client on one port.

**Task-specific `*Args`** classes: Pydantic models for user-provided job parameters (e.g., `OQHazardArgs` in `runzi/tasks/oq_hazard/hazard_args.py`).

**`ArgSweeper`**: Parses JSON config files with optional `swept_args` dict, generating all combinations as separate tasks. Config files have `title`, `description`, optional `swept_args`, and optional `submission_arg_overrides` fields alongside the task args.

**Task Factory pattern** (`runzi/automation/opensha_task_factory.py`, `python_task_factory.py`): Produces bash scripts (LOCAL), PBS scripts (CLUSTER), or AWS Batch configs (AWS) depending on the `--cluster-mode` CLI flag. Java-based tasks use `OpenshaTaskFactory`; Python-only tasks use `PythonTaskFactory`.

**`ModuleWithDefaultSubmissionArgs` protocol** (`runzi/protocols.py`): Task modules must expose a `default_submission_args: SubmissionArgs` attribute and `__name__`, so the factory can locate the task script file and obtain ECS defaults.

### Directory Structure

```
runzi/
├── cli/              # Typer CLI subcommands (inversion, hazard, ipp, rupset, reports, utils)
├── tasks/            # Task implementations, each with runner + task + args modules
│   ├── inversion/    # Java-based crustal/subduction inversion tasks
│   ├── oq_hazard/    # OpenQuake hazard + disaggregation tasks (Python)
│   └── ...           # scale_solution, rupset_report, etc.
├── automation/       # Task factories, toshi API client wrappers, scheduling
│   └── toshi_api/    # GraphQL API clients for general tasks, hazard tasks, solutions
├── aws/              # AWS ECS job config builder and S3 utilities
├── arguments.py      # SubmissionArgs, TaskRuntimeArgs, ArgSweeper
├── build_tasks.py    # Iterates ArgSweeper, dispatches to task factory
├── job_runner.py     # Abstract JobRunner base class
└── protocols.py      # ModuleWithDefaultSysArgs protocol
```

### Environment Configuration

Runtime configuration is via environment variables (loaded from `.env` by python-dotenv on the local machine).

**Local machine (`.env`)**

| Variable | Purpose |
|---|---|
| `NZSHM22_TOSHI_API_ENABLED` | Enable toshi API metadata storage |
| `NZSHM22_TOSHI_API_URL` | Toshi GraphQL API endpoint |
| `NZSHM22_TOSHI_API_KEY` | API auth key (legacy; prefer Cognito login) |
| `NZSHM22_TOSHI_COGNITO_DOMAIN` | Cognito domain for Scientist (interactive) login |
| `NZSHM22_TOSHI_COGNITO_SCIENTIST_CLIENT_ID` | Cognito app client ID for Scientist login |
| `NZSHM22_TOSHI_COGNITO_USER_POOL_ID` | Cognito user pool ID |
| `NZSHM22_TOSHI_COGNITO_IDENTITY_POOL_ID` | Cognito identity pool ID (for AWS credential federation) |
| `NZSHM22_TOSHI_COGNITO_REGION` | AWS region for Cognito (default `ap-southeast-2`) |
| `NZSHM22_SCRIPT_WORKER_POOL_SIZE` | Parallel worker count (LOCAL mode) |
| `NZSHM22_SCRIPT_WORK_PATH` | Working directory for task scripts/configs |
| `NZSHM22_OPENSHA_ROOT` | Path to OpenSHA repo (Java tasks) |
| `NZSHM22_FATJAR` | Path to OpenSHA fat JAR |
| `NZSHM22_RUNZI_ECR_DIGEST` | AWS ECR image digest for ECS tasks |
| `NZSHM22_THS_RLZ_DB` | toshi-hazard-store hazard realization database path (local directory or `s3://`) |
| `NZSHM22_THS_DISAGG_RLZ_DB` | toshi-hazard-store disaggregation realization database path (local directory or `s3://`) |
| `NZSHM22_OQ_VENV` | Path to the OpenQuake virtual environment root (e.g. `/opt/oq-venv`); required for OQ tasks |
| `NZSHM22_OQ_DATADIR` | Directory where `oq engine` writes HDF5 calc datastores (e.g. `/oqdata`); required for OQ tasks |

**AWS Batch job definition** (set in infrastructure, not forwarded from the local host)

| Variable | Purpose |
|---|---|
| `NZSHM22_TOSHI_M2M_SECRET_ARN` | ARN of the Secrets Manager secret holding the M2M (machine-to-machine) Cognito client credentials; triggers M2M JWT auth in the container |
| `NZSHM22_TOSHI_COGNITO_DOMAIN` | Cognito domain used for M2M token exchange inside the Batch container |

### Adding a New Task

1. Create a directory under `runzi/tasks/<task_name>/`
2. Define a Pydantic `*Args` model for user parameters
3. Implement the task module with a `default_submission_args` module-level instance (a `SubmissionArgs`) and `if __name__ == "__main__":` entry point that calls `get_config()`, rebuilds a `TaskRuntimeArgs` from `config['task_runtime_args']`, then runs the task
4. Create a `*Runner` subclass of `JobRunner` that sets `subtask_type`, `job_name`, and implements `get_model_type()`
5. Wire up a CLI command in `runzi/cli/` using Typer

## Code Style

- Line length: 120 characters
- Black with `skip-string-normalization = true` (single quotes)
- isort with vertical hanging indent (`multi_line_output = 3`)
- Google-style docstrings
- Use `TYPE_CHECKING` guards for type-hint-only imports
- Pydantic models: use `model_validate()`, `model_dump(mode='json')`, `model_copy(deep=True)`

See `AGENTS.md` for full coding conventions.
