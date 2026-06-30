# Runzi access-tier permission tightening (#318) — Design

## Context

The `terraform/access/` IAM ladder (`local ⊂ batch ⊂ admin`, see `main.tf`) was migrated
faithfully from `nshm-toshi-api`'s `serverless.yml` (ADR-0005) — drift and all. Issue #318 asks
us to tighten it to least-privilege. Two problems motivate this:

1. **Some grants on the federated user roles aren't user concerns.** The base policy grants
   `secretsmanager:GetSecretValue` for the `toshi-m2m` secret, and the admin policy grants
   Batch **compute-environment** and **job-queue** provisioning — both flagged by ADR-0005 as
   provisioning/machine powers that shouldn't sit on a broadly-assumable Cognito-federated role.
2. **Org constraint:** only **2 people** hold deployer/god-admin AWS credentials, and a core goal
   is that **scientists self-serve code/behaviour changes** (build/push a new image, point a job
   definition at it) **without** bottlenecking on those 2 admins.

**Intended outcome:** each tier grants only what its actor legitimately needs, organized around a
**substrate-vs-code** cleavage — without removing scientists' ability to publish their own code.

## Organizing principle: substrate vs code

| Axis | Changes | Blast radius | Actor | Mechanism |
|---|---|---|---|---|
| **Substrate / infra** | rarely | account-wide | the 2 deployer/god-admins | Terraform |
| **Code / behaviour** | constantly | runzi-only | scientists (self-serve) | runzi CLI + federated tiers |

Substrate = IAM tiers, compute environments, job queues, tfstate bucket, capacity (`maxVcpus`).
Code = the runzi image and the job definition that points at it.

**`runzi-admin` is explicitly KEPT** (not retired): it is the federated *self-serve release tier*
that lets scientists publish code on the **code** axis. We only strip its **substrate** powers.

## Current state (`terraform/access/main.tf`)

- **base**: `ECRRead`, `S3ReadWrite`, `M2MSecretRead`
- **batch** (+): `BatchSubmit` (7 actions: SubmitJob, DescribeJobs, ListJobs, TerminateJob,
  DescribeJobQueues, DescribeComputeEnvironments, DescribeJobDefinitions)
- **admin** (+): `VisualEditor0` (compute-env create/delete/update + Register/DeregisterJobDefinition),
  `VisualEditor1` (ECR push + CreateRepository + BatchDeleteImage), `IAMAdmin` (PassRole),
  `BatchQueueAdmin` (queue create/update/delete)
- **roles**: `local`=base, `batch`=base+batch, `admin`=base+batch+admin (cumulative)

Evidence gathered (code-traced): runzi calls `batch:SubmitJob` (submit path) and
`describe_job_definitions` + `register_job_definition` (only in `build_and_deploy_container.py`);
ECR push via `docker push`; `iam:PassRole` is required by `register_job_definition`. There is
**no** runzi caller of `get_secret`, compute-env/queue admin, `CreateRepository`,
`BatchDeleteImage`, or `DeregisterJobDefinition`.

## Target design

### base policy (inherited by all tiers)
- **KEEP** `ECRRead` (image pull) and `S3ReadWrite` (reports + THS store).
  - *Note:* the S3 ARNs are hardcoded to `-test` buckets regardless of stage — a real bug, but
    tracked separately in **#321**; out of scope here.
- **DROP** `M2MSecretRead`. **[DECIDED]** The `toshi-m2m` secret is read by `nshm_toshi_client`
  *inside the Batch container* (the container's task role), not by human/federated sessions; local
  auth is Cognito-JWT only. This is a machine concern, not a user one.

### batch policy (increment)
- **UNCHANGED** — keep all 7 `BatchSubmit` actions. **[DECIDED]** runzi code only calls
  `SubmitJob`, but the `Describe*`/`List`/`Terminate` actions support scientists monitoring and
  cancelling their own jobs interactively, and are deliberately retained.

### admin policy (increment) — the core change
**KEEP (code / publish — self-serve):**
- ECR push: `InitiateLayerUpload`, `UploadLayerPart`, `CompleteLayerUpload`, `PutImage`,
  `BatchCheckLayerAvailability`, `BatchGetImage` (on `nzshm22/*`)
- `batch:RegisterJobDefinition`
- `iam:PassRole` on `toshi_batch_ECS_TaskExecution`

**REMOVE (substrate → deployer):** **[DECIDED]**
- `batch:CreateComputeEnvironment`, `DeleteComputeEnvironment`, `UpdateComputeEnvironment`
- the entire `BatchQueueAdmin` statement (`batch:CreateJobQueue`, `UpdateJobQueue`,
  `DeleteJobQueue`)

**DROP (unused):** **[DECIDED]**
- `ecr:CreateRepository`, `ecr:BatchDeleteImage` — no runzi caller
- `batch:DeregisterJobDefinition` — no runzi caller

**Sid cleanup:** **[DECIDED]** since these statements are being edited anyway, rename the
console-editor Sids (`VisualEditor0` → `JobDefPublish`, `VisualEditor1` → `ECRPush`). This also
actions the ADR-0005 "tidy console-editor Sids" followup.

## Out of scope (tracked elsewhere)

- S3 stage-incorrect ARNs → **#321**
- Resource-scoping refinements (ECR push to `nzshm22/runzi` not `/*`; `RegisterJobDefinition` to
  the runzi JD name; `SubmitJob` to queue+JD ARNs) — optional future tightening; some intersect
  **#324**.
- Publish-workflow hardening (experimental vs shared JD, promotion) → **#324**
- Job-def ownership (CLI vs Terraform) → **#320**. Note: the self-serve constraint argues
  *against* deployer-gated Terraform for the JD.
- Retiring `runzi-admin` — **explicitly rejected** (would bottleneck scientists behind the 2 admins).

## Prerequisites / verification before apply

1. **Confirm the Batch container task/job role holds `secretsmanager:GetSecretValue` on
   `toshi-m2m-*`** before removing `M2MSecretRead` from base — so batch auth can't break.
2. **Confirm the deployer credential holds the compute-env + queue admin actions** being removed,
   so provisioning isn't stranded. (Deployer is god-admin — almost certainly yes; confirm.)
3. `terraform plan` shows *exactly* the intended diff and nothing else.

## Implementation

- Edit `terraform/access/main.tf` (single-bodied; applies to both stages per ADR-0005).
- Apply per stage with **deployer** creds (test → validate → prod), following
  `terraform/access/README.md` + `MIGRATION_RUNBOOK.md` patterns.
- Write **ADR-0006** recording the substrate-vs-code decision and `runzi-admin` as the kept
  self-serve release tier (per the project's ADR-before-significant-changes convention).

## Verification (end-to-end)

- `terraform plan/apply` diff matches intent: `M2MSecretRead` gone from base; compute-env actions
  + `BatchQueueAdmin` gone from admin; unused actions trimmed; Sids renamed.
- **Self-serve still works:** a `runzi-admin` scientist can still run `runzi utils docker-build`
  (ECR push + register JD succeed).
- **Substrate locked down:** the same scientist gets `AccessDenied` on
  `aws batch create-compute-environment` / `create-job-queue` / `update-compute-environment`.
- **Batch auth intact:** a submitted job still reads the M2M secret via the container's task role.
- **User tiers intact:** `runzi-batch` can submit/monitor/cancel; `runzi-local` can pull image +
  read/write S3.
