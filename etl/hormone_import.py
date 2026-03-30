#!/usr/bin/env python3
"""Import hormone/diagnostics results from Excel/CSV into PostgreSQL.

Usage:
    python etl/hormone_import.py path/to/results.xlsx
    python etl/hormone_import.py path/to/results.csv --dry-run
"""

import os
import sys
import logging
from datetime import datetime

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.extensions import db
from app.models import Participant, HormoneResult

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Validation ranges for hormone values
VALIDATION_RANGES = {
    'fasting_glucose_mg_dl': (30, 500),
    'insulin_uiu_ml': (0.5, 300),
    'cortisol_serum_ug_dl': (1, 60),
    'cortisol_saliva_awakening': (0.01, 5.0),
    'cortisol_saliva_30min': (0.01, 5.0),
    'cortisol_saliva_4pm': (0.01, 5.0),
    'cortisol_saliva_bedtime': (0.01, 5.0),
    'igf1_ng_ml': (10, 1000),
    'total_cholesterol_mg_dl': (50, 500),
    'hdl_mg_dl': (5, 150),
    'ldl_mg_dl': (10, 400),
    'triglycerides_mg_dl': (20, 1000),
}

# Column name aliases (map common variations to canonical names)
COLUMN_ALIASES = {
    'participant_id': 'tracking_id',
    'sample_id': 'tracking_id',
    'fasting_glucose': 'fasting_glucose_mg_dl',
    'glucose': 'fasting_glucose_mg_dl',
    'insulin': 'insulin_uiu_ml',
    'fasting_insulin': 'insulin_uiu_ml',
    'cortisol_serum': 'cortisol_serum_ug_dl',
    'cortisol': 'cortisol_serum_ug_dl',
    'igf1': 'igf1_ng_ml',
    'igf-1': 'igf1_ng_ml',
    'total_cholesterol': 'total_cholesterol_mg_dl',
    'cholesterol': 'total_cholesterol_mg_dl',
    'hdl': 'hdl_mg_dl',
    'ldl': 'ldl_mg_dl',
    'triglycerides': 'triglycerides_mg_dl',
    'tg': 'triglycerides_mg_dl',
    'lab': 'lab_name',
    'report_id': 'lab_report_id',
}


def read_file(filepath):
    """Read Excel or CSV file into DataFrame."""
    ext = os.path.splitext(filepath)[1].lower()
    if ext in ('.xlsx', '.xls'):
        return pd.read_excel(filepath)
    elif ext == '.csv':
        return pd.read_csv(filepath)
    else:
        raise ValueError(f'Unsupported file type: {ext}')


def normalize_columns(df):
    """Normalize column names using aliases."""
    df.columns = [c.strip().lower().replace(' ', '_') for c in df.columns]
    df = df.rename(columns=COLUMN_ALIASES)
    return df


def validate_row(row_num, row, errors):
    """Validate a single row. Returns dict of validated values."""
    values = {}
    for field, (lo, hi) in VALIDATION_RANGES.items():
        val = row.get(field)
        if pd.notna(val):
            try:
                fval = float(val)
                if fval < lo or fval > hi:
                    errors.append(f'Row {row_num}: {field}={fval} outside range [{lo}, {hi}]')
                else:
                    values[field] = fval
            except (ValueError, TypeError):
                errors.append(f'Row {row_num}: {field} non-numeric value "{val}"')
        else:
            values[field] = None
    return values


def main():
    if len(sys.argv) < 2:
        print('Usage: python etl/hormone_import.py <file.xlsx|file.csv> [--dry-run]')
        sys.exit(1)

    filepath = sys.argv[1]
    dry_run = '--dry-run' in sys.argv

    if not os.path.exists(filepath):
        logger.error(f'File not found: {filepath}')
        sys.exit(1)

    app = create_app()
    with app.app_context():
        logger.info(f'Reading {filepath}...')
        df = read_file(filepath)
        df = normalize_columns(df)

        if 'tracking_id' not in df.columns:
            logger.error('File must contain a "tracking_id" column.')
            sys.exit(1)

        batch_id = f'DIAG-{datetime.now().strftime("%Y%m%d-%H%M%S")}'
        errors = []
        imported = 0

        logger.info(f'Processing {len(df)} rows (batch: {batch_id})...')

        for idx, row in df.iterrows():
            row_num = idx + 2  # Excel row number (1-indexed + header)
            tid = str(row.get('tracking_id', '')).strip().upper()

            if not tid:
                errors.append(f'Row {row_num}: Missing tracking_id')
                continue

            participant = db.session.get(Participant, tid)
            if not participant:
                errors.append(f'Row {row_num}: Participant {tid} not found in database')
                continue

            validated = validate_row(row_num, row, errors)

            result = HormoneResult(
                tracking_id=tid,
                lab_name=str(row.get('lab_name', '')).strip() or None,
                lab_report_id=str(row.get('lab_report_id', '')).strip() or None,
                import_batch_id=batch_id,
                import_date=datetime.now(),
                **{k: v for k, v in validated.items() if v is not None},
            )

            db.session.add(result)
            imported += 1

        if errors:
            logger.warning(f'{len(errors)} validation issues:')
            for e in errors[:30]:
                logger.warning(f'  {e}')
            if len(errors) > 30:
                logger.warning(f'  ... and {len(errors) - 30} more')

        if dry_run:
            db.session.rollback()
            logger.info(f'DRY RUN: Would import {imported} records. No changes made.')
        else:
            if imported > 0:
                db.session.commit()
                logger.info(f'Imported {imported} records (batch: {batch_id})')
            else:
                db.session.rollback()
                logger.warning('No records imported.')


if __name__ == '__main__':
    main()
