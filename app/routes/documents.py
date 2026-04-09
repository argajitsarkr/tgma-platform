"""Per-participant document vault — scanned consent/assent/info-sheet/
questionnaire forms, photos, and a unified view that also merges in the
legacy BloodReport table.

Folder layout on server:
    {UPLOAD_FOLDER}/participants/{tracking_id}/{doc_type}/{timestamp}_{secure_name}

Uploads and deletes are gated to PI/Co-PI/Bioinformatician.
View and download are available to any logged-in user.
"""
import logging
import os
from datetime import datetime

from flask import (Blueprint, render_template, request, flash, redirect,
                   url_for, send_file, current_app, abort)
from flask_login import login_required, current_user
from sqlalchemy import func, inspect
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import Participant, BloodReport, ParticipantDocument
from app.utils.decorators import role_required
from app.utils.helpers import validate_tracking_id

logger = logging.getLogger(__name__)
documents_bp = Blueprint('documents', __name__, url_prefix='/documents')

ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png'}
EXT_MIME = {
    'pdf':  'application/pdf',
    'jpg':  'image/jpeg',
    'jpeg': 'image/jpeg',
    'png':  'image/png',
}

DOC_TYPE_LABELS = {
    'consent':           'Consent Form (Parent)',
    'assent':            'Assent Form (Participant)',
    'information_sheet': 'Information Sheet',
    'questionnaire':     'Questionnaire',
    'image':             'Image / Photo',
    'other':             'Other Document',
}
DOC_TYPE_ICONS = {
    'consent':           'bi-file-earmark-text',
    'assent':            'bi-file-earmark-check',
    'information_sheet': 'bi-file-earmark-richtext',
    'questionnaire':     'bi-clipboard-data',
    'image':             'bi-image',
    'other':             'bi-file-earmark',
}


def _ensure_table():
    """Create participant_documents table if it doesn't exist yet (first deploy safety)."""
    inspector = inspect(db.engine)
    if not inspector.has_table('participant_documents'):
        logger.info('Creating missing participant_documents table...')
        ParticipantDocument.__table__.create(db.engine)


def _allowed(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _human_size(num_bytes):
    if num_bytes is None:
        return '—'
    for unit in ('B', 'KB', 'MB', 'GB'):
        if num_bytes < 1024:
            return f'{num_bytes:.0f} {unit}' if unit == 'B' else f'{num_bytes:.1f} {unit}'
        num_bytes /= 1024
    return f'{num_bytes:.1f} TB'


@documents_bp.route('/')
@login_required
def index():
    """Landing page — all participants with blood report + document counts."""
    _ensure_table()

    # Blood report counts per tracking_id
    br_counts = dict(
        db.session.query(BloodReport.tracking_id, func.count(BloodReport.id))
                  .group_by(BloodReport.tracking_id).all()
    )
    # ParticipantDocument counts per tracking_id
    pd_counts = dict(
        db.session.query(ParticipantDocument.tracking_id, func.count(ParticipantDocument.id))
                  .group_by(ParticipantDocument.tracking_id).all()
    )

    participants = Participant.query.order_by(Participant.tracking_id).all()
    rows = []
    for p in participants:
        br = br_counts.get(p.tracking_id, 0)
        pd = pd_counts.get(p.tracking_id, 0)
        rows.append({
            'p': p,
            'blood_reports': br,
            'other_docs': pd,
            'total': br + pd,
        })

    total_all = sum(r['total'] for r in rows)
    with_any = sum(1 for r in rows if r['total'] > 0)

    return render_template('documents/index.html',
                           rows=rows,
                           total_all=total_all,
                           with_any=with_any)


@documents_bp.route('/<tracking_id>')
@login_required
def vault(tracking_id):
    """Per-participant vault — merged view of ParticipantDocument + BloodReport."""
    _ensure_table()

    # Path traversal guard — even though Flask route converters are safe,
    # the tracking_id feeds os.path.join in the upload handler. Enforce format here too.
    if not validate_tracking_id(tracking_id):
        flash('Invalid tracking ID format.', 'danger')
        return redirect(url_for('documents.index'))

    participant = db.session.get(Participant, tracking_id)
    if not participant:
        flash('Participant not found.', 'danger')
        return redirect(url_for('documents.index'))

    docs = (ParticipantDocument.query
            .filter_by(tracking_id=tracking_id)
            .order_by(ParticipantDocument.uploaded_at.desc())
            .all())

    # Group by doc_type
    grouped = {t: [] for t in ParticipantDocument.DOC_TYPES}
    for d in docs:
        grouped.setdefault(d.doc_type, []).append(d)

    blood_reports = (BloodReport.query
                     .filter_by(tracking_id=tracking_id)
                     .order_by(BloodReport.uploaded_at.desc())
                     .all())

    return render_template('documents/vault.html',
                           p=participant,
                           grouped=grouped,
                           blood_reports=blood_reports,
                           doc_type_labels=DOC_TYPE_LABELS,
                           doc_type_icons=DOC_TYPE_ICONS,
                           human_size=_human_size)


@documents_bp.route('/<tracking_id>/upload', methods=['POST'])
@login_required
@role_required('pi', 'co_pi', 'bioinformatician')
def upload(tracking_id):
    """Upload a new document. Role-gated."""
    _ensure_table()

    # Path traversal guard
    if not validate_tracking_id(tracking_id):
        flash('Invalid tracking ID format.', 'danger')
        return redirect(url_for('documents.index'))

    participant = db.session.get(Participant, tracking_id)
    if not participant:
        flash('Participant not found.', 'danger')
        return redirect(url_for('documents.index'))

    doc_type = request.form.get('doc_type', '').strip()
    if doc_type not in ParticipantDocument.DOC_TYPES:
        flash('Invalid document type.', 'danger')
        return redirect(url_for('documents.vault', tracking_id=tracking_id))

    if 'file' not in request.files:
        flash('No file selected.', 'warning')
        return redirect(url_for('documents.vault', tracking_id=tracking_id))

    file = request.files['file']
    if not file or file.filename == '':
        flash('No file selected.', 'warning')
        return redirect(url_for('documents.vault', tracking_id=tracking_id))

    if not _allowed(file.filename):
        flash('Only PDF, JPG, and PNG files are allowed.', 'danger')
        return redirect(url_for('documents.vault', tracking_id=tracking_id))

    original_filename = secure_filename(file.filename) or 'upload'
    ext = original_filename.rsplit('.', 1)[1].lower()
    stamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    filename = f'{stamp}_{original_filename}'

    upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'],
                              'participants', tracking_id, doc_type)
    os.makedirs(upload_dir, exist_ok=True)

    file_path = os.path.join(upload_dir, filename)
    try:
        file.save(file_path)
    except OSError as exc:
        logger.exception('Failed to save upload for %s', tracking_id)
        flash(f'Failed to save file: {exc}', 'danger')
        return redirect(url_for('documents.vault', tracking_id=tracking_id))

    try:
        file_size = os.path.getsize(file_path)
    except OSError:
        file_size = None

    notes = request.form.get('notes', '').strip() or None

    doc = ParticipantDocument(
        tracking_id=tracking_id,
        doc_type=doc_type,
        filename=filename,
        original_filename=original_filename,
        file_path=file_path,
        file_size=file_size,
        mime_type=EXT_MIME.get(ext),
        uploaded_by=current_user.username,
        notes=notes,
    )
    db.session.add(doc)
    db.session.commit()

    flash(f'{DOC_TYPE_LABELS[doc_type]} uploaded for {tracking_id}.', 'success')
    return redirect(url_for('documents.vault', tracking_id=tracking_id))


@documents_bp.route('/view/<int:doc_id>')
@login_required
def view(doc_id):
    doc = ParticipantDocument.query.get_or_404(doc_id)
    if not os.path.exists(doc.file_path):
        flash('File is missing on disk.', 'danger')
        return redirect(url_for('documents.vault', tracking_id=doc.tracking_id))
    return send_file(doc.file_path, mimetype=doc.mime_type or 'application/octet-stream')


@documents_bp.route('/download/<int:doc_id>')
@login_required
def download(doc_id):
    doc = ParticipantDocument.query.get_or_404(doc_id)
    if not os.path.exists(doc.file_path):
        flash('File is missing on disk.', 'danger')
        return redirect(url_for('documents.vault', tracking_id=doc.tracking_id))
    return send_file(doc.file_path, as_attachment=True, download_name=doc.original_filename)


@documents_bp.route('/<int:doc_id>/delete', methods=['POST'])
@login_required
@role_required('pi', 'co_pi', 'bioinformatician')
def delete(doc_id):
    doc = ParticipantDocument.query.get_or_404(doc_id)
    tracking_id = doc.tracking_id
    try:
        if os.path.exists(doc.file_path):
            os.remove(doc.file_path)
    except OSError:
        logger.warning('Could not remove file %s', doc.file_path)

    db.session.delete(doc)
    db.session.commit()
    flash('Document deleted.', 'info')
    return redirect(url_for('documents.vault', tracking_id=tracking_id))
