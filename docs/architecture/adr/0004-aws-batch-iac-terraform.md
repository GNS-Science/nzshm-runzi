# AWS Batch IaC: Terraform for the compute environment and queue (Phase 1)

## Decision

**runzi adopts Terraform, in this repo, to manage the two genuinely static AWS Batch
resources: the Fargate compute environment and the `BasicFargate_Q` job queue.** State lives
in a dedicated S3 bucket with native S3 locking (`use_lockfile`, Terraform ≥ 1.10); GNS operators
run `terraform apply` from their own machines. There is no CI-driven apply yet.

**The job definition (`Fargate-runzi-opensha-JD`) is explicitly out of scope for this phase** and
stays managed by the existing `runzi utils docker-build` CLI flow. Owning it in Terraform is a
tracked follow-up, not part of this decision.

This actions the IaC followup deferred in
[`0003-aws-batch-compute-consolidation.md`](0003-aws-batch-compute-consolidation.md#followups-not-blocking-this-decision):
*"Adopt infrastructure-as-code (Terraform or AWS CDK) to encode the single compute environment,
job definition, and queue, replacing the console-managed resources."* This ADR narrows that to
compute environment + queue for Phase 1, and explains why.

## Two deciding inputs

1. **The compute environment and queue are the resources with no source of truth.** They were
   hand-created in the AWS console and are documented only in prose (the consolidation ADR and
   `docs/usage/aws_batch.md`). They change rarely — sizing, subnets, security groups — which makes
   them an ideal, low-risk Terraform target: define once, `import` the live resource, and from
   then on `terraform plan` is the drift detector that prose can't be.
2. **The job definition mutates on every deploy, which conflicts with Terraform ownership.**
   `update_job_definition()` (`runzi/cli/build_and_deploy_container.py:140-185`) re-registers a
   new job-definition revision pinned to the freshly-pushed image **digest**
   (`NZSHM22_RUNZI_ECR_DIGEST`) on every `runzi utils docker-build`. If Terraform also owned this
   resource, every deploy would drift Terraform's state and every `terraform apply` would fight
   the CLI's re-registration. The image revision is an *application deployment* concern, not
   static infrastructure — the two need different lifecycles, so this phase only Terraforms the
   side that doesn't change every deploy.

## Background

Before this change, per
[`0003-aws-batch-compute-consolidation.md`](0003-aws-batch-compute-consolidation.md), all three Batch
resources (compute environment, job definition, job queue) were created and changed by hand in
the AWS console, with the ADR and `docs/usage/aws_batch.md` as the only record of their intended
shape. That ADR deferred IaC explicitly rather than block the Fargate consolidation on it.

Other apps in the GNS Batch account (a small number of outliers) may submit to some of the same
generically-named resources (`BasicFargate_Q`), but **runzi is the canonical app for configuring,
launching, and saving Batch jobs**, so this repo is the appropriate home for the Terraform that
manages them — rather than a separate infra repo, which would split the spec
(`docs/usage/aws_batch.md`, the consolidation ADR) from its implementation for no benefit at
runzi's current scale.

### Why Terraform over CDK or CloudFormation

- **Terraform** was chosen primarily because **adopting already-existing, hand-created resources
  is its strongest case**: `terraform import` brings a live resource under management without
  recreating it, and the subsequent `terraform plan` showing zero changes is a clean, verifiable
  proof that the HCL matches reality. CDK and CloudFormation can import too, but through stacks,
  which is a heavier unit than importing two standalone resources.
- It is not AWS-only (no lock-in if the account strategy changes), and its declarative HCL is a
  reasonable size for two resources without needing a general-purpose language (CDK's main
  selling point, infra-as-Python, isn't a strong pull for a stack this small).
- The trade-off accepted: Terraform requires managing its own state, unlike CloudFormation, which
  AWS tracks for you. See the state backend decision below.

### Why an S3 backend, not local state

A local state file is the lowest-friction option but assumes exactly one operator forever, and
that file must never be lost or it's recreate-or-reimport. Because more than one GNS operator may
run `terraform apply` over time, state needs to be shared and lockable. AWS's S3 backend with
native locking (`use_lockfile = true`, no DynamoDB table required on Terraform ≥ 1.10) is the
standard, lowest-overhead way to do that. The state bucket itself is a one-time, out-of-band
bootstrap (created once, the same way the Batch resources exist today) — accepted as the one
chicken-and-egg step in adopting Terraform at all.

CI-driven apply (GitHub Actions) was considered and explicitly deferred: it would require giving
this app repo's CI AWS deploy credentials, which is a larger blast-radius change than this phase
needs while there's no apply automation pressure yet.

## Consequences / deferred obligations

Because this is Phase 1, the following are explicit, tracked gaps rather than oversights:

- **The job definition's structure (IAM role, `platformCapabilities`, env vars, sizing) remains
  uncodified**, living only in whatever revision the CLI last registered plus the prose in
  `docs/usage/aws_batch.md`. This is the same gap the consolidation ADR already accepted for that
  resource; Phase 1 does not close it.
- **Discovering and importing the live compute-environment and queue config requires AWS
  console/CLI access** (exact compute-environment name, `maxVcpus`, subnets, security groups,
  queue priority) that must be gathered by an operator with credentials before `terraform import`
  can run. See `terraform/batch/README.md` for the discovery commands.
- **The S3 state bucket is a manual, out-of-band resource** (not Terraform-managed, for the
  obvious bootstrap reason) until/unless a future change brings it under a higher-level
  bootstrap stack.
- **No CI apply.** All `terraform apply` runs are manual, from an operator's machine, until a
  follow-up decision adds automation.
- **Run with deployer-level credentials, not the federated `runzi-admin` session.** Provisioning
  the compute environment + queue is a deployer/devops activity — same posture as
  `terraform/access/`. The `runzi-admin` access tier does **not** hold Terraform-state access
  (removed in PR #315 per ADR-0005's least-privilege followup), so it cannot run this root in any
  case. Use the same deployer credentials that run `sls deploy` / `terraform/access/`.

## Followups not blocking this decision

- **Own the job definition in Terraform.** Once this phase is proven, decide between (a) leaving
  it CLI-managed permanently, or (b) bringing it under Terraform with the image digest as a
  `terraform apply -var` input, with the CLI driving that apply so deploys stay one command. This
  is a larger change to `build_and_deploy_container.py` and deserves its own review.
- **Retire `BigLever_32GB_8VCPU_v2_*`** (the consolidation ADR's pending manual cleanup) — done by
  hand in the console, not via Terraform, since we don't import resources slated for deletion.
- **CI-driven `terraform apply`**, if/when operators want deploys automated — needs a decision on
  granting AWS credentials to this repo's CI.
- **Bring the state bucket itself under IaC** (e.g. a tiny bootstrap module) if a second Terraform
  root ever needs the same backend.

## Files

- `docs/architecture/adr/0003-aws-batch-compute-consolidation.md` — the prior ADR this one actions
  the IaC followup of.
- `docs/usage/aws_batch.md` — updated to describe the Terraform-managed resources and link the
  runbook.
- `terraform/batch/` — the new Terraform root: `versions.tf`, `backend.tf`, `providers.tf`,
  `variables.tf`, `main.tf`, and `README.md` (operator runbook: discovery commands, state bucket
  bootstrap, init/import/plan/apply workflow).
- `runzi/arguments.py` — `DEFAULT_JOB_QUEUE` / `DEFAULT_JOB_DEFINITION` remain the names Terraform
  must match; unchanged by this phase.
- `runzi/cli/build_and_deploy_container.py` — unchanged by this phase; remains the sole owner of
  the job definition's image revision.
