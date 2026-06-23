# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),

## [1.2.0] - 2026-06-23

### Added

- Support for multiple year queries per report template
- `SiteReport` class extracted into its own module for cleaner structure
- Test suite with 16 pytest tests covering generate, validate, isolation, and save
- Test data bundle for integration-style tests

### Changed

- Refactored report generation to remove side effects and support processing multiple sites from a single DSF result
- Updated report-queries.json to newest version

### CI

- Added test and lint jobs (pytest + ruff) that must pass before Docker build
- Enforced job ordering: test → docker-build → build-and-push-image
- Fixed `actions/checkout` version (v5 → v4)

## [1.1.2] - 2025-09-19


### Changed

- Remove logging of reports
- Update CI actions

## [1.1.1] - 2025-09-19

### Added

- CI and container build

### Changed

- Improved robustness, by catching missing or empty fields in capabilityStatement
- Update report-queries.json to newest version

### Security

- Added Renovate
- Update used libraries

## [1.1.0] - 2024-08-07

### Changed

- Updated Encounter year query handling 

## [1.0.0] - 2024-07-01

- Initialized project

### Added

- Add basic report queries to count number of resources available for each profile
- Yearly Query for encounter
- Validate query completeness and report format
- Dynamically get dsf organisation idents
- Added report schema
- Added basic container deployment
- Make mii relevant resources and dsf site ident to abbreviation mapping configurable
- Revert to dsf site idents if site not found in mapping
