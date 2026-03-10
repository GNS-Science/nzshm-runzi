# Changelog

## [0.9.2] 2026-03-11

## Added
 - Shared validator module `runzi/tasks/validators.py` with `all_or_none`, `exactly_one`, `at_most_one`, and `resolve_path` helpers
 - Tests for all shared validators (`tests/test_validators.py`)

## Changed
 - Refactored inline validation logic in inversion, coulomb, and hazard task modules to use shared validators

## [0.9.1] 2026-03-10

## Changed
 - Improved docker build with UCERF converter option
 - Documentation for building and running docker image
 - Reduced size of docker image

## Added
 - Script for building and deploying docker image
 
## Removed
 - OpenQuake example input files

## [0.9.0] 2026-03-03

## Changed
 - Complete refactor of job configuration and execution
   - Pydantic models for verification of input data
   - Simpler pattern for extending to new task types
   - JSON config files are now validated before submission
   - CLI restructured into subcommands
 - Modernization of python dev standards (pyproject.toml, type hints, etc.)

## Added
 - Sideload paleoseismic recurrence interval
 - Sideload custom fault models
 - Sideload named faults

## Removed
 - python3.9 support

## [0.1.0] 2025-*

## Added
- Initial documentation
- Development toolchain and workflows
- Expand user paths for files specified in hazard config file
- Hazard Task: docker image hash
- Classes for specifying input arguments to scripts.

## Changed
- Hazard and disaggregation job configuration and parsing of sites handled by `nzhsm-model`
- Hazard realizations written to arrow/parquet dataset with `toshi-hazard-store`
- General Task: logic trees, location file, hazard config are uploaded as files
- Hazard Task: logic trees, and hazard config are stored as json

## Removed
 - Deleted unused automation scripts
 - Moved deprecated automation scripts to arkive
