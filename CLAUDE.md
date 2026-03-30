# CLAUDE.md — Project Intelligence for TGMA Platform

## Project Overview
TGMA (Tripura Gut Microbiome in Adolescents) — Flask 3.1 research data management platform.
ICMR-funded study at Tripura University. Self-hosted on Dell PowerEdge R730, LAN-only, Docker deployment.

## Deployment
- **Server**: PowerEdge R730, Ubuntu, Docker Compose at `/home/mmilab/Desktop/tgma-platform`
- **Access**: http://192.168.1.35:8100 (LAN only, no internet)
- **Database**: PostgreSQL 16 in Docker, volume `tgma-platform_pgdata`
- **Rebuild flow**: `git pull && sudo docker compose down && sudo docker compose up -d --build`
- **Re-seed DB**: `sudo docker compose exec web python scripts/init_db.py --synthetic`
- **Full reset (wipes data)**: add `-v` flag to `docker compose down`

## Mistakes Log — Do NOT Repeat

### 1. SESSION_COOKIE_SECURE on HTTP
**What happened**: Set `SESSION_COOKIE_SECURE = True` in ProductionConfig. This caused CSRF "session token missing" errors because the cookie was only sent over HTTPS, but the server runs plain HTTP on LAN.
**Fix**: Set `SESSION_COOKIE_SECURE = False` for LAN-only HTTP deployment.
**Rule**: Never enable secure cookies unless HTTPS is configured.

### 2. Special characters in DATABASE_URL password
**What happened**: DB_PASSWORD in `.env` contained `&`, `%`, `@` characters. Docker Compose interpolated these into `DATABASE_URL`, breaking URL parsing. psycopg2 saw `E&%u@db` as hostname.
**Fix**: Use only alphanumeric passwords in `.env` (no `@`, `&`, `%`, `#`, `=`).
**Rule**: Always use simple alphanumeric passwords for database URLs in environment variables.

### 3. Dockerfile apt-get failures on slim images
**What happened**: `apt-get update` failed with exit code 100 inside `python:3.12-slim` when installing WeasyPrint dependencies (libpango, libpangocairo, etc.).
**Fix**: Removed WeasyPrint deps (not needed yet), kept only `libpq-dev` and `gcc` for psycopg2.
**Rule**: Keep Dockerfile dependencies minimal. Only add system packages that are actively needed.

### 4. Inline grep in Dockerfile RUN
**What happened**: `RUN pip install --no-cache-dir $(grep -v WeasyPrint requirements.txt)` failed because shell expansion inside Docker RUN doesn't work as expected with multiline output.
**Fix**: Split into two commands: `grep > reqs.txt && pip install -r reqs.txt`.
**Rule**: Never use command substitution `$(...)` with pip install in Dockerfiles. Write to temp file first.

### 5. PostgreSQL init.sql referencing non-existent tables
**What happened**: `init_db.sql` creates a trigram index on `participants` table, but this runs during DB initialization before Flask creates the tables. Caused the DB container to be marked "unhealthy".
**Fix**: The error is harmless (DB still starts), but the healthcheck timed out on first run. Just restart.
**Rule**: Don't put table-dependent SQL in `docker-entrypoint-initdb.d/`. Run indexes after `db.create_all()`.

### 6. Duplicate freezer positions in synthetic data
**What happened**: Random freezer position generation (rack/shelf/box/row/col) created collisions, violating the UNIQUE constraint `uq_samples_freezer_position`.
**Fix**: Track used positions in a `set()` and retry until unique.
**Rule**: Always track uniqueness when generating random data for columns with UNIQUE constraints.

### 7. conda multiline argument on Windows
**What happened**: `conda run -n base python -c "..."` with multiline Python code fails on Windows with "Support for scripts where arguments contain newlines not implemented."
**Fix**: Write Python code to a `.py` file and run it, or use single-line `-c` commands.
**Rule**: Never use multiline strings with `conda run` on Windows.

### 8. GitHub password auth rejected
**What happened**: Tried `git clone` with username/password on the server. GitHub no longer accepts passwords.
**Fix**: Made repo public temporarily for cloning, or use Personal Access Token.
**Rule**: Use PAT tokens or SSH keys for GitHub auth. Never attempt password auth.

### 9. Docker port conflicts on shared server
**What happened**: Original `docker-compose.yml` bound PostgreSQL to port 5432 and Nginx to 80/443 — all already in use by other services.
**Fix**: Removed bundled nginx, removed DB port binding (internal only), exposed web on configurable `WEB_PORT` (8100).
**Rule**: Always check existing port usage (`docker ps`) before binding. Never assume standard ports are free on shared servers.

### 10. git clone into non-empty directory
**What happened**: `git clone <url>` without `.` created a subdirectory instead of cloning into current dir. User then couldn't find `.env.example`.
**Rule**: Use `git clone <url> .` to clone into current directory. Verify with `ls` after clone.

## Architecture Rules

### DO
- Use `tracking_id` (VARCHAR 20) as primary key for all participant-related tables
- Keep sample types as `stool` internally (display as "Fecal" in UI)
- Use `saliva_cortisol` for the new cortisol saliva sample type (suffix: COR)
- Use green color palette: #2D6A4F (primary), #52B788 (secondary), #95D5B2, #B7E4C7
- Use `tgma-card` class for cards, `stat-card` for stat cards, `btn-tgma` for buttons
- Test with `conda run -n base python -m pytest tests/ -v` on Windows dev machine
- Commit with `Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>`

### DO NOT
- Do NOT add CDN links — all assets must be local (LAN-only, no internet on server)
- Do NOT use surrogate keys for participant tables — `tracking_id` is the PK
- Do NOT store passwords in plain text anywhere (not even in comments)
- Do NOT use `git push --force` on main
- Do NOT modify `.env` on the server without checking current values first
- Do NOT run `docker compose down -v` unless explicitly asked (destroys all data)
- Do NOT add WeasyPrint or heavy system dependencies to Dockerfile unless specifically needed
- Do NOT assume Python 3.x is default on Windows — use `conda run -n base python`

## File Structure Key Points
- `config.py` — TARGET_SAMPLES_YEAR1=160, SEQUENCING_BATCH_SIZE=32
- `app/models/admin.py` — AuditLog + BloodReport models
- `app/routes/diagnostics.py` — PDF upload (NOT Excel import anymore)
- `app/routes/samples.py` — ALLOWED_SAMPLE_TYPES = ['stool', 'saliva_cortisol']
- `app/templates/samples/qc.html` — DELETED (vendor handles QC)
- `app/templates/diagnostics/import.html` — DELETED (replaced by index.html for PDF upload)
- `scripts/init_db.py` — Has real user credentials (repo must be PRIVATE when these are present)

## Users
| Username | Role | Real Person |
|----------|------|-------------|
| surajit_b | PI | Dr. Surajit Bhattacharjee |
| sanchari_p | Co-PI | Ms. Sanchari Pal |
| argajit_s | Bioinformatician | Mr. Argajit Sarkar |
| field_sup | Field Supervisor | TBD |
