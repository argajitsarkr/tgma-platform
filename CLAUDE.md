# CLAUDE.md — Project Intelligence for TGMA Platform

## Project Overview
TGMA (Tripura Gut Microbiome in Adolescents) — Flask 3.1 research data management platform.
ICMR-funded study at Tripura University. Self-hosted on Dell PowerEdge R730, LAN-only, Docker deployment.

**Status (April 2026)**: Platform is **feature-complete and actively field-testing**. 65+ source files, 56 tests passing, Docker deployment live. All core workflows operational: participant ID allocation → thermal label printing → KoboCollect field data entry → KoboToolbox sync → dashboard review → document vault upload.

Active KoboToolbox form: **XLSForm v4.1** (`tgma_v4_1` version `2026-04-27-v4.1`). The platform sync layer reads v4.1 field names with v3/earlier names as fallback; group-prefixed Kobo paths are flattened first (see mistake #24).

---

## How the System Works (End-to-End)

### The Big Picture
Field workers collect data from adolescent participants across three districts of Tripura (West, South, Dhalai). Each participant gets a unique tracking ID (e.g. `TGMA-WT-F-001`). This ID is the single thread connecting physical labels, paper forms, biosamples, KoboCollect entries, and the database — everything is linked by it.

### Step 1 — Before the Field Visit: ID Allocation + Label Printing
1. A supervisor (PI/Co-PI/Bioinformatician) opens the platform → **ID Allocation** (`/ids`)
2. Fills in: field worker name, district (WT/ST/DL), gender (M/F), number of IDs (e.g. 10)
3. Platform generates sequential 3-digit IDs: `TGMA-WT-F-001` to `TGMA-WT-F-010`
4. These are saved in the `id_allocations` table (status = `allocated`)
5. The supervisor clicks **Thermal** → expands per-participant buttons → clicks each participant's print button
6. Browser opens `/ids/thermal-labels/TGMA-WT-F-001` → generates 10 QR-code labels as a print page
7. **Ctrl+P** → select DP27 USB thermal printer → paper size **E 50 x 30 mm** → margins **None** → Print
8. The printer outputs 10 stickers (50mm wide × 25mm tall each — the 5mm gap feeds between labels):
   - Folder label (QR + `TGMA-WT-F-001`)
   - Fecal tube (`TGMA-WT-F-001-STL`)
   - Saliva Morning (`TGMA-WT-F-001-SLV1`)
   - Saliva Noon (`TGMA-WT-F-001-SLV2`)
   - Saliva Evening (`TGMA-WT-F-001-SLV3`)
   - Saliva Night (`TGMA-WT-F-001-SLV4`)
   - Consent Form (`TGMA-WT-F-001-DOC`)
   - Assent Form (`TGMA-WT-F-001-DOC`)
   - Information Sheet (`TGMA-WT-F-001-DOC`)
   - Questionnaire (`TGMA-WT-F-001-DOC`)
9. **QR codes encode a direct URL** to the participant's platform page — scanning any label with a phone camera opens the record immediately

### Step 2 — In the Field (Offline)
1. Field worker carries the printed label roll and a KoboCollect-loaded phone
2. For each participant, peels labels and sticks them onto:
   - The participant folder
   - Sample collection vials (fecal tube, 4 saliva vials)
   - Paper forms (consent, assent, info sheet, questionnaire)
3. Opens KoboCollect on phone → opens the TGMA survey form → **types or scans the pre-printed tracking ID** into the `tracking_id` field at the top
4. Fills in the participant's demographics, clinical measurements, GPS location
5. Submits the form — it syncs to KoboToolbox server when internet is available
6. **No platform access needed in the field** — the phone works fully offline

### Step 3 — Back at the Lab: KoboToolbox Sync
1. PI/Co-PI/Bioinformatician opens the platform → **KoboToolbox Sync** (`/kobo`)
2. Clicks **Sync Now** (incremental: only new submissions since last sync)
3. The platform calls KoboToolbox REST API v2, fetches submissions paginated (100/page)
4. For each submission:
   - Validates `tracking_id` format (`TGMA-(WT|ST|DL)-(M|F)-\d{3,4}`)
   - Rejects if `tracking_id`, `full_name`, `gender`, or `district` are missing
   - Upserts: creates new `Participant` record or updates existing one
   - Creates related records: `HealthScreening`, `Anthropometrics`, `LifestyleData`, etc. — but **only if fields are non-NULL**
   - Never overwrites existing non-NULL values with NULL
5. Sync log stored in `kobo_sync_log` — every run shows counts (new/updated/skipped/error)
6. Full re-sync option available if incremental state is lost

### Step 4 — In the Lab: Sample Registration
1. Field worker hands over samples to lab staff
2. Lab staff opens **Samples** (`/samples`) → Register Sample
3. Scans or types the sample ID from the label (e.g. `TGMA-WT-F-001-STL`)
4. Assigns freezer position (rack/shelf/box/row/col) — UNIQUE constraint prevents duplicates
5. Sample travels through the pipeline: registered → stored → shipped → sequenced
6. Sequencing results imported later via `etl/sequencing_import.py` (Nucleome Informatics TSV)

### Step 5 — Document Upload
1. After scanning paper forms, lab staff opens **Documents** (`/documents`)
2. Finds the participant → clicks their vault
3. Uploads scanned PDFs or photos of: consent form, assent form, info sheet, questionnaire
4. Files stored at `{UPLOAD_FOLDER}/participants/{tracking_id}/{doc_type}/`
5. Read-only blood report PDFs (from Diagnostics upload) are merged into the same vault view

### Step 6 — Dashboard Review
- PI opens the dashboard → sees enrollment progress, district breakdown, sample pipeline status
- Data quality route flags GPS outliers, missing data, duplicates
- ICMR progress report auto-generates from current DB state

---

## Deployment
- **Server**: PowerEdge R730, Ubuntu, Docker Compose at `/home/mmilab/Desktop/tgma-platform`
- **Access (LAN)**: http://192.168.1.35:8100
- **Access (public)**: ngrok HTTPS tunnel — URL changes on restart; get current URL with `sudo docker compose logs ngrok | grep url=` or run `bash scripts/ngrok_url.sh`
- **Database**: PostgreSQL 16 in Docker, volume `tgma-platform_pgdata`
- **Rebuild flow**: `git pull && sudo docker compose down && sudo docker compose up -d --build`
- **Re-seed / upsert users**: `sudo docker compose exec web python scripts/init_db.py`
- **Re-seed with synthetic data**: `sudo docker compose exec web python scripts/init_db.py --synthetic`
- **Wipe demo data (keeps users + schema)**: `sudo docker compose exec web python scripts/wipe_data.py --confirm`
- **Full reset (wipes data + volumes)**: add `-v` flag to `docker compose down`
- **Dev machine**: Windows (Anaconda), run with `conda run -n base python`
- **Ngrok setup (one-time)**: Sign up at ngrok.com, add `NGROK_AUTHTOKEN=<token>` to `.env` on server, then rebuild

## Build Verification
```bash
# App factory smoke test
conda run -n base python -c "from app import create_app; app = create_app('testing'); print('OK')"

# Full test suite (44 tests)
conda run -n base python -m pytest tests/ -v
```

---

## Label Printing — Technical Details

### Physical Setup
- **Printer**: DP27 USB thermal label printer
- **Roll**: 50mm wide × 25mm tall stickers (with ~5mm gap between stickers)
- **Printer driver page size**: E 50 x 30 mm (closest available option — the 5mm extra is the gap)

### How It Works in the Browser
- Route `/ids/thermal-labels/<tracking_id>` generates 10 QR code PNGs in-memory using `qrcode` library
- Each QR encodes `http://<server-host>/participants/<tracking_id>` — scanning opens the participant's page
- Template uses `@page { size: 50mm 30mm; margin: 0 }` so browser tells the printer each page = one label
- Inner content container is constrained to `height: 25mm` — content never overflows onto the gap
- Layout: QR code on left (18×18mm) + category tag / description / bold tracking ID on right
- Font: Courier New, 8pt, weight 900 for the tracking ID — legible at thermal resolution

### Print Procedure
1. Click **Thermal** button next to a batch → expand → click per-participant print button
2. New tab opens with the 10-label preview (3×3 grid on screen)
3. Press **Ctrl+P** → select DP27 → Paper size: **E 50 x 30 mm** → Margins: **None** → Print
4. 10 labels print sequentially on the roll

### Label Kit (10 per participant)
| # | Label | Value |
|---|-------|-------|
| 1 | Participant Folder | `TGMA-WT-F-001` |
| 2 | Fecal Sample | `TGMA-WT-F-001-STL` |
| 3 | Saliva Morning (6-8 AM) | `TGMA-WT-F-001-SLV1` |
| 4 | Saliva Noon (12-1 PM) | `TGMA-WT-F-001-SLV2` |
| 5 | Saliva Evening (5-6 PM) | `TGMA-WT-F-001-SLV3` |
| 6 | Saliva Night (10-11 PM) | `TGMA-WT-F-001-SLV4` |
| 7 | Consent Form | `TGMA-WT-F-001-DOC` |
| 8 | Assent Form | `TGMA-WT-F-001-DOC` |
| 9 | Information Sheet | `TGMA-WT-F-001-DOC` |
| 10 | Questionnaire | `TGMA-WT-F-001-DOC` |

Blood vials are NOT labelled by the platform — the diagnostics company requires handwritten participant name/age/sex on vials.

### Deleting Test Allocations
- Expand a batch → small **×** button per ID → deletes that allocation
- **Delete Batch** button wipes the whole batch at once
- Both routes refuse if a `Participant` record already uses that ID (safety check)
- Role-gated: PI / Co-PI / Bioinformatician only

---

## Tracking ID Format
- **Pattern**: `TGMA-{DISTRICT}-{GENDER}-{SEQ}`
- **District codes**: `WT` (West Tripura), `ST` (South Tripura), `DL` (Dhalai)
- **Gender**: `M` or `F`
- **Sequence**: 3 digits (new format, e.g. `001`) — legacy 4-digit IDs (`0001`) still accepted by the validator
- **Examples**: `TGMA-WT-F-001`, `TGMA-ST-M-042`, `TGMA-DL-F-099`
- **Max per district/gender combo**: 999 (3-digit) — sufficient for 440 target enrollment

---

## Complete File Inventory

### App Core
| File | Purpose |
|------|---------|
| `wsgi.py` | WSGI entry point |
| `config.py` | DevelopmentConfig / ProductionConfig / TestingConfig; study params (TARGET_ENROLLMENT=440, TARGET_SAMPLES_YEAR1=160, SEQUENCING_BATCH_SIZE=32); KOBO_API_URL config |
| `requirements.txt` | Flask 3.1, SQLAlchemy, pandas, python-barcode, qrcode, Pillow, openpyxl, gunicorn, psycopg2-binary, etc. |
| `.env.example` | Template for environment variables (DB, Kobo, upload paths, ngrok) |
| `app/__init__.py` | App factory — registers all 10 blueprints, extensions, context processor |
| `app/extensions.py` | SQLAlchemy, Migrate, LoginManager, CSRFProtect |
| `app/auth.py` | Login/logout blueprint, Flask-Login user_loader |

### Models (8 files)
| File | Tables |
|------|--------|
| `app/models/__init__.py` | Re-exports all models |
| `app/models/user.py` | `users` — bcrypt password hashing, roles (pi, co_pi, bioinformatician, field_supervisor) |
| `app/models/participant.py` | `participants` — PK is `tracking_id` (VARCHAR 20), enrollment status, GPS coords; all child tables cascade-delete on `db.session.delete(p)` |
| `app/models/clinical.py` | `health_screenings`, `anthropometrics`, `menstrual_data` — computed BMI, waist-hip ratio |
| `app/models/survey.py` | `lifestyle_data`, `environment_ses` — diet, activity, SES data from KoboToolbox |
| `app/models/sample.py` | `samples`, `sample_shipments` — freezer positions (UNIQUE constraint), chain of custody |
| `app/models/results.py` | `hormone_results`, `sequencing_results`, `id_allocations` — HOMA-IR, TG/HDL computed props |
| `app/models/admin.py` | `audit_log`, `blood_reports`, `kobo_sync_log`, `participant_documents` — diagnostics PDFs, sync history, per-participant scanned forms/photos |

### Route Blueprints (10 files)
| File | URL Prefix | Key Features |
|------|-----------|--------------|
| `app/routes/__init__.py` | — | Package init |
| `app/routes/dashboard.py` | `/` | Stats cards, enrollment progress, district breakdown charts |
| `app/routes/participants.py` | `/participants` | CRUD, server-side DataTables API, detail, edit (POST), delete (POST + cascade) — gated to PI/Co-PI/Bioinformatician |
| `app/routes/samples.py` | `/samples` | Register, tracker, freezer map, dispatch, detail |
| `app/routes/diagnostics.py` | `/diagnostics` | Blood report PDF upload |
| `app/routes/ids.py` | `/ids` | Bulk ID allocation; batches table with re-print, Excel kit, per-participant thermal print (50x30mm page / 25mm sticker) and delete buttons; `thermal_labels()` generates 10 QR code PNGs via `qrcode` + base64 data URIs, QR encodes participant URL; `delete_allocation()` and `delete_batch()` with participant-exists safety check; LABEL_KIT = 10 labels |
| `app/routes/quality.py` | `/quality` | GPS bounds check, outlier detection (\|Z\|>3), duplicates, missing data |
| `app/routes/kobo.py` | `/kobo` | Manual "Sync Now" + Full Re-sync, sync log history, per-run detail view. PI/Co-PI/Bioinformatician only. |
| `app/routes/documents.py` | `/documents` | Per-participant document vault — upload/view/download/delete scanned forms and photos (PDF+JPG+PNG). Merges read-only `BloodReport` rows. Upload+delete gated to PI/Co-PI/Bioinformatician. Path-traversal guard via `validate_tracking_id()`. Self-healing `_ensure_table()`. |
| `app/routes/ml.py` | `/ml` | Placeholder for ML pipeline status |
| `app/routes/reports.py` | `/reports` | ICMR progress report, export-ready |

### Templates (22 files)
| File | Notes |
|------|-------|
| `app/templates/base.html` | Sidebar layout, Satoshi font, Bootstrap 5, DataTables, Chart.js — all local assets |
| `app/templates/login.html` | Centered login card |
| `app/templates/dashboard.html` | Stat cards, enrollment chart, district pie |
| `app/templates/participants/list.html` | Server-side DataTables with district/gender/status/lifestyle filters |
| `app/templates/participants/detail.html` | Tabbed view: demographics, clinical, samples, surveys. Role-gated Edit + Delete + Documents shortcut in header |
| `app/templates/samples/tracker.html` | Sample pipeline overview |
| `app/templates/samples/register.html` | New sample form |
| `app/templates/samples/detail.html` | Single sample view |
| `app/templates/samples/freezer.html` | Freezer grid map |
| `app/templates/samples/dispatch.html` | Shipment management |
| `app/templates/diagnostics/index.html` | Blood report PDF upload |
| `app/templates/ids/allocate.html` | Bulk ID generation form; sequence status table; batches table with expandable thermal print + per-ID/batch delete buttons |
| `app/templates/ids/labels.html` | Batch label sheet — 10-label info banner, per-participant thermal print button table, 4-column grid preview |
| `app/templates/ids/thermal_labels.html` | Print-ready thermal labels — `@page { size: 50mm 30mm }`, 25mm inner content area, 10 QR codes as base64 PNGs, QR left + text right, 3×3 screen preview |
| `app/templates/quality/dashboard.html` | Data quality dashboard |
| `app/templates/ml/status.html` | Coming soon placeholder |
| `app/templates/reports/index.html` | Report listing |
| `app/templates/reports/icmr_progress.html` | ICMR progress report template |
| `app/templates/kobo/sync.html` | KoboToolbox sync dashboard — Sync Now / Full Re-sync, history table |
| `app/templates/kobo/log_detail.html` | Per-run detail — stat cards, filterable submission table, error messages |
| `app/templates/documents/index.html` | Document vault landing — participant list with doc counts, client-side search |
| `app/templates/documents/vault.html` | Per-participant vault — role-gated upload form, grouped doc-type cards, merged blood-report section |

### Static Assets
| File | Notes |
|------|-------|
| `app/static/css/custom.css` | Full custom theme — Satoshi font, green palette (#2D6A4F), sidebar, cards, tables, responsive, print |
| `app/static/js/charts.js` | Chart.js helpers for dashboard |
| `app/static/vendor/` | Bootstrap 5, jQuery 3, Chart.js, DataTables — all local, no CDN |
| `app/static/vendor/fonts/Satoshi-*.woff2` | Satoshi font family (Light, Regular, Medium, Bold) |

### Utils
| File | Purpose |
|------|---------|
| `app/utils/helpers.py` | `validate_tracking_id()`, `generate_tracking_id()` (3-digit: `%03d`), `generate_sample_id()`, `validate_gps()`, `validate_age()`; TRACKING_ID_PATTERN = `TGMA-(WT\|ST\|DL)-(M\|F)-(\d{3,4})` (3-digit new, 4-digit legacy); SAMPLE_SUFFIXES dict |
| `app/utils/decorators.py` | `@role_required()` decorator for route protection |
| `app/utils/audit.py` | Audit logging helper |

### ETL Scripts (3 files)
| File | Purpose |
|------|---------|
| `etl/kobo_sync.py` | KoboToolbox sync engine — `_do_sync()` core logic + `run_sync()` context-aware wrapper. Paginated API fetch, critical-field validation, idempotent upsert, NULL-safe, sync log. |
| `etl/hormone_import.py` | Import hormone/diagnostics results from Excel/CSV |
| `etl/sequencing_import.py` | Import Nucleome Informatics vendor manifest TSV |

### Deployment (5 files)
| File | Purpose |
|------|---------|
| `Dockerfile` | python:3.12-slim, libpq-dev + gcc, gunicorn (4 workers) |
| `docker-compose.yml` | PostgreSQL 16-alpine + Flask/Gunicorn; `WEB_PORT` configurable (default 8100); DB port internal only |
| `nginx.conf` | Optional reverse proxy config |
| `systemd/tgma-dashboard.service` | Systemd unit for non-Docker deploy |
| `scripts/backup.sh` | Daily pg_dump with 30-day retention |

### Scripts
| File | Purpose |
|------|---------|
| `scripts/init_db.py` | DB init + upsert 5 users + `--synthetic` for ~50 test participants. **Repo must be PRIVATE — contains credentials.** |
| `scripts/wipe_data.py` | Reset script — deletes all participants (cascade), ID allocations, KoboSync logs. `--confirm` required. Preserves users. Also `shutil.rmtree`s `participants/` upload folder. |
| `scripts/init_db.sql` | PostgreSQL extensions (pg_trgm). |
| `scripts/generate_barcodes.py` | Generate Code128 barcode label PDFs (legacy, superseded by browser QR printing) |
| `scripts/ngrok_url.sh` | Fetch current ngrok public URL from local API (port 4040) |

### Tests (4 files, 44 tests)
| File | Tests |
|------|-------|
| `tests/conftest.py` | TestingConfig (SQLite in-memory), session rollback per test, `pi_user` and `auth_client` fixtures |
| `tests/test_models.py` | 19 tests — tracking ID validation (3-digit new + 4-digit legacy), sample ID generation, GPS, age, BMI/WHR, HOMA-IR, TG/HDL, password hashing, roles |
| `tests/test_auth.py` | 6 tests — login page, success/failure, protected redirect, logout |
| `tests/test_kobo_sync.py` | 19 tests — critical-field validation, field mapping, NULL sections, gender/district derivation, GPS, menstrual gating |

---

## Mistakes Log — Do NOT Repeat

### 1. SESSION_COOKIE_SECURE on HTTP
Set `SESSION_COOKIE_SECURE = True` → CSRF "session token missing" on HTTP LAN. Set to `False` for HTTP deployment.

### 2. Special characters in DATABASE_URL password
`&`, `%`, `@` in DB_PASSWORD break Docker Compose URL interpolation. Use alphanumeric passwords only.

### 3. Dockerfile apt-get failures on slim images
WeasyPrint deps (`libpango`, etc.) fail on `python:3.12-slim`. Keep Dockerfile deps minimal.

### 4. Inline grep in Dockerfile RUN
`RUN pip install $(grep -v X requirements.txt)` — shell expansion breaks. Write to temp file first: `grep > reqs.txt && pip install -r reqs.txt`.

### 5. PostgreSQL init.sql referencing non-existent tables
Trigram index in `docker-entrypoint-initdb.d/` runs before Flask creates tables → healthcheck timeout. Don't put table-dependent SQL there.

### 6. Duplicate freezer positions in synthetic data
Random position generation hits UNIQUE constraint. Track used positions in a `set()` and retry.

### 7. conda multiline argument on Windows
`conda run -n base python -c "..."` with newlines fails. Write to `.py` file instead.

### 8. GitHub password auth rejected
GitHub no longer accepts passwords for clone/push. Use PAT tokens or SSH keys.

### 9. Docker port conflicts on shared server
PostgreSQL 5432 and Nginx 80/443 already in use. Always check `docker ps` before binding ports.

### 10. git clone into non-empty directory
`git clone <url>` without `.` creates a subdirectory. Use `git clone <url> .`.

### 11. Read tool required before Write on existing files
Claude Code Write tool rejects writes to files not yet read in the session. Always Read first.

### 12. Context window exhaustion during large builds
Building 54+ files in one session hits context limits. Commit frequently, use parallel batches.

### 13. Test assertion against wrong validation layer
The tracking_id regex `TGMA-(WT|ST|DL)-(M|F)-(\d{3,4})` rejects before gender validation runs. Assert `error is not None` rather than a specific message substring.

### 14. ETL script as CLI-only, not importable
CLI-only `main()` with its own app context can't be called from a Flask route. Design ETL scripts as importable modules with a public function + thin CLI wrapper.

### 15. Upsert clobbering existing data with NULLs
Sync overwriting non-NULL values with NULL on re-sync. Only update fields where new value `is not None`. Skip creating related records if ALL fields are NULL.

### 16. Importing from parent directory in route handlers
`etl/` is outside the app package. Use `sys.path.insert(0, project_root)` at import time in the route.

### 17. New model table missing on deployed server
Added `kobo_sync_log` table locally but `db.create_all()` not re-run on server → 500. Use `_ensure_table()` self-healing pattern or Flask-Migrate.

### 18. Nested app context crash when calling ETL from Flask route
`with app.app_context():` inside `run_sync()` nested inside the request context → session detached on exit → 500. Use `flask.has_app_context()` to detect existing context. Always wrap route operations in try/except.

### 19. `Query.delete()` bypasses ORM cascade rules
`Participant.query.delete()` leaves orphaned child rows. Always iterate and `db.session.delete(p)` per object when cascade matters.

### 20. URL path segments joined into filesystem paths without validation
`tracking_id` from URL can contain `../` sequences. Always call `validate_tracking_id()` before any `os.path.join` with user-controlled strings.

### 21. `scripts/` not in `sys.path` when run inside Docker container
`docker compose exec web python scripts/wipe_data.py` → `ModuleNotFoundError: No module named 'app'`. Add `sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))` at top of every script in `scripts/`.

### 22. Code128 barcodes don't scan from phone at thermal printer resolution
Thermal printers compress fine bars of Code128 barcodes, making them unreadable by phone cameras. Use QR codes instead — they are error-tolerant, square, and scan reliably at small sizes.

### 23. `@page` CSS size must match printer driver's available paper sizes
Setting `@page { size: 50mm 25mm }` has no effect if the printer driver doesn't offer that size. The actual sticker is 25mm tall but the closest driver option is "E 50 x 30 mm". Set `@page` to 50x30mm to match the driver, then constrain content to 25mm with an inner container. The 5mm difference falls on the inter-label gap.

### 24. KoboToolbox API returns group-prefixed field paths — sync silently fails without flattening
**Symptom**: "Sync Now" reports success, the per-run log card shows `inserted=0, updated=0, skipped=N`, every detail row says `Missing tracking_id — skipped`, and field-test data never appears on `/participants`. The sync_log row is `status='success'` because each rejection is caught cleanly inside the per-row try/except — the worst kind of "green" failure.

**Cause**: When the XLSForm uses `begin_group` / `end_group` (v4.1 has six top-level parts and many sub-groups), KoboToolbox API v2 returns submission JSON with **the group path prefixed onto every field name**: `part_a/tracking_id`, `part_b/b1/b1_chronic_illness`, `part_f/anthro/anthro_height_cm`, etc. `submission.get('tracking_id')` returns `None`, validation rejects it as a missing required field, the participant is never created.

**Fix**: Flatten the submission dict before any field reads. Strip everything before the last `/` (XLSForm field names are globally unique within a form, so last-segment-wins is safe). Always preserve keys starting with `_` (Kobo metadata). See `flatten_kobo_submission()` in `etl/kobo_sync.py` — it's idempotent, so calling it on already-flat dicts is a no-op.

---

## Architecture Rules

### DO
- Use `tracking_id` (VARCHAR 20, 3-digit format) as primary key for all participant-related tables
- Keep sample types as `stool` internally (display as "Fecal" in UI)
- Use `saliva_cortisol` for cortisol saliva type (suffix: COR)
- Use green color palette: #2D6A4F (primary), #52B788 (secondary), #95D5B2, #B7E4C7
- Use `tgma-card` class for cards, `stat-card` for stat cards, `btn-tgma` for buttons
- Use Satoshi font family (woff2 in `app/static/vendor/fonts/`)
- All vendor libraries must be local (no CDN — LAN-only, no internet on server)
- DataTables for server-side paginated tables; Chart.js for dashboard charts
- Design ETL scripts as importable modules with a public function + thin CLI wrapper
- In upsert logic, only overwrite with non-NULL values (preserve existing data)
- Gate admin features with `@role_required('pi', 'co_pi', 'bioinformatician')`
- Always call `validate_tracking_id()` before joining `tracking_id` into a filesystem path
- Test with `conda run -n base python -m pytest tests/ -v` on Windows dev machine
- Commit with `Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>`
- Use QR codes (not Code128) for thermal label printing

### DO NOT
- Do NOT add CDN links — all assets must be local
- Do NOT use surrogate keys for participant tables — `tracking_id` is the PK
- Do NOT store passwords in plain text anywhere
- Do NOT use `git push --force` on main
- Do NOT run `docker compose down -v` unless explicitly asked (destroys all data)
- Do NOT add WeasyPrint or heavy system dependencies to Dockerfile unless needed
- Do NOT assume Python 3.x is default on Windows — use `conda run -n base python`
- Do NOT use multiline strings in `conda run -n base python -c` on Windows
- Do NOT overwrite existing DB values with NULL during upsert/sync
- Do NOT auto-sync KoboToolbox on a schedule — manual trigger only
- Do NOT accept KoboToolbox submissions missing `tracking_id`, `full_name`, `gender`, `district`
- Do NOT use `Query.delete()` on models with ORM cascade relationships
- Do NOT use Code128 barcodes for thermal printing — use QR codes

---

## CSS Theme Reference
- **Background**: `--tgma-bg: #F5F3EF`
- **Card**: `--tgma-card: #FFFFFF` with `--tgma-border: #E8E5DF`
- **Primary accent**: `--tgma-accent: #2D6A4F` / hover: `#245A42`
- **Light green**: `--tgma-accent-light: #D8F3DC`
- **Greens**: `--tgma-green-500: #52B788`, `--tgma-green-300: #95D5B2`, `--tgma-green-200: #B7E4C7`
- **Text**: `--tgma-text: #1B1B1B`, muted: `--tgma-muted: #6B7280`
- **Radius**: `--tgma-radius: 14px`, small: `10px`
- **Sidebar width**: `260px`
- **Responsive**: sidebar hidden below 768px
- **Print**: sidebar, top-bar, buttons, tabs hidden

---

## Study Parameters (config.py)
| Parameter | Value |
|-----------|-------|
| TARGET_ENROLLMENT | 440 |
| TARGET_SAMPLES_YEAR1 | 160 |
| TARGET_SEQUENCING | 160 |
| DISTRICT_TARGETS | WT: 200, ST: 100, DL: 100 |
| LIFESTYLE_GROUPS | AT, AP, SDT, SP (100 each) |
| SEQUENCING_BATCH_SIZE | 32 |
| TOTAL_BATCHES_YEAR1 | 5 |
| GPS bounds | Lat: 22.9–24.5, Lon: 91.1–92.3 |

---

## Users
| Username | Role | Real Person | Default Password |
|----------|------|-------------|-----------------|
| surajit_b | pi | Dr. Surajit Bhattacharjee | SurajitPI@2026 |
| shib_d | co_pi | Dr. Shib Sekhar Datta | ShibCoPI@2026 |
| sanchari_p | bioinformatician | Miss. Sanchari Pal (Project Scholar) | SanchariTGMA@2026 |
| argajit_s | bioinformatician | Mr. Argajit Sarkar (Project Scholar) | ArgajitTGMA@2026 |
| field_sup | field_supervisor | Field Supervisor | FieldTGMA@2026 |

---

## KoboToolbox Sync Strategy
- **Active form**: `tgma_v4_1` version `2026-04-27-v4.1` (XLSForm v4.1 — heavy `begin_group` nesting)
- **Trigger**: Manual only — PI/Co-PI/Bioinformatician clicks "Sync Now" in UI (`/kobo`)
- **Modes**: Incremental (since last sync) or Full (re-fetch everything)
- **Critical fields (REJECT if missing)**: `tracking_id`, `full_name`, `gender`, `district`
- **Optional fields (accept as NULL)**: age, DOB, GPS, anthropometrics, lifestyle, environment, menstrual
- **Group flattening**: `flatten_kobo_submission()` strips group-path prefixes from every key first thing — see mistake #24. Idempotent.
- **Multi-version field reads**: `_first(sub, 'v4.1_name', 'v3_name')` reads new names with old-name fallback so historical submissions still parse.
- **Slug → midpoint** for select_one fields that target numeric DB columns (sitting hours, screen time, meals/day, family size). Maps live in `etl/kobo_sync.py` next to the field-rename table.
- **Gender slug**: v4.1 sends `male`/`female`; v3 sent `M`/`F`. Both accepted via `GENDER_SLUG_TO_CODE`.
- **District**: v4.1 sends 2-letter code directly; v3 sent slug (`west_tripura`). Both accepted via `DISTRICT_SLUG_TO_CODE`. `district='other'` rejected (non-Tripura participants don't fit the tracking-ID schema).
- **Idempotent**: Upserts by `tracking_id` — syncing same submission twice updates existing record
- **NULL-safe**: Only overwrites with non-NULL values; empty optional sections don't create empty related records
- **GPS**: Read from `_geolocation` array first, then v4.1 `gps_location` geopoint string (`"lat lon alt acc"`), then legacy `gps_latitude`/`gps_longitude`. Out-of-bounds → WARNING, not rejection.
- **Sync log**: Every run stored in `kobo_sync_log` with counts + per-submission JSON details
- **API**: KoboToolbox REST API v2, paginated (100/page), sorted by `_submission_time`
- **State file**: `etl/.kobo_sync_state.json` stores last sync timestamp for incremental mode

---

## Git History (as of April 2026)
```
(pending) Align platform to XLSForm v4.1; fix silent KoboSync bug (group-prefixed JSON keys, mistake #24)
27f9eea Align platform to KoboToolbox XLSForm v3 (NT/GT/UK districts, slug-aware sync, yn_to_bool fix)
560ca7a Update CLAUDE.md: full how-it-works narrative, label printing details, mistake #22-23
2749d22 Split Consent + Assent into separate labels (9 → 10 per participant)
93abd18 QR links to participant page, 3-digit IDs, larger label text, remove footer
f288602 Switch thermal labels to QR codes, fix 25mm sticker fit, add ID delete
c570975 Add direct thermal label printing (50x25mm) with real Code128 barcodes
70fc1f9 Update CLAUDE.md: April 2026 refresh
4c72f01 Fix wipe_data.py ModuleNotFoundError: add project root to sys.path
24171ac Add per-participant Document Vault for scanned forms and photos
0615b3e Add participant edit/delete UI, demo-data wipe script, and batched label-kit access
6a08b2f Add Label Kit Excel generator for Seznik thermal printer workflow
8b01ceb Fix DataTables sort icon rendering and participants table column widths
4756173 Add participant stat cards and fix KoboSync placeholder credential error
45479c2 Add ngrok public tunnel, 5-user upsert, and label sheet for field worker workflow
0173610 Fix Sync Now 500 error: nested app context + unhandled exception
bf78019 Fix KoboToolbox sync 500 error: auto-create missing table on first access
ebaaa28 Add KoboToolbox sync with manual UI trigger, validation, and sync log
```
