from enum import Enum


class ComputePlatform(Enum):
    EC2 = 10
    Fargate = 20


EC2_CONFIGS = {
    "BL_CONF_0": dict(job_def="BigLever_32GB_8VCPU_JD", job_queue="BigLever_32GB_8VCPU_JQ", mem=30000, cpu=8),
    "BL_CONF_1": dict(job_def="BigLever_32GB_8VCPU_v2_JD", job_queue="BigLever_32GB_8VCPU_v2_JQ", mem=30000, cpu=8),
    "BL_CONF_2": dict(job_def="BigLever_32GB_8VCPU_v2_JD", job_queue="BigLever_16GB_4VCPU_JQ", mem=15000, cpu=4),
    "BL_CONF_3": dict(  # r5.12xlarge or similar
        job_def="BigLeverOnDemandEC2-JD", job_queue="BigLeverOnDemandEC2-job-queue", mem=380000, cpu=48
    ),
    "BL_CONF_16_120": dict(  # r5.12xlarge or similar
        job_def="BigLeverOnDemandEC2-JD", job_queue="BigLeverOnDemandEC2-job-queue", mem=120000, cpu=16
    ),
    "BL_CONF_32_60": dict(
        job_def="BigLeverOnDemandEC2-JD", job_queue="BigLeverOnDemandEC2-job-queue", mem=60000, cpu=32
    ),
    "BL_CONF_16_30": dict(
        job_def="BigLeverOnDemandEC2-JD", job_queue="BigLeverOnDemandEC2-job-queue", mem=30000, cpu=16
    ),
    "BL_CONF_8_20": dict(job_def="BigLeverOnDemandEC2-JD", job_queue="BigLeverOnDemandEC2-job-queue", mem=20000, cpu=8),
    "BL_CONF_32_120": dict(  # r5.12xlarge or similar
        job_def="BigLeverOnDemandEC2-JD", job_queue="BigLeverOnDemandEC2-job-queue", mem=120000, cpu=32
    ),
}
