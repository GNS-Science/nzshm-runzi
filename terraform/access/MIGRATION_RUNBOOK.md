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

> **Namespace snapshots by stage** so test and prod don't overwrite each other: pass an outdir
> like `SNAPSHOTS/$STAGE/baseline` (the 3rd arg is the literal directory). The examples below
> write to `baseline`, `after-apply`, etc. for brevity — prefix them with `SNAPSHOTS/$STAGE/` in
> practice, and `diff` the matching pair (e.g. `diff -ru SNAPSHOTS/$STAGE/baseline
> SNAPSHOTS/$STAGE/after-apply`).

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
- **The admin policy does NOT yet contain the queue grant** (it gains `BatchQueueAdmin` only at
  T2b). Don't assume specific Sids — the live policy may be console-edited (the test stage had
  `VisualEditor0/1` + `IAMAdmin`, not the `serverless.yml` names). Just confirm the addition is
  absent:
  ```bash
  grep -c CreateJobQueue baseline/policy-admin.json   # expect 0
  jq '[.. | .Sid? // empty]' baseline/policy-admin.json # eyeball what IS there (it's your
                                                        # reconciliation source at T2 — see Step 2)
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

**Action (import):** in `terraform/access/`, init the backend, select the workspace, and import
the live resources (see [`README.md`](README.md) for the full command list). **`terraform init`
must come first** — workspace commands need the backend initialised — and a stage's **first** run
needs `workspace new`, not `select`:
```bash
terraform init                  # initialise the S3 backend FIRST
terraform workspace new "$STAGE" # first time for this stage (use `select` on later runs)
# terraform import aws_iam_policy.runzi_base   arn:aws:iam::$ACCOUNT:policy/toshi-runzi-base-$STAGE
# ... (3 policies, 3 roles) ...
terraform plan
```

**Validate (T2, after import, before apply) — RECONCILE main.tf TO LIVE:**
- The goal is a `terraform plan` showing **only** the intended addition: the admin policy
  gaining a `BatchQueueAdmin` statement (`batch:CreateJobQueue/UpdateJobQueue/DeleteJobQueue`),
  authored only in Terraform — see ADR-0005.
- **Expect the first plan to show MORE than that.** The live resources can have **drifted from
  `serverless.yml`** (the test stage was hand-edited in the console — different Sids, extra
  `iam:PassRole`, an `nzshm22/*` ECR scope, a `STAGE` tag, and the M2M secret ARN in
  `ap-southeast-2` not `us-east-1`). `main.tf` was modelled on `serverless.yml`, so it will NOT
  match.
- **When it doesn't match, fix `main.tf` to mirror LIVE — never change the live resource to match
  the HCL.** The authoritative "live" is your **baseline snapshot** (`baseline/policy-*.json`,
  `role-*-*.json`): reproduce each live statement verbatim, then append only the two intended
  addition. Re-run `terraform plan` and iterate until the only diff is that one addition. (See
  the worked example in ADR-0005 "Consequences" — this is per-stage; prod's drift may differ.)
- Nothing has been applied yet, so the live AWS state is still pristine:
  ```bash
  ./scripts/snapshot-access-tiers.sh "$STAGE" "$POOL_ID" after-import
  diff -ru baseline after-import        # expect: NO differences
  ```

**Action (apply) — apply the saved, reviewed plan:**
```bash
terraform plan -out=tfplan   # same result as the review plan above, saved to a file
terraform apply tfplan       # applies EXACTLY that plan — no re-evaluation in between
rm tfplan                    # gitignored, but clean it up
```
For an auth-critical change, applying a saved plan guarantees `apply` does exactly what you
reviewed (nothing can drift between plan and apply).

**Validate (T2b, after apply) — exactly one expected change:**
```bash
./scripts/snapshot-access-tiers.sh "$STAGE" "$POOL_ID" after-apply
diff -ru baseline after-apply
# expect: the ONLY difference is in policy-admin.json — the added BatchQueueAdmin statement
#         (the queue actions). Everything else identical.
grep -c BatchQueueAdmin after-apply/policy-admin.json    # expect 1 (now present)
```

---

## Step 3 → T3 — Deploy #2: De-template (`nshm-toshi-api`) — the Retain proof

**Action:** drop the 6 resources from THIS stage's CloudFormation stack and deploy. (Only do this
once T1's Retain gate and T2b were green.)

⚠️ **`serverless.yml` is shared across stages.** Do **not** delete the 6 resource definitions
outright — that would also remove them from un-migrated stages' templates, and the next
`sls deploy --stage <other>` (even for an unrelated change) would drop them from that stack
(`Retain` → orphaned, since that stage isn't Terraform-managed yet). Instead, exclude them **only
for this stage**, keeping the definitions for the others. Use the existing `serverlessIfElse`
block:
```yaml
  serverlessIfElse:
      - If: '"${self:custom.stage}" == "test"'   # the stage being migrated
        Exclude:
          # ... existing entries ...
          - resources.Resources.ToshiRunziBaseManagedPolicy
          - resources.Resources.ToshiRunziBatchManagedPolicy
          - resources.Resources.ToshiRunziAdminManagedPolicy
          - resources.Resources.ToshiRunziLocalRole
          - resources.Resources.ToshiRunziBatchRole
          - resources.Resources.ToshiRunziAdminRole
```
(Note: use the correct `resources.Resources.` path — an existing entry has a stale `resourcee`
typo. The `ToshiIdentityPool*` / groups are NOT excluded; the role attachment already references
the role ARNs by `Fn::Sub` string, so excluding the role resources leaves no dangling `!Ref`.)
```bash
# in the nshm-toshi-api repo, with the stage-conditional exclusions added:
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
