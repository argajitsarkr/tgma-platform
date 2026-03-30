#!/usr/bin/env python3
"""Import sequencing results from vendor manifest (TSV/CSV) into PostgreSQL.

Nucleome Informatics provides a manifest file with per-sample sequencing stats
after each batch run. This script parses that manifest and populates the
sequencing_results table.

Usage:
    python etl/sequencing_import.py path/to/manifest.tsv
    python etl/sequencing_import.py path/to/manifest.csv --dry-run
"""

import os
import sys
import logging
from datetime import datetime, date

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.extensions import db
from app.models import Participant, Sample, SequencingResult

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Column name aliases
COLUMN_ALIASES = {
    'sample_id': 'tracking_id',
    'participant_id': 'tracking_id',
    'sample': 'tracking_id',
    'batch_id': 'sequencing_batch_id',
    'batch': 'sequencing_batch_id',
    'reads': 'total_reads',
    'total_reads_raw': 'total_reads',
    'reads_after_qc': 'reads_post_qc',
    'clean_reads': 'reads_post_qc',
    'host_removal': 'host_removal_pct',
    'host_pct': 'host_removal_pct',
    'contigs': 'assembly_contigs',
    'n50': 'assembly_n50',
    'taxonomy_path': 'taxonomy_profile_path',
    'taxonomy_file': 'taxonomy_profile_path',
    'functional_path': 'functional_profile_path',
    'functional_file': 'functional_profile_path',
    'mags': 'mag_count',
    'total_mags': 'mag_count',
    'hq_mags': 'hq_mag_count',
    'mq_mags': 'mq_mag_count',
    'qc_status': 'qc_status',
    'received_date': 'data_received_date',
}


def read_file(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.tsv':
        return pd.read_csv(filepath, sep='\t')
    elif ext == '.csv':
        return pd.read_csv(filepath)
    elif ext in ('.xlsx', '.xls'):
        return pd.read_excel(filepath)
    else:
        raise ValueError(f'Unsupported file type: {ext}')


def normalize_columns(df):
    df.columns = [c.strip().lower().replace(' ', '_') for c in df.columns]
    df = df.rename(columns=COLUMN_ALIASES)
    return df


def safe_int(val):
    if pd.isna(val):
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def safe_float(val):
    if pd.isna(val):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def main():
    if len(sys.argv) < 2:
        print('Usage: python etl/sequencing_import.py <manifest.tsv|csv|xlsx> [--dry-run]')
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
            logger.error('Manifest must contain a "tracking_id" (or "sample_id") column.')
            sys.exit(1)

        errors = []
        imported = 0

        logger.info(f'Processing {len(df)} rows...')

        for idx, row in df.iterrows():
            row_num = idx + 2
            tid = str(row.get('tracking_id', '')).strip().upper()

            # Strip sample suffix if present (e.g., TGMA-WT-F-0037-STL → TGMA-WT-F-0037)
            if tid.count('-') > 3:
                tid = '-'.join(tid.split('-')[:4])

            if not tid:
                errors.append(f'Row {row_num}: Missing tracking_id')
                continue

            participant = db.session.get(Participant, tid)
            if not participant:
                errors.append(f'Row {row_num}: Participant {tid} not found')
                continue

            result = SequencingResult(
                tracking_id=tid,
                vendor='Nucleome Informatics',
                sequencing_batch_id=str(row.get('sequencing_batch_id', '')).strip() or None,
                total_reads=safe_int(row.get('total_reads')),
                reads_post_qc=safe_int(row.get('reads_post_qc')),
                host_removal_pct=safe_float(row.get('host_removal_pct')),
                assembly_contigs=safe_int(row.get('assembly_contigs')),
                assembly_n50=safe_int(row.get('assembly_n50')),
                taxonomy_profile_path=str(row.get('taxonomy_profile_path', '')).strip() or None,
                functional_profile_path=str(row.get('functional_profile_path', '')).strip() or None,
                mag_count=safe_int(row.get('mag_count')),
                hq_mag_count=safe_int(row.get('hq_mag_count')),
                mq_mag_count=safe_int(row.get('mq_mag_count')),
                qc_status=str(row.get('qc_status', 'pending')).strip().lower() or 'pending',
                data_received_date=date.today(),
            )

            db.session.add(result)
            imported += 1

        if errors:
            logger.warning(f'{len(errors)} issues:')
            for e in errors[:20]:
                logger.warning(f'  {e}')

        if dry_run:
            db.session.rollback()
            logger.info(f'DRY RUN: Would import {imported} sequencing records.')
        else:
            if imported > 0:
                db.session.commit()
                logger.info(f'Imported {imported} sequencing records.')
            else:
                db.session.rollback()
                logger.warning('No records imported.')


if __name__ == '__main__':
    main()
