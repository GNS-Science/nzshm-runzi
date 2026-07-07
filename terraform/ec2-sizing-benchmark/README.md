# EC2 sizing benchmark — throwaway pinned compute environments (#323 Phase 2)

Stands up **one On-Demand EC2 compute environment + queue per instance type**, so the family
comparison can run all types from a single `terraform apply` and be removed with one `terraform
destroy` — instead of re-pinning `terraform/batch`'s shared `runzi-ec2-CE` and applying once per
family. Each CE is pinned to a single instance type; `min_vcpus = 0` so idle CEs cost nothing.

This is **throwaway infra with local state** — not part of the managed `terraform/batch` module.

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

# Collect each once its jobs finish:
uv run python scripts/ec2_sizing/collect_results.py --manifest scratch/c6i.json --csv scratch/c6i.csv
```

The collector reads back the actual instance type per job (it will match the pinned type) and prices it
from `INSTANCE_SPECS` in `collect_results.py` — add any AMD (c6a/m6a/r6a) prices there before trusting
their cost columns.

## Tear down

```bash
terraform destroy      # removes all benchmark CEs + queues
```

Nothing else references these resources, so destroy is clean. (The shared `runzi-ec2-CE` is untouched
throughout — this module never modifies it.)
