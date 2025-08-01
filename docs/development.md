# Codegen for toshi API graphql queries

We can use ariadne-codegen to generate typed classes and async functions for making calls to the toshi API.
1. Add the query to runzi/automation/scaling/toshi_api_codegen/queries.graphql
2. Run ariadne
```
$ poetry run ariadne-codegen client
```
3. Move the generated code to the correct package location
```
$ mv graphql_client/ runzi/automation/scaling/toshi_api_codegen/
```