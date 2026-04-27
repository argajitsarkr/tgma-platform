#!/usr/bin/env python3
"""One-shot upgrade: expand the samples.sample_type CHECK constraint to include
`saliva_cortisol` (the dedicated saliva-cortisol sample type used by the
Register Samples form).

Background: the original CHECK constraint was emitted by db.create_all() with
the older 8-type list. The platform later switched to a simplified two-type
workflow (stool + saliva_cortisol) but the CHECK was never updated on
already-deployed PostgreSQL instances, so any insert with sample_type =
'saliva_cortisol' raised IntegrityError → Flask 500.

Fresh DBs pick this up automatically via db.create_all(). This script exists
for already-deployed PostgreSQL instances. Idempotent: safe to re-run.

Usage:
    sudo docker compose exec web python scripts/upgrade_sample_type_constraint.py
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import text
from app import create_app
from app.extensions import db


SAMPLE_TYPE_CONSTRAINT_SQL = """
ALTER TABLE samples DROP CONSTRAINT IF EXISTS ck_samples_type;
ALTER TABLE samples ADD CONSTRAINT ck_samples_type
    CHECK (sample_type IN ('stool', 'blood', 'saliva_1', 'saliva_2', 'saliva_3', 'saliva_4',
                            'saliva_cortisol', 'dna_extract', 'serum'));
"""


def main():
    app = create_app(os.environ.get('FLASK_CONFIG', 'production'))
    with app.app_context():
        with db.engine.begin() as conn:
            conn.execute(text(SAMPLE_TYPE_CONSTRAINT_SQL))
        print('OK: ck_samples_type now allows saliva_cortisol.')


if __name__ == '__main__':
    main()
