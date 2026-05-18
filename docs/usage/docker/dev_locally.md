# Developing runzi inside the Docker container

Some tasks (OpenQuake hazard, disaggregation) require dependencies baked into the Docker image — Java 11, the OpenSHA fat-jar, and OpenQuake. When working on those tasks you want code changes on the host to take effect immediately, without rebuilding the image.

## 1. Build the dev image (once, or when deps change)

```bash
runzi utils docker-build --dev \
  --fatjar-tag <fatjar_tag> \
  --oq-version <oq_version> \
  --runzi-gitref <branch-or-commit>
```

This builds `runzi-build:dev` locally. It does **not** push to ECR or update the AWS Batch job definition. The `FATJAR_TAG`, `OQ_VERSION`, and `PYTHON_VERSION` values from your `.env` are picked up automatically if present.

Rebuild whenever you change a dependency (openquake version, fatjar, nzshm-model, etc.). Pure Python changes to the `runzi/` source do **not** require a rebuild.

## 2. Run with live host source

Add `--docker-dev` to any normal `runzi` invocation. The wrapper automatically bind-mounts your local `runzi/` source over the copy baked into the image, so every Python edit takes effect immediately:

```bash
runzi --docker-dev hazard oq-hazard /path/to/config.json
```

The dev image installs runzi as an editable package pointing at `/app/nzshm-runzi`. The wrapper mounts your host repo there, so every import resolves to your live files.

## 3. Debugging with pdb

Drop a `breakpoint()` anywhere in the host source, then run the command above. `--docker-dev` allocates an interactive TTY so pdb takes over the terminal when the breakpoint is hit.

For an interactive shell instead of a one-shot command:

```bash
runzi --docker-shell --docker-dev
```

(Combining `--docker-shell` and `--docker-dev` drops into bash with the dev image and source mount active.)

Or equivalently with a raw docker run:

```bash
docker run --rm -it --entrypoint bash \
  -v /path/to/nzshm-runzi:/app/nzshm-runzi \
  ... (same volumes and --env-file) \
  runzi-build:dev
```

Then inside the container: `runzi hazard oq-hazard /INPUT_FILES/config.json`.

## Notes

- The bind-mount overrides only the `runzi` package. All other deps (OpenSHA, OpenQuake, Java, nzshm-model) remain as built into the image.
- `PYTHONDONTWRITEBYTECODE=1` is set in the dev image so the container does not write root-owned `__pycache__/` directories into your host repo.
- The `.env` file in your working directory is loaded automatically by both the wrapper and runzi itself (via python-dotenv).
- The source path is auto-derived from `runzi.__file__` so you do not need to specify it — just run `runzi --docker-dev` from any directory.
