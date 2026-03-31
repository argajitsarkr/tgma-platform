"""KoboToolbox sync route — manual "Sync Now" button + sync log viewer."""

import json
from flask import Blueprint, render_template, flash, redirect, url_for, current_app, request
from flask_login import login_required, current_user

from app.extensions import db
from app.models import KoboSyncLog
from app.utils.decorators import role_required

kobo_bp = Blueprint('kobo', __name__, url_prefix='/kobo')


@kobo_bp.route('/')
@login_required
@role_required('pi', 'co_pi', 'bioinformatician')
def index():
    """Show sync dashboard with log history."""
    logs = KoboSyncLog.query.order_by(KoboSyncLog.started_at.desc()).limit(50).all()

    # Parse details_json for the most recent successful sync
    latest_details = []
    for log in logs:
        if log.status == 'success' and log.details_json:
            try:
                latest_details = json.loads(log.details_json)
            except (json.JSONDecodeError, TypeError):
                latest_details = []
            break

    return render_template('kobo/sync.html',
                           logs=logs,
                           latest_details=latest_details)


@kobo_bp.route('/sync', methods=['POST'])
@login_required
@role_required('pi', 'co_pi', 'bioinformatician')
def trigger_sync():
    """Handle the 'Sync Now' button click."""
    full_sync = request.form.get('full_sync') == '1'

    # Import here to avoid circular imports
    import sys
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    from etl.kobo_sync import run_sync

    result = run_sync(
        app=current_app._get_current_object(),
        triggered_by=current_user.username,
        full_sync=full_sync,
    )

    if result.status == 'success':
        flash(
            f'Sync complete: {result.inserted} new, {result.updated} updated, '
            f'{result.skipped} skipped out of {result.total_fetched} submissions.',
            'success'
        )
    elif result.status == 'failed':
        flash(f'Sync failed: {result.error_message}', 'danger')
    else:
        flash('Sync finished with unknown status.', 'warning')

    return redirect(url_for('kobo.index'))


@kobo_bp.route('/log/<int:log_id>')
@login_required
@role_required('pi', 'co_pi', 'bioinformatician')
def log_detail(log_id):
    """Show detailed results for a specific sync run."""
    log = KoboSyncLog.query.get_or_404(log_id)

    details = []
    if log.details_json:
        try:
            details = json.loads(log.details_json)
        except (json.JSONDecodeError, TypeError):
            details = []

    return render_template('kobo/log_detail.html', log=log, details=details)
