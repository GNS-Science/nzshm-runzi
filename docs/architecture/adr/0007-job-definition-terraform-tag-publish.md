# Job definitions under Terraform via floating image tags; tag-based self-serve publish

## Decision

**Bring the Batch job definitions under Terraform (`terraform/batch/`) by pointing them at a stable
image *tag* instead of a pinned image *digest*, and split publishing into a self-serve image push
(experimental) and a deliberate promote (prod).** This resolves the job-definition ownership
question deferred by [0004](0004-aws-batch-iac-terraform.md) (#320) and hardens the publish workflow
(#324) in a single decision.

Concretely:

- **Two Terraform-managed job definitions**, both static substrate:
  - `runzi-fargate-JD` (prod) → `containerProperties.image = <ecr>/nzshm22/runzi:prod`
  - `runzi-fargate-experimental-JD` → `<ecr>/nzshm22/runzi:experimental`

  These are **new** definitions (not the old `Fargate-runzi-opensha-JD`), so the change is a clean
  create + retirement rather than an in-place mutation of the live prod resource, and adopts a
  tidier `runzi-fargate-*` scheme. They codify the previously-uncodified structure (task-execution
  role, `platformCapabilities`, env, sizing) that ADR-0004 left living only in the last-registered
  revision.

- **`runzi utils docker-build` no longer registers a job definition.** It builds, pushes the
  immutable `runzi-<hash>_py…_oq-…` version tag, and moves the `:experimental` floating tag onto
  that same digest. `update_job_definition()` is deleted. Because the experimental JD tracks the
  `:experimental` *tag*, it picks up the new image on the next job start with **no re-registration**.

- **A new `runzi utils promote` command** retags an existing digest (a version tag, or whatever
  `:experimental` currently resolves to) onto the `:prod` tag — an ECR manifest re-tag, no rebuild.
  This is the only way the shared prod surface changes: a deliberate, named, CloudTrail-logged
  action rather than a silent side effect of every build.

- **`runzi-admin` sheds `batch:RegisterJobDefinition` and the `iam:PassRole`** it only held to embed
  the task-execution role at registration time. Scientists no longer register job definitions at
  all; they push image content. This refines [0006](0006-runzi-access-tier-least-privilege.md)'s
  substrate-vs-code cleavage — the JD *shape* (including which tag it tracks) is now substrate,
  owned by the deployer via Terraform; the image *content under a tag* is code, self-serve via ECR
  push.

`:latest` is retired — `:experimental` and `:prod` are the only floating tags, removing the
ambiguity #324 calls out. The default job definition (`DEFAULT_JOB_DEFINITION`, `runzi/arguments.py`)
is repointed to `runzi-fargate-JD`; scientists target the experimental JD via the existing
`sys_arg_overrides.ecs_job_definition` config mechanism (no new CLI flag yet — see Followups).

## Two deciding inputs

1. **The only reason ADR-0004 kept the JD out of Terraform was that it mutates on every deploy.**
   `update_job_definition()` re-registered a new revision pinned to the freshly-pushed image
   **digest** on every `docker-build`, which would drift Terraform's state and fight every apply.
   That conflict is entirely a consequence of the JD pinning the *digest*. Point the JD at a *tag*
   the build moves instead, and the JD stops changing on deploy — it becomes exactly the kind of
   rarely-changing, console-born resource ADR-0004 found ideal for Terraform. The reframing doesn't
   work *around* ADR-0004's reasoning; it removes the precondition that reasoning rested on.

2. **Publishing must stay self-serve, but the shared prod surface must stop changing by accident.**
   Only 2 people hold deployer/god-admin credentials, and scientists must self-serve code changes
   (#318 / [0006](0006-runzi-access-tier-least-privilege.md)) — so gating publish behind Terraform
   for *every* code experiment is a non-starter. Separating an `:experimental` tag (the zero-thought
   default `docker-build` target) from a `:prod` tag (changed only by an explicit `promote`) gives
   isolation without a principal bottleneck: experimentation can't touch prod by default, and
   promotion is self-serve but deliberate and audited.

## Background

Before this change, all three Batch resources were console-born; ADR-0003 consolidated compute and
ADR-0004 brought the compute environment + queue under Terraform but **explicitly deferred the job
definition** because it mutated every deploy. ADR-0004's "Followups" framed the open choice as
(a) leave the JD CLI-managed permanently, or (b) bring it under Terraform with the image digest
passed as a `-var`, with the CLI driving the apply. This ADR takes a third path neither option
anticipated: bring the JD under Terraform but make the image reference a **tag**, so the CLI never
needs to drive a Terraform apply *or* re-register the JD — the two lifecycles (static JD shape vs.
moving image content) are cleanly separated by the indirection of the tag.

### Why one ECR repo and two floating tags (not two repos)

A single repo (`nzshm22/runzi`) carrying `:experimental` and `:prod` tags is the minimum mechanism.
Two repos would let ECR IAM scope *push-to-prod* separately from *push-to-experimental* (ECR
conditions on repository, not tag), but actually reducing blast radius that way needs a *different
principal* to hold prod-push — which rebuilds the 2-admin bottleneck this ADR exists to avoid. At
this scale the honest control on prod promotion is **intent + CloudTrail audit** (a deliberate
`promote` command, logged with the principal), not an IAM principal split. Two repos remain the
upgrade path if a genuine prod-push principal is ever wanted; nothing here blocks that move.

### Auditability under floating tags

Floating tags don't cost the git-hash audit trail, because an ECR digest can carry multiple tags.
`docker-build` keeps pushing the immutable `runzi-<hash>_py…_opensha-…_oq-…` version tag and *also*
moves `:experimental` onto that same digest; `promote` moves `:prod` onto an existing digest. So
"what is running in prod right now?" resolves `:prod` → digest → the version tag sharing that digest
→ the git hash. Each tag move is a CloudTrail `PutImage` event carrying the principal — arguably a
better record than JD revision history. To keep per-job reproducibility, runzi resolves the selected
JD's tag → concrete digest at submit time and records it in toshi provenance
(`NZSHM22_RUNZI_ECR_DIGEST`), so a job pins exactly which digest it ran even though the JD names only
a tag.

## Consequences / deferred obligations

- **The ECR repo `nzshm22/runzi` must allow mutable tags** for the `:experimental`/`:prod` scheme to
  work. If image-tag immutability is ever required, the two-repo copy model (above) is the fallback.
- **Cutover is ordered and partly deployer-run** (see Followups for who runs what): seed `:prod` and
  `:experimental` from the current live digest → `terraform apply` the two new JDs →
  merge the runzi-side CLI/arguments change → drop the IAM perms → retire the old
  `Fargate-runzi-opensha-JD` by hand once nothing resolves it (the same manual deregistration
  ADR-0004 uses for deleted Batch resources).
- **The `:prod`/`:experimental` tags must exist before the JDs are applied**, or the JDs reference a
  non-existent image. Seeding (step 1) is a one-time manual ECR retag of the current live image.
- **No IAM gate on prod promotion** — by deliberate choice (deciding input 2). `promote` is
  self-serve; its control is audit, not authorization. Revisit if a prod-push principal is ever
  introduced.

## Followups not blocking this decision

- **Ergonomic `--experimental` flag.** Job definitions and compute environments are in flux (an EC2
  option is coming). Until they settle, experimental submission uses the existing
  `sys_arg_overrides.ecs_job_definition` override; add a top-level `--experimental` flag on the run
  commands once the JD/compute-env set is stable (flags over subcommands, per existing CLI design).
- **Deployer coordination for cutover.** The `terraform apply` of the two new JDs, the
  `terraform/access/` IAM tightening, and the retirement of the old JD are deployer-credentialed
  steps (same posture as ADR-0004/0005) run alongside the runzi merge — tracked in #320/#324.
- **Two-repo promotion** if prod-push ever needs a separate principal (above).

## Files

- `terraform/batch/main.tf`, `variables.tf`, `outputs.tf`, `README.md` — the two new
  `aws_batch_job_definition` resources (image as tag) and operator runbook.
- `runzi/cli/build_and_deploy_container.py` — `update_job_definition()` removed; `tag_and_push_image`
  pushes the version tag + `:experimental`; new `promote` command. `runzi/cli/utils_cli.py` wires it.
- `runzi/arguments.py` — `DEFAULT_JOB_DEFINITION` repointed to `runzi-fargate-JD`; experimental JD
  name constant added.
- `runzi/automation/local_config.py`, `runzi/build_tasks.py`, `runzi/aws/aws.py` — submit-time
  resolution of the JD's image tag → digest for toshi provenance.
- `terraform/access/main.tf` — drop `JobDefPublish` (`batch:RegisterJobDefinition`) and `IAMAdmin`
  (`iam:PassRole`) from `runzi_admin`. `docs/usage/access_tiers.md` updated.
- `docs/usage/aws_batch.md`, `docs/usage/docker/` — two JDs, tag scheme, promote workflow.
- [0004](0004-aws-batch-iac-terraform.md) — its job-definition deferral is **superseded** by this
  ADR (status note added there). [0006](0006-runzi-access-tier-least-privilege.md) — its deferred
  publish resource-scoping is actioned here.
