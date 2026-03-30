import os
from flask import Blueprint, render_template, request, flash, redirect, url_for, send_file, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app.extensions import db
from app.models import Participant, BloodReport

diagnostics_bp = Blueprint('diagnostics', __name__, url_prefix='/diagnostics')

ALLOWED_EXTENSIONS = {'pdf'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@diagnostics_bp.route('/')
@login_required
def index():
    participants = Participant.query.order_by(Participant.tracking_id).all()
    return render_template('diagnostics/index.html', participants=participants)


@diagnostics_bp.route('/upload/<tracking_id>', methods=['POST'])
@login_required
def upload(tracking_id):
    participant = Participant.query.get_or_404(tracking_id)

    if 'pdf_file' not in request.files:
        flash('No file selected.', 'warning')
        return redirect(url_for('diagnostics.index'))

    file = request.files['pdf_file']
    if file.filename == '':
        flash('No file selected.', 'warning')
        return redirect(url_for('diagnostics.index'))

    if not allowed_file(file.filename):
        flash('Only PDF files are allowed.', 'danger')
        return redirect(url_for('diagnostics.index'))

    # Save file
    upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'blood_reports', tracking_id)
    os.makedirs(upload_dir, exist_ok=True)

    original_filename = secure_filename(file.filename)
    filename = f"{tracking_id}_{original_filename}"
    file_path = os.path.join(upload_dir, filename)
    file.save(file_path)

    notes = request.form.get('notes', '').strip() or None

    report = BloodReport(
        tracking_id=tracking_id,
        filename=filename,
        original_filename=original_filename,
        file_path=file_path,
        uploaded_by=current_user.username,
        notes=notes,
    )
    db.session.add(report)
    db.session.commit()

    flash(f'Blood report uploaded for {tracking_id}.', 'success')
    return redirect(url_for('diagnostics.index'))


@diagnostics_bp.route('/view/<int:report_id>')
@login_required
def view_report(report_id):
    report = BloodReport.query.get_or_404(report_id)
    return send_file(report.file_path, mimetype='application/pdf')


@diagnostics_bp.route('/download/<int:report_id>')
@login_required
def download_report(report_id):
    report = BloodReport.query.get_or_404(report_id)
    return send_file(report.file_path, as_attachment=True, download_name=report.original_filename)


@diagnostics_bp.route('/delete/<int:report_id>', methods=['POST'])
@login_required
def delete_report(report_id):
    report = BloodReport.query.get_or_404(report_id)
    try:
        if os.path.exists(report.file_path):
            os.remove(report.file_path)
    except OSError:
        pass
    db.session.delete(report)
    db.session.commit()
    flash('Report deleted.', 'info')
    return redirect(url_for('diagnostics.index'))
