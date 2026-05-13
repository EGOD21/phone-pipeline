# Authorized SMB Phone Pipeline

Local Python + Postgres pipeline for collecting public business phone numbers from authorized data access, then filtering out franchises, chains, large companies, suppressed numbers, and low-confidence contacts before export.

This project does not include an unrestricted YellowPages.com scraper. YellowPages.com prohibits scraping/data mining in its terms and disallows `/search*` in `robots.txt`. Use the API/license path by default. Use `--source yp-scraper` only when your written Yellow Pages authorization explicitly allows automated extraction and you provide an authorized URL template.

## Setup

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
createdb smb_phone_pipeline
export DATABASE_URL=postgresql://localhost/smb_phone_pipeline
smb-phone-pipeline init-db
```

## Configuration

Copy `.env.example` into your shell environment or export values directly.

Required for API fetches:

```bash
export DATABASE_URL=postgresql://localhost/smb_phone_pipeline
export YP_API_BASE_URL=https://authorized-provider.example/api/search
export YP_API_KEY=...
```

Required for authorized scraper fetches:

```bash
export YP_AUTHORIZES_AUTOMATED_EXTRACTION=true
export YP_SEARCH_URL_TEMPLATE='https://authorized.example/search?term={category}&loc={city}%2C%20{state}&page={page}'
```


## Simplest Workflow

No Postgres required:

```bash
smb-phone-pipeline quick-csv --source yp-api --states TX --limit-cities 1 --max-searches 10
```

Fuller run, still CSV-only:

```bash
smb-phone-pipeline quick-csv --source yp-api --states TX,CA,FL --limit-cities 5 --csv out/approved.csv
```

## Simple Postgres Workflow

After setup and env vars, the database workflow is two pipeline commands:

```bash
smb-phone-pipeline simple-seed
smb-phone-pipeline simple-run --source yp-api
```

For a safer first pass, limit to a few states and batches:

```bash
smb-phone-pipeline simple-seed --states TX,CA,FL
smb-phone-pipeline simple-run --source yp-api --max-batches 5
```

The pipeline searches by city/state/category instead of area code because directory sources usually search geographically, and business phone area codes can be VoIP, neighboring-market, toll-free, or call-center numbers. Area-code checks are still applied during compliance filtering to reject toll-free numbers.

## Usage

```bash
smb-phone-pipeline discover --states CA,TX --categories all --limit-cities 5
smb-phone-pipeline fetch --source yp-api --limit 100
smb-phone-pipeline normalize --limit 1000
smb-phone-pipeline dedupe
smb-phone-pipeline franchise-filter
smb-phone-pipeline compliance-filter
smb-phone-pipeline export --csv out/approved.csv --jsonl out/approved.jsonl
```

Use `run-all` for a bounded dry run:

```bash
smb-phone-pipeline run-all --source yp-api --states CA,TX --limit-cities 2 --fetch-limit 50 --export-csv out/dry-run.csv
```

## Data Safety Defaults

- Keeps source evidence for every record.
- Exports only records with status `approved`.
- Rejects known chains/franchises, repeated names across too many cities/states, national/corporate domains, toll-free phones, suppressed phones/domains, and low-confidence phone records.
- Stores rejected records and rejection reasons for audit.
- Maintains `suppressions` for opt-outs and internal do-not-call records.
