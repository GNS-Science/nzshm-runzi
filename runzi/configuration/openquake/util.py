from enum import Enum
from typing import Any, Dict, Generator


class ComputePlatform(Enum):
    EC2 = 10
    Fargate = 20


EC2_CONFIGS = {
    "BL_CONF_0": dict(job_def="BigLever_32GB_8VCPU_JD", job_queue="BigLever_32GB_8VCPU_JQ", mem=30000, cpu=8),
    "BL_CONF_1": dict(job_def="BigLever_32GB_8VCPU_v2_JD", job_queue="BigLever_32GB_8VCPU_v2_JQ", mem=30000, cpu=8),
    "BL_CONF_2": dict(job_def="BigLever_32GB_8VCPU_v2_JD", job_queue="BigLever_16GB_4VCPU_JQ", mem=15000, cpu=4),
    "BL_CONF_0": dict(  # r5.12xlarge or similar
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


def unpack_keys(d: Dict[str, Any]) -> list[str]:
    keys = []
    for k1, v in d.items():
        for k2 in v.keys():
            keys.append((k1, k2))
    return keys


def unpack_values(d: Dict[str, Any]) -> Generator[Any, None, None]:
    for v in d.values():
        for v2 in v.values():
            yield v2


def update_arguments(dict1, dict2):

    for name, table in dict2.items():
        if dict2.get(name):
            for k, v in table.items():
                dict1[name][k] = v
        else:
            dict1[name] = table

    # return dict1


def update_oq_args(oq_args, config_scaler, iter_keys, iter_values):

    update_arguments(oq_args, config_scaler)
    iter_dict = dict()
    for k, v in zip(iter_keys, iter_values):
        iter_dict[k[0]] = {k[1]: v}
    update_arguments(oq_args, iter_dict)
