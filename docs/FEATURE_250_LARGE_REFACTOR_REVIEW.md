# Code Review: `feature/250-input-validation-v2`

## Context

This branch represents the v0.2.0 refactor of nzshm-runzi — a complete reworking of the job configuration and execution architecture, aimed at making the codebase more maintainable, type-safe, and extensible. The review compares against `main` across 95 commits.

---

## 1. Summary of Structural & Architectural Changes

### The Big Picture

The old architecture had task logic scattered across `runners/`, `scripts/`, `execute/`, and `configuration/` directories with ad-hoc argument handling. The new architecture consolidates everything into a clean, modular pattern:

| Component | Old Location | New Location |
|-----------|-------------|--------------|
| Task runners | `runzi/runners/` (flat) | `runzi/tasks/{task_name}/` (per-task packages) |
| CLI entry points | `runzi/scripts/` | `runzi/cli/` (modular Typer subcommands) |
| AWS utilities | `runzi/util/aws/` | `runzi/aws/` (top-level) |
| Argument handling | Scattered across runners | `runzi/arguments.py` (unified) |
| Config permutations | `runzi/configuration/` | Removed (replaced by ArgSweeper) |
| Test root | `test/` | `tests/` (Python convention) |

### Core Architectural Additions

**`arguments.py`** — Introduces `ArgSweeper` and `SystemArgs`, providing a single unified pattern for loading config from JSON, validating with Pydantic, and sweeping across parameter combinations.

**`job_runner.py`** — Abstract `JobRunner` base class that standardizes the run-submit-track lifecycle. Each task simply inherits and provides its `Args` class and task module.

**Per-task package pattern:**
```
runzi/tasks/{task_name}/
├── __init__.py              # Exports Args + JobRunner
├── {task_name}_task.py      # Pydantic Args model + execution logic
└── {task_name}_runner.py    # JobRunner subclass
```

**Modular CLI** — Typer app with subcommands (`hazard`, `inversion`, `rupture-sets`, `reports`), each in its own module. Clean 3-line command pattern: load config → create runner → run.

---

## 2. Code Statistics

| Metric | Value |
|--------|-------|
| Files changed | 398 |
| Lines added | **10,010** |
| Lines removed | **45,409** |
| Net change | **-35,399 lines** |
| Python files changed | 186 |
| Python lines added | 5,426 |
| Python lines removed | 20,774 |
| New files | 98 |
| Deleted files | 235 |
| Modified files | 65 |
| Total commits | 95 |

**Verdict:** A net reduction of ~35K lines is a strong signal — the codebase got dramatically leaner. Much of the removed code was legacy configuration, old runners, and large fixture/data files.

---

## 3. New Patterns & Improvements

### Pydantic v2 Validation (the headline feature)

The branch introduces a layered validation approach using modern Pydantic v2 patterns:

- **`Annotated[type, AfterValidator(fn)]`** for inline single-field validation (e.g., model version checks, compatible calc ID lookups)
- **`@field_validator`** for path resolution relative to config file location
- **`@model_validator(mode='after')`** for cross-field dependency validation (e.g., "if no model version, must provide all three logic tree files")
- **Context injection** via `model_validate(..., context={"base_path": ...})` for resolving relative file paths

This means invalid configurations fail fast with clear error messages, rather than blowing up deep in task execution.

### Dependency Injection via Context

`ArgSweeper.from_config_file()` passes the config file's parent directory as context to Pydantic validators, enabling clean relative path resolution without global state.

### Extensibility

Adding a new task type is now a well-defined recipe: create a package in `tasks/`, define an `Args` model with validators, subclass `JobRunner`, and wire up a CLI command. The old pattern required touching multiple scattered files.

### Modernization

- `pyproject.toml` as the single source of project metadata
- Type hints throughout
- Python 3.9 dropped (3.10+ only)
- Version bumped to 0.2.0
- Conventional `tests/` directory

---

## 4. Possible Further Improvements

### Architecture
- **Consider a task registry pattern** — Rather than manually wiring each task into the CLI, tasks could self-register (e.g., via entry points or a decorator), reducing the boilerplate when adding new task types.
- **Shared validator library** — Several validators (path resolution, model version checking) are repeated across task args classes. These could be extracted into a `runzi.validation` module.

### Code Quality
- **`extra='forbid'` in model_config** — Currently passed at call sites (`model_validate(..., extra='forbid')`). Consider setting `model_config = ConfigDict(extra='forbid')` directly on the base args models so it can't be forgotten.
- **Error message consistency** — Some validators raise bare `ValueError` while others provide detailed context. A consistent error message pattern (e.g., including the field name and expected values) would improve the user experience.

### Developer Experience
- **Type stubs or protocols for task modules** — `task_module: ModuleType` in `JobRunner.__init__` relies on duck typing (`task_module.default_system_args`). A Protocol class would make the contract explicit and catch errors at type-check time.

---

## 5. Documentation Review

### What Exists

| Document | Status | Notes |
|----------|--------|-------|
| CHANGELOG.md | Updated | Covers v0.2.0 changes but quite terse |
| README.md | Updated | New badges, CLI examples, links |
| `docs/architecture/architecture.md` | New | Mermaid class diagram of JobRunner/ArgSweeper |
| `docs/usage/input/*.md` | New | Auto-generated API docs from Pydantic model docstrings |
| `docs/testing.md` | Exists | **Empty** (1 line) |
| mkdocs.yml | Updated | Reflects new doc structure |

### Correlation with Code Changes

The docs accurately reflect the *structure* of the new architecture (the class diagram matches the code). The auto-generated input docs pull from Pydantic models, which is a good pattern.

### Gaps & Inconsistencies

1. **No validation rules documentation** — The Pydantic models encode ~20+ validation rules (incompatible parameter combinations, required file groups, path constraints). None of these are documented in user-facing prose. Users will only discover them via error messages at runtime.

2. **No migration guide** — This is a breaking refactor from v0.1.0 to v0.2.0. There's no guide showing old config format → new config format, or old CLI usage → new CLI usage.

3. **Empty `docs/testing.md`** — Promised but not delivered. Should describe how to run tests, the test structure, and how to add tests for new task types.

4. **CHANGELOG could be richer** — The current entry is:
   > "Complete refactor of job configuration and execution"

   A few more bullets on what this means practically (e.g., "JSON config files are now validated before submission", "CLI restructured into subcommands") would help users.

5. **Removed docs not fully replaced** — Old process docs (`docs/process/openquake_processes.md`, `docs/process/opensha_processes.md`) were deleted. If that procedural knowledge is still relevant, it should live somewhere.

---

## 6. Test Coverage Review

### What's There (and it's good!)

| Test File | Lines | Coverage Area |
|-----------|-------|--------------|
| `test_inversion_input.py` | 96 | Cross-field validation for inversion args |
| `test_oq_args.py` | 187 | Comprehensive OQ hazard/disagg validation |
| `test_swept_args.py` | 27 | ArgSweeper parameter sweeping |
| `test_openquake_hazard_task.py` | 52 | Hazard task initialization |
| `test_get_oq_hazard_tasks.py` | 70 | OQ hazard task generation |
| `test_get_oq_disagg_tasks.py` | 44 | Disagg task generation |
| **14 fixture files** | ~850 | Realistic JSON/CSV test data |

**Strengths:**
- Good use of `pytest.mark.parametrize` for combinatorial testing
- Both positive and negative test cases (valid configs and expected validation failures)
- Realistic fixture data (not toy examples)
- Clean `conftest.py` patterns with shared fixtures
- Custom `does_not_raise()` context manager for parameterized pass/fail tests

### Suggestions for Improvement

1. **Test the untested task types** — Inversion and OQ hazard have good validation tests, but these task types appear to lack test coverage:
   - `average_solutions`
   - `coulomb_rupture_sets`
   - `scale_solution`
   - `subduction_rupture_sets`
   - `time_dependent_solution`
   - `rupset_report` / `inversion_report`

   Even basic "valid config loads without error" tests would catch regressions.

2. **Test `ArgSweeper` more thoroughly** — Only 27 lines for the core config loading mechanism. Consider testing:
   - Config files with unknown fields (should fail with `extra='forbid'`)
   - Missing required fields
   - Sweep over empty lists
   - Multiple swept arguments producing the correct cartesian product

3. **Integration/smoke tests** — Current tests validate arguments but don't test the runner → task execution path. Even a mock-based integration test that verifies `JobRunner.run_jobs()` calls the right task with the right args would be valuable.

4. **Test error messages** — Since validation errors are user-facing, consider asserting on the error message content (not just that `ValidationError` is raised). This prevents regressions in error quality.

5. **CI note** — Tests run on `ubuntu/macos/windows` but only Python 3.11. Consider adding 3.10 and 3.12 to the matrix, especially since 3.9 was just dropped.

6. **Fill in `docs/testing.md`** — Even a brief "run `pytest` from the repo root" with notes on fixture organization would help contributors.

---

## 7. Overall Assessment

This is a really well-executed refactor. The codebase went from ~45K lines of scattered, ad-hoc task configuration to ~10K lines of clean, validated, modular code. The architectural choices are sound:

- Pydantic for validation is the right tool for the job
- The per-task package pattern scales well
- The ArgSweeper abstraction cleanly separates config loading from task logic
- The modular CLI is much more discoverable than the old flat scripts

The main areas for follow-up are documentation (particularly validation rules and migration guidance) and extending test coverage to the remaining task types. But the foundation laid here is solid — future contributors will thank you for it.

Nice work! The net -35K lines speaks for itself.
