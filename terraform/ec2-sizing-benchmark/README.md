# EC2 sizing benchmark — ephemeral pinned compute environments (#323 and future benchmarks)

Stands up **one On-Demand EC2 compute environment + queue per instance type**, so a family comparison
can run all types from a single `terraform apply` and be removed with one `terraform destroy` — instead
of re-pinning `terraform/batch`'s shared `runzi-ec2-CE` and applying once per family. Each CE is pinned
to a single instance type; `min_vcpus = 0` so idle CEs cost nothing.

The **resources are ephemeral** (apply before a benchmark, destroy after), but the **state lives in S3**
(`backend.tf`, key `benchmark/ec2-sizing.tfstate`, shared bucket with `terraform/batch`/`access`). That
makes `terraform destroy` reliable even from a different machine and lets concurrent runs lock safely —
it does **not** mean the resources are long-lived. The module is task-agnostic (just a list of instance
types), so it's reusable for benchmarking any task type; the workload-specific bits live in
`scripts/ec2_sizing/`.

## Stand up

```bash
cd terraform/ec2-sizing-benchmark
cp terraform.tfvars.example terraform.tfvars   # fill role/subnets/SG from terraform/batch's live values
terraform init
terraform apply                                # creates 6 CEs + 6 queues (default set)
terraform output queues                        # instance_type -> queue name
```

Deployer credentials are required (creating Batch compute environments/queues), same posture as
`terraform/batch`.

## Run the benchmark (per family, 8 vCPU, exact-fit → one job per instance)

Constant memory (`--memory-mb 14000`) fits the smallest family instance (c6i.2xlarge = 16 GiB) so heap
is held constant across families and isolates the CPU family. Repeat per queue from `terraform output`:

```bash
uv run python scripts/ec2_sizing/submit_matrix.py \
    --vcpus 8 --memory-mb 14000 --replicates 5 \
    --job-queue ec2sizing-c6i-2xlarge-Q --manifest scratch/c6i.json
# ...then m6i.2xlarge, r6i.2xlarge, c6a/m6a/r6a queues, each to its own manifest.

# Collect each once its jobs finish — pass the pinned type via --instance-type (see note below):
uv run python scripts/ec2_sizing/collect_results.py --manifest scratch/c6i.json --csv scratch/c6i.csv \
    --queues ec2sizing-c6i-2xlarge-Q --instance-type c6i.2xlarge
```

**Always pass `--instance-type` for a pinned run.** The collector's default is to resolve the instance
type from Batch→ECS→EC2, but that only works while the container instances are still registered — with
`min_vcpus = 0` the CE scales to zero after the jobs finish and ECS deregisters the instances
(`describe_container_instances` then returns `MISSING`), so cost would go blank. Since the type is
*known* (you pinned it), `--instance-type` prices it directly and is immune to scale-down. Prices come
from `INSTANCE_SPECS` in `collect_results.py` — refresh the AMD (c6a/m6a/r6a) values before trusting them.

## Tear down

```bash
terraform destroy      # removes all benchmark CEs + queues
```

Nothing else references these resources, so destroy is clean. (The shared `runzi-ec2-CE` is untouched
throughout — this module never modifies it.) Because state is in S3, `destroy` works from any machine
with bucket + deployer access — it doesn't depend on whoever ran `apply` keeping a local state file.

## State & concurrent benchmarks

State lives in S3 (`backend.tf`) under `benchmark/ec2-sizing.tfstate`, lock-protected. To run **two
benchmarks at once** (e.g. inversions and OQ hazard), don't fork the module — partition state with a
Terraform **workspace** (same approach `terraform/access` uses for stages):

```bash
terraform workspace new hazard   # separate state under the same key; `select` to switch back
terraform apply                  # add e.g. -var 'name_prefix=ec2sizing-haz' to avoid resource-name clashes
```

Default (`terraform workspace select default`) is fine for a single benchmark at a time.
