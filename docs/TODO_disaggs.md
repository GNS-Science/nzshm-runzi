## TODO disaggs

 - get the template config automatically instead of manually in teh oq_run_disagg

```
query hazard_sol {
  node(id:"T3BlbnF1YWtlSGF6YXJkU29sdXRpb246MTA2OTc3") {
    __typename
    ... on OpenquakeHazardSolution {
        modified_config {
          id
          file_name
          file_size
          file_url
        }
    }
  }
}

```

 - add useful metadata to the final hazard solution (Done needs TUI update)
 - add predecessors
 - store the modified config
 - add Annes openquake code automatically in dockerfile
 - test Hazard again
 - add OHS type enum for DISAGGS
 - update Automation TASK_TYPE enum fro DISAGGS
 - check on Annes mods into GEM oq-engine/main