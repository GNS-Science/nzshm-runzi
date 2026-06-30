# Runzi access-tier least-privilege: substrate vs code

## Decision

Tighten the `terraform/access/` IAM ladder along a **substrate-vs-code** cleavage:

- **Substrate** (IAM tiers, compute environments, job queues, tfstate bucket, capacity) — rare
  changes, account-wide blast radius — is owned by the **deployer** (the 2 god-admins) via
  Terraform.
- **Code** (the runzi image and the job definition pointing at it) — constant changes,
  runzi-only blast radius — is **self-serve** for scientists via the federated tiers.

Concretely:
- **base policy:** drop `M2MSecretRead`. The `toshi-m2m` secret is read by `nshm_toshi_client`
  inside the Batch container (its task/job role), not by human/federated sessions; local auth is
  Cognito-JWT only.
- **batch policy:** unchanged (keep all `BatchSubmit` actions; they support interactive
  monitor/cancel).
- **admin policy:** keep code/publish (ECR push, `RegisterJobDefinition`, `iam:PassRole`); remove
  substrate provisioning (`Create/Update/DeleteComputeEnvironment`, `Create/Update/DeleteJobQueue`);
  drop unused (`ecr:CreateRepository`, `ecr:BatchDeleteImage`, `batch:DeregisterJobDefinition`);
  rename console-editor Sids (`VisualEditor0` → `JobDefPublish`, `VisualEditor1` → `ECRPush`).

**`runzi-admin` is kept, not retired** — it is the federated self-serve release tier that lets
scientists publish code without holding deployer/god-admin credentials.

## Two deciding inputs

1. **Only 2 people hold deployer/god-admin credentials, and scientists must self-serve code
   changes.** Making publishing deployer-only would bottleneck every code experiment behind those
   2 admins. So the publish step (build/push image + register job def) stays on a federated tier.
2. **Provisioning powers don't belong on a broadly-assumable federated role.** The same principle
   that removed `TerraformStateS3` from `runzi-admin` (ADR-0005) applies to compute-env/queue
   admin: these are substrate, done with deployer creds via `terraform/batch/`, never by runzi.

## Consequences / deferred

- Verified before apply: the container job role holds the M2M secret read; the deployer holds the
  removed provisioning actions (see the implementation plan's pre-apply verification gate).
- Resource-scoping refinements (ECR push to `nzshm22/runzi`; `RegisterJobDefinition`/`SubmitJob`
  to specific ARNs) are deferred — some intersect the publish-workflow hardening (#324).
- S3 stage-incorrect ARNs remain (#321); job-def ownership remains CLI-managed and self-serve,
  which this ADR reinforces (#320).

## Files

- `terraform/access/main.tf` — the policy edits.
- `docs/usage/access_tiers.md` — updated ladder description.
- `docs/architecture/adr/0005-runzi-iam-tiers-terraform-migration.md` — this actions its
  "move provisioning perms off the federated runzi roles" and "tidy Sids" followups.
