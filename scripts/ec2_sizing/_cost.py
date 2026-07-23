"""Shared cost primitives for the EC2 sizing benchmarks (#323).

The EC2 On-Demand price table and the fair-share cost formula are task-agnostic, so both the crustal
inversion collector (``collect_results.py``) and the coulomb rupture-set collector
(``collect_coulomb_results.py``) import them from here — one price table, no drift.

Cost is analytical, not raw billing: a benchmark under-packs instances, so we charge each job only for
the vCPUs it requested — ``(instance $/hr / instance vCPU) x job vCPU x wall-hours`` — the cost it would
carry on a fully-packed production instance.
"""

from __future__ import annotations

from typing import Any

# EC2 On-Demand price table, us-east-1, Linux: (vcpu, usd_per_hour). AWS Batch "optimal" resolves to
# CURRENT-gen C/M/R families (a pilot landed on m6i.xlarge), not the legacy C4/M4/R4, so the modern
# generations are covered here; the older ones are kept as a harmless fallback. Prices are APPROXIMATE —
# REFRESH from the AWS pricing page before trusting cost figures. Instances not listed leave cost blank
# and trigger a warning (add them here). last verified: 2026-07
INSTANCE_SPECS: dict[str, tuple[int, float]] = {
    # general purpose (M)
    'm6i.large': (2, 0.096),
    'm6i.xlarge': (4, 0.192),
    'm6i.2xlarge': (8, 0.384),
    'm6i.4xlarge': (16, 0.768),
    'm6i.8xlarge': (32, 1.536),
    'm6i.12xlarge': (48, 2.304),
    'm6i.16xlarge': (64, 3.072),
    'm5.large': (2, 0.096),
    'm5.xlarge': (4, 0.192),
    'm5.2xlarge': (8, 0.384),
    'm5.4xlarge': (16, 0.768),
    'm5.8xlarge': (32, 1.536),
    'm5.12xlarge': (48, 2.304),
    'm5.16xlarge': (64, 3.072),
    # compute optimized (C)
    'c6i.large': (2, 0.085),
    'c6i.xlarge': (4, 0.170),
    'c6i.2xlarge': (8, 0.340),
    'c6i.4xlarge': (16, 0.680),
    'c6i.8xlarge': (32, 1.360),
    'c6i.12xlarge': (48, 2.040),
    'c6i.16xlarge': (64, 2.720),
    'c5.large': (2, 0.085),
    'c5.xlarge': (4, 0.170),
    'c5.2xlarge': (8, 0.340),
    'c5.4xlarge': (16, 0.680),
    'c5.9xlarge': (36, 1.530),
    'c5.12xlarge': (48, 2.040),
    'c5.18xlarge': (72, 3.060),
    'c5.24xlarge': (96, 4.080),
    # memory optimized (R)
    'r6i.large': (2, 0.126),
    'r6i.xlarge': (4, 0.252),
    'r6i.2xlarge': (8, 0.504),
    'r6i.4xlarge': (16, 1.008),
    'r6i.8xlarge': (32, 2.016),
    'r6i.12xlarge': (48, 3.024),
    'r6i.16xlarge': (64, 4.032),
    'r5.large': (2, 0.126),
    'r5.xlarge': (4, 0.252),
    'r5.2xlarge': (8, 0.504),
    'r5.4xlarge': (16, 1.008),
    'r5.8xlarge': (32, 2.016),
    'r5.12xlarge': (48, 3.024),
    'r5.16xlarge': (64, 4.032),
    # AMD (c6a/m6a/r6a) — same x86 arch as the Intel i-variants, ~10% cheaper (Phase 2 comparison)
    'c6a.large': (2, 0.0765),
    'c6a.xlarge': (4, 0.153),
    'c6a.2xlarge': (8, 0.306),
    'c6a.4xlarge': (16, 0.612),
    'c6a.8xlarge': (32, 1.224),
    'c6a.12xlarge': (48, 1.836),
    'c6a.16xlarge': (64, 2.448),
    'c6a.24xlarge': (96, 3.672),
    'c6a.32xlarge': (128, 4.896),  # Batch packed a 64-vCPU benchmark job here (#344); per-vCPU rate size-independent
    'm6a.large': (2, 0.0864),
    'm6a.xlarge': (4, 0.1728),
    'm6a.2xlarge': (8, 0.3456),
    'm6a.4xlarge': (16, 0.6912),
    'm6a.8xlarge': (32, 1.3824),
    'm6a.12xlarge': (48, 2.0736),
    'm6a.16xlarge': (64, 2.7648),
    'm6a.24xlarge': (96, 4.1472),
    'm6a.32xlarge': (128, 5.5296),  # Batch may pack a 64-vCPU benchmark job here; per-vCPU rate matches the 16xlarge
    'r6a.large': (2, 0.1134),
    'r6a.xlarge': (4, 0.2268),
    'r6a.2xlarge': (8, 0.4536),
    'r6a.4xlarge': (16, 0.9072),
    'r6a.8xlarge': (32, 1.8144),
    'r6a.12xlarge': (48, 2.7216),
    'r6a.16xlarge': (64, 3.6288),
    # legacy fallback (pre-current-gen "optimal")
    'c4.xlarge': (4, 0.199),
    'c4.2xlarge': (8, 0.398),
    'c4.4xlarge': (16, 0.796),
    'm4.xlarge': (4, 0.200),
    'm4.2xlarge': (8, 0.400),
    'm4.4xlarge': (16, 0.800),
    'r4.xlarge': (4, 0.266),
    'r4.2xlarge': (8, 0.532),
    'r4.4xlarge': (16, 1.064),
}


def duration_seconds(summary: dict[str, Any]) -> float | None:
    """Wall seconds from a Batch JobSummary's epoch-millis timestamps, or ``None`` if not both present."""
    started, stopped = summary.get('startedAt'), summary.get('stoppedAt')
    if started is None or stopped is None:
        return None
    return max(0.0, (stopped - started) / 1000.0)


def job_cost_usd(instance_type: str | None, job_vcpu: int, seconds: float | None) -> float | None:
    """Fair-share cost = (instance $/hr / instance vCPU) x job vCPU x hours; ``None`` if unpriceable."""
    if instance_type is None or seconds is None or instance_type not in INSTANCE_SPECS:
        return None
    instance_vcpu, usd_per_hour = INSTANCE_SPECS[instance_type]
    return (usd_per_hour / instance_vcpu) * job_vcpu * (seconds / 3600.0)
