# Changelog

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
