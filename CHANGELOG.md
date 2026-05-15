# Changelog

All notable changes to JobScout will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Admin Blueprint scaffold (routes/admin_routes.py) + GET /api/admin/doctor health-check endpoint with 6 probes (#22).
- Thread-safe scrape status broker (`core/scrape_status.py`) and `GET /api/scrape/status` endpoint for live progress polling (#19).
- Dashboard Monitor tab now shows live per-company scrape progress (current company, completed/total, jobs found, ETA) while a scrape is running (#19).

### Fixed
- `run_scrape()` TypeError on `POST /api/scrape` — caller signature aligned (#19).
