"""Wipe demo data: synthetic participants + ID allocations + KoboSync logs.

Usage:
    python scripts/wipe_data.py --confirm

Run on server:
    sudo docker compose exec web python scripts/wipe_data.py --confirm

This preserves users and the schema. It deletes:
  - All participants (cascades to samples, hormones, anthropometrics, etc.)
  - All ID allocations
  - All KoboSync log entries
"""
import sys

from app import create_app
from app.extensions import db
from app.models import Participant, IdAllocation, KoboSyncLog


def main():
    if '--confirm' not in sys.argv:
        print('Refusing to run without --confirm flag.')
        print('This will DELETE all participants, ID allocations, and sync logs.')
        sys.exit(1)

    app = create_app()
    with app.app_context():
        n_part = Participant.query.count()
        n_alloc = IdAllocation.query.count()
        n_log = KoboSyncLog.query.count()

        print(f'Deleting {n_part} participants (cascades to samples, hormones, etc.)...')
        # Delete one-by-one so SQLAlchemy cascade fires (Query.delete bypasses cascades)
        for p in Participant.query.all():
            db.session.delete(p)

        print(f'Deleting {n_alloc} ID allocations...')
        IdAllocation.query.delete()

        print(f'Deleting {n_log} KoboSync log entries...')
        KoboSyncLog.query.delete()

        db.session.commit()
        print('Wipe complete. Users and schema preserved.')


if __name__ == '__main__':
    main()
