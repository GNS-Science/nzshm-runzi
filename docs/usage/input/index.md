# Input Arguments and Files
The input arguments for every task type is defined by a `pydantic` `BaseModel` class. The definitions of these classes can be found in the sections below. The input files are `json` representations of one of these input argument objects with a few exceptions:
- `title` and `description` fields must also be provided
- A special `swept_args` field.
- `sys_arg_overrides`

`swept_args` are arguments that the user wishes to iterate over. If multiple arguments are swept, runzi will run all combinations of the swept arguments. Any arguments in `swept_args` must not be present elsewhere in the input file.

The `sys_arg_overrides` field is used to over-write the default system arguments for that particular job type. See the [SystemArgs](system_args.md) documentation for a list of available system arguments. Default system arguments for each job type can be found on the respective page.

# Validators
Some input classes have validators to ensure that only valid inputs or valid combinations of imputs are allowed. These will be listed with each argument class under `Validators`.

# General Task IDs
Some task types have a `source_solution_id` parameter. At the time of spawning the jobs, these can be toshi GeneralTask IDs. In this case, runzi will find the produced inversion solutions (or rupture sets) from the GeneralTask and automatically generate swept arguments of the resultant solutions (or rupture sets).

# Example
For Coulomb rupture set generation the input file might look like this.

```
{
    "title": "Prefered, Min, and Max dips Rupture set",
    "description": "Rupture sets with range of possible dip values",

    "max_sections": 2000,
    "max_jump_distance": 15,
    "adaptive_min_distance": 6,
    "thinning_factor": 0,
    "min_sub_sects_per_parent": 2,
    "min_sub_sections": 2,
    "scaling_relationship": "SIMPLE_CRUSTAL",

    "depth_scaling": 
        {
            "sans":  0.8,
            "tvz":  0.667
        }
    ,

    "swept_args": {
        "fault_model_file": [
            {"tag": "max dip", "archive_id": "RmlsZToxMDIyNjA="},
            {"tag": "min dip", "archive_id": "RmlsZToxMDIyNjE="},
            {"tag": "preferred dip", "archive_id": "RmlsZToxMDIyNjI="}
        ]
    },

    "sys_arg_overrides": {
        "ecs_vcpu": 24
    }

}
```