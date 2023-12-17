from typing import Dict, Any, Generator


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


def update_oq_args(oq_args, config_scaler, iter_keys, iter_values, description):

    update_arguments(oq_args, config_scaler)
    iter_dict = dict()
    for k, v in zip(iter_keys, iter_values):
        iter_dict[k[0]] = {k[1]: v}
    update_arguments(oq_args, iter_dict)
    update_arguments(oq_args, {"general": {"description": description}})
