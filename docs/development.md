# CLI Documentation
The CLI documents are built using `typer` `utils docs`, e.g.
```console
$ typer runzi/cli/runzi_cli.py utils docs > cli.md
```

# Adding New Task Types
Each task type has a directory under `runzi/tasks` where a runner and a task script are defined. The runner defines a child class of `JobRunner` that provides custom behavior to setup the jobs. The task script has a definition of input arguments that is derived from `pydantic.BaseModel`, a default submission arguments member named `default_submission_args` that is a `SubmissionArgs` object, and a script to run the task (which rebuilds a `TaskRuntimeArgs` from the shipped config). Have a look at the existing task types and follow the pattern.

Each task type should be added to the documentation in `docs/usage/example_input_files` and `docs/usage/input`.
