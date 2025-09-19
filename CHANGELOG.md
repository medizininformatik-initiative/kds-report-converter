# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),


## [1.1.1] - 2025-09-19

### Added

- CI and container build

### Changed

- Improved robustnes, by catching missing or empty fields in capabilityStatement

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
