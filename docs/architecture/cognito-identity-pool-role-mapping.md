# Cognito Identity Pool role mapping with multiple User Pool groups

## Symptom

Running `runzi --cluster-mode AWS` fails at job submission with:

    ClientError: An error occurred (AccessDeniedException) when calling the SubmitJob
    operation: User: arn:aws:sts::<acct>:assumed-role/toshi-runzi-local-test/
    CognitoIdentityCredentials is not authorized to perform: batch:SubmitJob ...
    because no identity-based policy allows the batch:SubmitJob action

The user *is* in a group whose role allows `batch:SubmitJob`, but the Identity Pool
handed out a *different* role that doesn't.

## Root cause: which IAM role a multi-group user gets

runzi never chooses an IAM role. `nshm_toshi_client.aws.get_aws_session()` calls
`cognito-identity get_id` + `get_credentials_for_identity` with **no `CustomRoleArn`**,
so the role is decided entirely by the **Identity Pool's role-mapping configuration**.

When a user belongs to multiple User Pool groups, two independent mechanisms exist —
and they do **not** combine the way you'd expect:

| Identity Pool "authenticated role selection" | How the role is chosen | Honors group precedence? |
|---|---|---|
| **Use `cognito:preferred_role`** | The single role in the token's `cognito:preferred_role` claim | **Yes** — claim = role of the group with the lowest precedence number |
| **Choose role with rules** | Claim-match rules evaluated **top-down, first match wins** | **No** — `preferred_role` is ignored entirely |

The token also carries `cognito:roles` (all roles from all groups) and `cognito:groups`
(memberships ordered by precedence).

## Two traps that cost real debugging time

1. **The cached `id_token` carries a stale `preferred_role`.**
   `cognito:preferred_role` is baked into the ID token at issuance. runzi reuses the cached
   token from `~/.toshi/credentials` and only refreshes when the *access* token expires
   (`nshm_toshi_client/auth.py:263` — `_get_valid_credentials` refreshes on
   `is_token_expired(access_token)`, then returns the cached `id_token` unchanged).
   Changing group precedence in Cognito does nothing until you mint a new token:
   re-run `toshi-auth login` (a passive wait-for-refresh is not guaranteed to be enough).

2. **Rules mode ignores `preferred_role`.**
   Even with a fresh token whose `preferred_role` is correct, you can still be assigned the
   wrong role if the pool is in "Choose role with rules" mode. Rules are first-match-wins,
   so a rule keyed on a lower-value group (e.g. `cognito:groups contains runzi-local → local
   role`) listed *before* the batch rule wins for anyone in both groups. The tell-tale sign:
   removing the user from the `runzi-local` group makes submission work, while
   `preferred_role` reads as the batch role the whole time.

## How to diagnose

Decode the ID token claims (no signature check needed — the library ships the helper):

    python -c "from nshm_toshi_client.auth import load_credentials, decode_jwt_payload; \
    p = decode_jwt_payload(load_credentials()['id_token']); \
    print('preferred_role:', p.get('cognito:preferred_role')); \
    print('roles:', p.get('cognito:roles')); \
    print('groups:', p.get('cognito:groups'))"

- `preferred_role` wrong → re-login (trap 1), and/or fix group precedence.
- `preferred_role` correct but you still assume the wrong role → the pool is in rules mode
  (trap 2); inspect the rules, not precedence.

## Fixes (Identity Pool console — infra, not this repo)

Cognito → Identity Pools → your pool → User access → **Authenticated role selection**:

- **Preferred (simplest):** set it to **use the role from `cognito:preferred_role`**. Group
  precedence then governs (lowest number wins). Confirm `preferred_role` already points at the
  intended role via the decode command above.
- **If you must keep rules mode:** reorder the rules so the higher-privilege group rule is
  evaluated *before* the lower one, or remove/scope the lower-group rule so it doesn't fire for
  users who are also in the higher group.
- Check the **Role resolution** fallback (Default authenticated role vs. DENY) — this is only
  the no-rule-matched fallback, not the multi-group case above.
- Ensure the target role's **trust policy** allows `cognito-identity.amazonaws.com` to assume it
  with `"cognito-identity.amazonaws.com:amr": "authenticated"`.

## Related

- `docs/architecture/aws-auth-decision.md` — why runzi uses the in-memory Cognito→boto3 path.
- `nshm_toshi_client/aws.py::get_aws_session()` — the federation call (no `CustomRoleArn`).
- `nshm_toshi_client/auth.py:242,263` — `get_id_token()` / cached-token refresh behaviour.
- `runzi/aws/session.py` — wrapper with fallback to the default boto3 chain.
