#!/usr/bin/env python3
"""One-shot upgrade: expand the participants.district CHECK constraint to include
the 3 districts added in XLSForm v3 (NT, GT, UK).

Fresh DBs pick this up automatically via db.create_all(). This script exists for
already-deployed PostgreSQL instances where the old 3-district constraint is in place.

Idempotent: safe to re-run.

Usage:
    sudo docker compose exec web python scripts/upgrade_district_constraint.py
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import text
from app import create_app
from app.extensions import db


NEW_DISTRICTS_SQL = """
ALTER TABLE participants DROP CONSTRAINT IF EXISTS ck_participants_district;
ALTER TABLE participants ADD CONSTRAINT ck_participants_district
    CHECK (district IN ('WT', 'ST', 'DL', 'NT', 'GT', 'UK'));
"""


def main():
    app = create_app(os.environ.get('FLASK_CONFIG', 'production'))
    with app.app_context():
        with db.engine.begin() as conn:
            conn.execute(text(NEW_DISTRICTS_SQL))
        print('OK: ck_participants_district now allows WT, ST, DL, NT, GT, UK.')


if __name__ == '__main__':
    main()
