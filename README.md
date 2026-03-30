# TGMA Research Data Platform

Private, self-hosted research data management platform for the **TGMA (Tripura Gut Microbiome in Adolescents)** study — an ICMR-funded project (Grant ID: IIRPSG-2025-01-03722) at Tripura University, India.

**PI:** Prof. Surajit Bhattacharjee (Dept. of Molecular Biology & Bioinformatics, Tripura University)
**Co-PI:** Dr. Shib Sekhar Datta (Tripura Medical College & Dr. BRAM Teaching Hospital)
**Lead Bioinformatician:** Mr. Argajit Sarkar

## Quick Start (Docker)

```bash
# 1. Clone and configure
git clone <repo-url> /opt/tgma-platform
cd /opt/tgma-platform
cp .env.example .env
# Edit .env — set SECRET_KEY, DB_PASSWORD, LAN_IP

# 2. Start services
docker compose up -d

# 3. Initialize database and seed users
docker compose exec web python scripts/init_db.py --synthetic

# 4. Access at https://<LAN_IP>
```

## Quick Start (Direct Install on Ubuntu)

```bash
# Prerequisites
sudo apt update
sudo apt install python3.12 python3.12-venv postgresql nginx

# Database
sudo -u postgres createuser tgma_user -P
sudo -u postgres createdb tgma_db -O tgma_user
sudo -u postgres psql tgma_db < scripts/init_db.sql

# Application
cd /opt/tgma-platform
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your DATABASE_URL, SECRET_KEY, etc.

# Initialize
python scripts/init_db.py --synthetic

# Run (development)
python wsgi.py

# Run (production with systemd)
sudo cp systemd/tgma-dashboard.service /etc/systemd/system/
sudo systemctl enable --now tgma-dashboard
```

## Default Login Credentials

| Role | Username | Password |
|------|----------|----------|
| PI | `pi_sb` | `changeme_pi_2026` |
| Co-PI | `copi_ssd` | `changeme_copi_2026` |
| Bioinformatician | `bioinfo_as` | `changeme_bioinfo_2026` |
| Field Supervisor | `field_sup` | `changeme_field_2026` |

**Change these immediately after first login.**

## Features

- **Dashboard** — Enrollment progress, sample collection status, budget tracking
- **Participant Registry** — Searchable/filterable participant list with full detail views (demographics, health screening, lifestyle, anthropometrics, samples, hormone results, sequencing, audit trail)
- **Sample Tracker** — Freezer inventory, batch dispatch to sequencing vendor, QC view
- **ID Allocation** — Pre-allocate participant IDs for field collection days
- **Diagnostics Import** — Upload hormone/lipid panel results from Excel/CSV with validation
- **Data Quality** — Missing data analysis, anthropometric outliers, GPS validation, duplicate detection
- **ML Pipeline** — Feature matrix export (CSV) for the metabolic risk prediction pipeline
- **Reports** — ICMR progress report, enrollment summary, sample inventory (CSV export)
- **Audit Logging** — All data changes tracked with user, timestamp, old/new values

## ETL Scripts

```bash
# KoboToolbox sync (run daily via cron)
python etl/kobo_sync.py

# Import hormone results from diagnostics center
python etl/hormone_import.py path/to/results.xlsx

# Import sequencing results from Nucleome Informatics
python etl/sequencing_import.py path/to/manifest.tsv
```

## Barcode Generation

```bash
# Generate tracking ID barcodes
python scripts/generate_barcodes.py --range TGMA-WT-F 1 20

# Generate sample barcodes for a participant
python scripts/generate_barcodes.py --samples TGMA-WT-F-0037
```

## Backups

```bash
# Manual backup
bash scripts/backup.sh

# Add to cron (daily at 2 AM)
echo "0 2 * * * /opt/tgma-platform/scripts/backup.sh >> /var/log/tgma/backup.log 2>&1" | crontab -
```

## Tech Stack

- **Backend:** Flask 3.1, Flask-SQLAlchemy, Flask-Login, Flask-Migrate
- **Database:** PostgreSQL 16
- **Frontend:** Bootstrap 5.3, Chart.js 4, DataTables 2, jQuery 3.7 (all vendored locally)
- **Deployment:** Docker Compose / Gunicorn + Nginx + systemd
- **Server:** Dell PowerEdge R470, Ubuntu, 84 GB RAM, 2 TB storage

## Security

- LAN-only access (nginx binds to TU LAN IP, not 0.0.0.0)
- HTTPS with self-signed certificate
- PostgreSQL listens on localhost only
- All passwords in .env (gitignored)
- Session timeout: 30 minutes
- Audit logging on all data modifications
- **This platform stores identifiable health data of minors. It must NEVER be publicly accessible.**

## Project Structure

```
tgma-platform/
├── app/                    # Flask application
│   ├── models/             # SQLAlchemy models (7 files)
│   ├── routes/             # Blueprint routes (8 modules)
│   ├── templates/          # Jinja2 templates (17 files)
│   ├── static/             # CSS, JS, vendor libs
│   └── utils/              # Decorators, audit, helpers
├── etl/                    # ETL scripts (Kobo, hormones, sequencing)
├── scripts/                # DB init, backup, barcode generation
├── tests/                  # Pytest test suite
├── config.py               # Flask configuration
├── wsgi.py                 # WSGI entry point
├── docker-compose.yml      # Docker deployment
├── Dockerfile
├── nginx.conf
└── systemd/                # Systemd service file
```

## Participant Tracking ID

Format: `TGMA-[DISTRICT]-[GENDER]-[SEQUENTIAL]`

- District: WT (West Tripura), ST (South Tripura), DL (Dhalai)
- Gender: M (Male), F (Female)
- Sequential: 0001–9999

Example: `TGMA-WT-F-0037` = West Tripura, Female, Participant #37

This ID is the **universal primary key** — every table references it. Sample IDs append a suffix: `-STL` (stool), `-BLD` (blood), `-SLV1` through `-SLV4` (saliva), `-DNA`, `-SRM`.
