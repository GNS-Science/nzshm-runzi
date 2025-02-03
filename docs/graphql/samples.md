#R2VuZXJhbFRhc2s6Nzc0RFhjUTQ=

```
query s0 {
  search(search_term:"table_type:HAZARD_GRID*") {
    search_result {
      edges {
        node {
          __typename
          ... on AutomationTask {
            id
            created
            parents {
              total_count
            }
            files { total_count}
            #arguments{ k v }
            #metrics {k v}
            duration
            model_type
          }
          ... on Table {
            id
            name
            created
            table_type
            object_id
            column_headers
            column_types
            rows
            dimensions{k v}
          }
        }
      }
    }
  }
}

query gt0 {
  node(id:"R2VuZXJhbFRhc2s6Nzg4VXNHMno=") {
    ... on GeneralTask {
      argument_lists {k v}
      children {
        total_count
        edges {
          node {
            child {
              ... on AutomationTask {
                id
                duration
                state
                created
                task_type
                parents {
                  edges {
                    node {
                      parent {
                        id
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}

query is0 {
  node(id:"SW52ZXJzaW9uU29sdXRpb246MjExNy4wemJkYTc=") {
    __typename
    ... on InversionSolution {
      tables {table_type table_id}
    }
  }
}

query get_table {
    node(id: "VGFibGU6MjZWWUh3UA==") {
    ... on Table {
      id
      name
      created
      table_type
      object_id
      column_headers
      column_types
      # rows
      dimensions{k v}
    }
  }
}

fragment task_files on FileRelationConnection {
  total_count
  edges {
    node {
      ... on FileRelation {
        role
        file {
          ... on Node {
            id
          }
          ... on FileInterface {
            file_name
            file_size
            meta {k v}
          }
          ... on InversionSolution {
            tables {
              table_id
              label
              created
            }
          }
        }
      }
    }
  }
}

query rgt0 {
  #QXV0b21hdGlvblRhc2s6OTk2Q1NoOVg=
  node(id: "QXV0b21hdGlvblRhc2s6OTk2Q1NoOVg=") {
    __typename
    ... on RuptureGenerationTask {
      id
      files {
    	 ...task_files
      }
    }
    ... on AutomationTask {
      model_type
      task_type
      id
      duration
      metrics {k v}
      arguments {k v}
      environment {k v}
      files {
        ...task_files
      }
    }
  }
}

query one_general{
  #node(id: "R2VuZXJhbFRhc2s6Nzk2dFFhY3o=") {
  node(id: "R2VuZXJhbFRhc2s6OTkwWjdqOVE=") {
    __typename
    ... on GeneralTask {
      id
      title
      description
      created
      children {
        #total_count
        edges {
          node {
            child {
              __typename
              ... on Node {
                id
              }
              ... on AutomationTask {
                created
                state
                result

              }
            }
          }
        }
      }
    }
  }
}
```