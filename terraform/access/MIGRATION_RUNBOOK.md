# Migration runbook: hand off the runzi IAM access tiers to Terraform

End-to-end, per-stage runbook for migrating the 6 runzi IAM resources
(`toshi-runzi-{base,batch,admin}` policies + `toshi-runzi-{local,batch,admin}` roles) from
`nshm-toshi-api`'s Serverless/CloudFormation stack into this `terraform/access/` root, **without
deleting the live resources or disrupting any login**.

Each step pairs the **action** with an **AWS-CLI validation gate**. Do not proceed past a gate
that fails. Run the whole thing on **`test` first, validate, then repeat for `prod`.**

Background and rationale: [`ADR-0005`](../../docs/architecture/adr/0005-runzi-iam-tiers-terraform-migration.md).
Cross-repo coordination checklist: `GNS-Science/nshm-toshi-api` issue #353.

---

## Preconditions

- **Deployer-level AWS credentials.** This migration creates/updates IAM and runs `sls deploy`;
  the federated `runzi-admin` session is *not* enough. Confirm you're in the right account:
  ```bash
  aws sts get-caller-identity
  # Account must be 461564345538, and the principal a deployer (not assumed-role/toshi-runzi-*).
  ```
- **Tools:** `aws` CLI v2, `jq`, `terraform >= 1.10`, and the ability to `sls deploy` the
  `nzshm22-toshi-api-<stage>` stack (or coordinate with whoever does — issue #353).
- **Regions:** the CloudFormation stack and the Cognito Identity Pool are in **`ap-southeast-2`**
  (so every `cloudformation` / `cognito-identity` command below passes `--region ap-southeast-2`).
  **IAM is global** — no region on `iam` commands.
- **The stage's Identity Pool ID** (used by the snapshot script and the role trust policies):
  ```bash
  aws cloudformation describe-stacks --stack-name nzshm22-toshi-api-<stage> \
    --region ap-southeast-2 \
    --query "Stacks[0].Outputs[?OutputKey=='IdentityPoolId'].OutputValue" --output text
  ```
  (Or read `NZSHM22_TOSHI_COGNITO_IDENTITY_POOL_ID` from `.env`.) Export it for convenience:
  ```bash
  export STAGE=test
  export POOL_ID="ap-southeast-2:xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
  export ACCOUNT=461564345538
  ```

The validation gates lean on `scripts/snapshot-access-tiers.sh`, which captures the 6 resources +
the Identity Pool role mapping as normalized JSON so you can `diff` two points in time. It is
strictly read-only.

---

## T0 — Baseline (before any change)

**Action:** capture the starting state.
```bash
./scripts/snapshot-access-tiers.sh "$STAGE" "$POOL_ID" baseline
```

**Validate:**
- All 6 resources exist (the snapshot succeeds — it fails loudly if any are missing).
- **The ladder is 1 / 2 / 3** managed policies:
  ```bash
  for t in local batch admin; do
    printf '%s: ' "$t"; jq 'length' "baseline/role-${t}-attached.json"
  done
  # expect: local: 1   batch: 2   admin: 3
  ```
- **The group→role mapping** is intact and most-privileged-first:
  ```bash
  jq '.Roles.authenticated, .RoleMappings' baseline/identity-pool-roles.json
  # authenticated -> .../role/toshi-runzi-local-<stage>
  # rules, in order: runzi-admin -> admin role, runzi-batch -> batch role, runzi-local -> local role
  ```
- **The admin policy does NOT yet contain the queue/state grants** (it gains them only at T2b):
  ```bash
  jq '[.. | .Sid? // empty]' baseline/policy-admin.json
  # expect Sids: BatchAdmin, ECRAdmin  — and NOT TerraformStateS3
  grep -c TerraformStateS3 baseline/policy-admin.json   # expect 0
  ```
- **CloudFormation currently owns all 6:**
  ```bash
  aws cloudformation list-stack-resources --stack-name "nzshm22-toshi-api-${STAGE}" \
    --region ap-southeast-2 \
    --query "StackResourceSummaries[?starts_with(LogicalResourceId,'ToshiRunzi')].LogicalResourceId" \
    --output text
  # expect the 6: ToshiRunziBaseManagedPolicy ToshiRunziBatchManagedPolicy ToshiRunziAdminManagedPolicy
  #               ToshiRunziLocalRole ToshiRunziBatchRole ToshiRunziAdminRole
  ```

---

## Step 1 → T1 — Deploy #1: Retain + de-reference (`nshm-toshi-api`)

**Action:** deploy the already-merged `serverless.yml` changes (issue #353 / PR #354) that add
`DeletionPolicy: Retain` to the 6 resources and re-point the role attachment at their ARNs via
`Fn::Sub`:
```bash
# in the nshm-toshi-api repo
sls deploy --stage "$STAGE"
```

**Validate — behaviour-preserving:**
```bash
./scripts/snapshot-access-tiers.sh "$STAGE" "$POOL_ID" after-deploy1
diff -ru baseline after-deploy1        # expect: NO differences
```
The `Fn::Sub` ARNs equal the prior `!GetAtt` ARNs, so the live policies, roles, and the role
mapping are unchanged.

**Validate — Retain is actually live** (this is the safety gate for the irreversible Step 3; there
is no API that reports a resource's `DeletionPolicy`, so inspect the *deployed* template):
```bash
aws cloudformation get-template --stack-name "nzshm22-toshi-api-${STAGE}" \
  --region ap-southeast-2 --template-stage Processed --query TemplateBody --output json \
  | jq '.Resources | to_entries
        | map(select(.key|startswith("ToshiRunzi")))
        | map({(.key): .value.DeletionPolicy})'
# expect every one of the 6 to show "Retain"
```
**Do not continue to Step 3 unless all 6 show `Retain` here.**

---

## Step 2 → T2 / T2b — Import into Terraform, then apply (`nzshm-runzi`)

**Action (import):** in `terraform/access/`, select the workspace and import the live resources
(see [`README.md`](README.md) for the full command list):
```bash
terraform workspace select "$STAGE"
terraform init
# terraform import aws_iam_policy.runzi_base   arn:aws:iam::$ACCOUNT:policy/toshi-runzi-base-$STAGE
# ... (3 policies, 3 roles) ...
terraform plan
```

**Validate (T2, after import, before apply):**
- `terraform plan` shows **zero changes EXCEPT** the admin policy gaining
  `CreateJobQueue`/`UpdateJobQueue`/`DeleteJobQueue` + the `TerraformStateS3` statement. Those live
  only in Terraform by design (see ADR-0005). Any *other* diff means the HCL doesn't match live —
  fix the HCL, not the live resource.
- Nothing has been applied yet, so the live AWS state is still pristine:
  ```bash
  ./scripts/snapshot-access-tiers.sh "$STAGE" "$POOL_ID" after-import
  diff -ru baseline after-import        # expect: NO differences
  ```

**Action (apply):**
```bash
terraform apply
```

**Validate (T2b, after apply) — exactly one expected change:**
```bash
./scripts/snapshot-access-tiers.sh "$STAGE" "$POOL_ID" after-apply
diff -ru baseline after-apply
# expect: the ONLY differences are in policy-admin.json — the added BatchAdmin queue actions
#         and the new TerraformStateS3 statement. Everything else identical.
grep -c TerraformStateS3 after-apply/policy-admin.json    # expect 1 (now present)
```

---

## Step 3 → T3 — Deploy #2: De-template (`nshm-toshi-api`) — the Retain proof

**Action:** remove the 6 resource definitions from `serverless.yml` and deploy. (Only do this once
T1's Retain gate and T2b were green.)
```bash
# in the nshm-toshi-api repo, after deleting the 6 ToshiRunzi* resources from serverless.yml
sls deploy --stage "$STAGE"
```

**Validate — CloudFormation released them but the live resources survive (Retain worked):**
```bash
# 1) The 6 logical IDs are GONE from the stack:
aws cloudformation list-stack-resources --stack-name "nzshm22-toshi-api-${STAGE}" \
  --region ap-southeast-2 \
  --query "StackResourceSummaries[?starts_with(LogicalResourceId,'ToshiRunzi')].LogicalResourceId" \
  --output text
# expect: empty

# 2) ...but every IAM resource still EXISTS (this pair is the proof):
for t in base batch admin; do
  aws iam get-policy --policy-arn "arn:aws:iam::${ACCOUNT}:policy/toshi-runzi-${t}-${STAGE}" \
    --query 'Policy.Arn' --output text
done
for t in local batch admin; do
  aws iam get-role --role-name "toshi-runzi-${t}-${STAGE}" --query 'Role.Arn' --output text
done
# expect: all 6 ARNs print (no errors)
```

**Validate — the live resources are untouched by the CFN removal:**
```bash
./scripts/snapshot-access-tiers.sh "$STAGE" "$POOL_ID" after-deploy2
diff -ru after-apply after-deploy2     # expect: NO differences
```

> **Tag caveat:** the IAM resources keep their stale `aws:cloudformation:*` tags after Retain —
> Terraform does not strip them. That is expected and harmless; ownership is proven by stack
> membership (above), **not** by tags. Cosmetic tag cleanup is an optional follow-up.

---

## T4 — Final / end-to-end validation

**Config proof — the mapping still resolves to the now-Terraform-owned roles:**
```bash
jq '.Roles.authenticated, .RoleMappings.ToshiProvider.RulesConfiguration.Rules' \
  after-deploy2/identity-pool-roles.json
# default authenticated -> toshi-runzi-local-<stage>
# rules in order: runzi-admin -> admin, runzi-batch -> batch, runzi-local -> local
```

**Live login (optional — where a test user exists in a tier):**
```bash
# as a user who is in the runzi-batch group, for this stage:
toshi-auth login
aws sts get-caller-identity
# expect the assumed role: .../assumed-role/toshi-runzi-batch-<stage>/...
# Functional check: that user can submit a runzi Batch job end-to-end.
```
Spot-check a `runzi-admin` user the same way if available.

**No drift:**
```bash
terraform plan        # expect: no changes
```

---

## Abort / rollback

- **Anything up to and including Step 2 is reversible.** The resources are still CloudFormation-
  owned until Step 3. To back out: `terraform state rm` the imported resources (and/or
  `terraform destroy` is *not* needed — nothing new was created except the admin-policy statements,
  which you can also revert), and leave `serverless.yml` as the owner. No `sls` change is required
  to abort before Step 3.
- **Step 3 (deploy #2) is the point of no easy return** — once the resources are removed from the
  CloudFormation template they are Terraform-owned. Only cross it after T1's Retain gate and T2b
  are both green. If a later `prod` run surfaces a problem, you still have the `test` snapshots and
  this runbook to compare against.
