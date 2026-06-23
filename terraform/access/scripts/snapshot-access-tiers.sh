#!/usr/bin/env bash
#
# snapshot-access-tiers.sh — capture the live state of runzi's 6 IAM access-tier resources
# (3 managed policies + 3 roles) and the Cognito Identity Pool's role mapping for one stage,
# as normalized JSON files, so you can `diff` two snapshots across a migration checkpoint.
#
# READ-ONLY: only `aws sts get-caller-identity`, `aws iam get*/list*`, and
# `aws cognito-identity get-identity-pool-roles`. It never mutates anything.
#
# Usage:
#   ./snapshot-access-tiers.sh <stage> <identity-pool-id> [outdir]
#
# Example (capture a baseline, then a checkpoint, then compare):
#   ./snapshot-access-tiers.sh test "ap-southeast-2:xxxx-..." baseline
#   # ... perform a migration step ...
#   ./snapshot-access-tiers.sh test "ap-southeast-2:xxxx-..." after-deploy1
#   diff -ru baseline after-deploy1     # expect: no differences
#
# The identity pool id for a stage comes from .env's NZSHM22_TOSHI_COGNITO_IDENTITY_POOL_ID or:
#   aws cloudformation describe-stacks --stack-name nzshm22-toshi-api-<stage> \
#     --region ap-southeast-2 \
#     --query "Stacks[0].Outputs[?OutputKey=='IdentityPoolId'].OutputValue" --output text
#
# Prereqs: aws CLI v2, jq. The Cognito Identity Pool lives in ap-southeast-2; IAM is global.

set -euo pipefail

usage() {
  echo "usage: snapshot-access-tiers.sh <stage> <identity-pool-id> [outdir]" >&2
  echo "  identity-pool-id: from .env NZSHM22_TOSHI_COGNITO_IDENTITY_POOL_ID, or the" >&2
  echo "  toshi-api stack output IdentityPoolId (see header comment)." >&2
  exit 2
}

stage="${1:-}"
identity_pool_id="${2:-}"
[ -n "$stage" ] || usage
[ -n "$identity_pool_id" ] || usage

outdir="${3:-snapshot-${stage}-$(date -u +%Y%m%dT%H%M%SZ)}"

# The Identity Pool and the toshi-api CloudFormation stack are deployed in ap-southeast-2.
cognito_region="ap-southeast-2"

account="$(aws sts get-caller-identity --query Account --output text)"

mkdir -p "$outdir"

echo "Snapshotting runzi access tiers: stage=${stage} account=${account} -> ${outdir}/"

# --- Managed policies: the current default version's document ---------------------------------
for tier in base batch admin; do
  policy_arn="arn:aws:iam::${account}:policy/toshi-runzi-${tier}-${stage}"
  default_version="$(aws iam get-policy --policy-arn "$policy_arn" \
    --query 'Policy.DefaultVersionId' --output text)"
  aws iam get-policy-version --policy-arn "$policy_arn" --version-id "$default_version" \
    --query 'PolicyVersion.Document' --output json | jq -S '.' > "${outdir}/policy-${tier}.json"
done

# --- Roles: trust policy + attached managed policies (proves the ladder 1/2/3) ----------------
for tier in local batch admin; do
  role_name="toshi-runzi-${tier}-${stage}"
  aws iam get-role --role-name "$role_name" \
    --query 'Role.AssumeRolePolicyDocument' --output json | jq -S '.' \
    > "${outdir}/role-${tier}-trust.json"
  aws iam list-attached-role-policies --role-name "$role_name" \
    --query 'AttachedPolicies[].PolicyArn' --output json | jq -S 'sort' \
    > "${outdir}/role-${tier}-attached.json"
done

# --- Identity Pool role mapping (default authenticated role + the group->role rules) ----------
aws cognito-identity get-identity-pool-roles \
  --identity-pool-id "$identity_pool_id" --region "$cognito_region" \
  --output json | jq -S '.' > "${outdir}/identity-pool-roles.json"

echo "Done. Snapshot written to ${outdir}/"
echo "Compare two snapshots with:  diff -ru <baseline-dir> ${outdir}"
