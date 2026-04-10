"""Wipe demo data: synthetic participants + ID allocations + KoboSync logs
+ per-participant uploaded documents (files on disk).

Usage:
    python scripts/wipe_data.py --confirm

Run on server:
    sudo docker compose exec web python scripts/wipe_data.py --confirm

This preserves users and the schema. It deletes:
  - All participants (cascades to samples, hormones, anthropometrics,
    documents, etc.)
  - All ID allocations
  - All KoboSync log entries
  - The `{UPLOAD_FOLDER}/participants/` subtree on disk
  - Legacy `{UPLOAD_FOLDER}/blood_reports/` is NOT touched (preserved
    intentionally since the PI may want to keep those files).
"""
import os
import shutil
import sys

# Add project root to path so `from app import ...` works when this script is
# run directly (e.g., `python scripts/wipe_data.py` inside the container).
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.extensions import db
from app.models import Participant, IdAllocation, KoboSyncLog


def main():
    if '--confirm' not in sys.argv:
        print('Refusing to run without --confirm flag.')
        print('This will DELETE all participants, ID allocations, sync logs, and uploaded documents.')
        sys.exit(1)

    app = create_app()
    with app.app_context():
        n_part = Participant.query.count()
        n_alloc = IdAllocation.query.count()
        n_log = KoboSyncLog.query.count()

        print(f'Deleting {n_part} participants (cascades to samples, hormones, documents, etc.)...')
        # Delete one-by-one so SQLAlchemy cascade fires (Query.delete bypasses cascades)
        for p in Participant.query.all():
            db.session.delete(p)

        print(f'Deleting {n_alloc} ID allocations...')
        IdAllocation.query.delete()

        print(f'Deleting {n_log} KoboSync log entries...')
        KoboSyncLog.query.delete()

        db.session.commit()

        # Remove orphaned files on disk — cascade cleaned the DB but not the disk.
        upload_root = app.config.get('UPLOAD_FOLDER')
        if upload_root:
            participants_dir = os.path.join(upload_root, 'participants')
            if os.path.isdir(participants_dir):
                print(f'Removing {participants_dir}...')
                shutil.rmtree(participants_dir, ignore_errors=True)
            else:
                print(f'No participants/ folder under {upload_root} — nothing to remove.')

        print('Wipe complete. Users, schema, and blood_reports/ folder preserved.')


if __name__ == '__main__':
    main()
