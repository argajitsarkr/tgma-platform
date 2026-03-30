import os
import uuid
from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required
from werkzeug.utils import secure_filename
import pandas as pd

from app.extensions import db
from app.models import Participant, HormoneResult
from app.utils.decorators import role_required

diagnostics_bp = Blueprint('diagnostics', __name__, url_prefix='/diagnostics')

ALLOWED_EXTENSIONS = {'xlsx', 'xls', 'csv'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@diagnostics_bp.route('/')
@login_required
@role_required('pi', 'co_pi', 'bioinformatician')
def index():
    recent_imports = HormoneResult.query.filter(
        HormoneResult.import_batch_id.isnot(None)
    ).with_entities(
        HormoneResult.import_batch_id,
        HormoneResult.import_date,
        db.func.count(HormoneResult.id)
    ).group_by(
        HormoneResult.import_batch_id, HormoneResult.import_date
    ).order_by(HormoneResult.import_date.desc()).limit(20).all()

    return render_template('diagnostics/import.html', recent_imports=recent_imports)


@diagnostics_bp.route('/upload', methods=['POST'])
@login_required
@role_required('pi', 'co_pi', 'bioinformatician')
def upload():
    if 'file' not in request.files:
        flash('No file uploaded.', 'danger')
        return redirect(url_for('diagnostics.index'))

    file = request.files['file']
    if file.filename == '' or not allowed_file(file.filename):
        flash('Invalid file. Please upload .xlsx, .xls, or .csv.', 'danger')
        return redirect(url_for('diagnostics.index'))

    filename = secure_filename(file.filename)
    upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'diagnostics')
    os.makedirs(upload_dir, exist_ok=True)
    filepath = os.path.join(upload_dir, f"{uuid.uuid4().hex}_{filename}")
    file.save(filepath)

    try:
        if filename.endswith('.csv'):
            df = pd.read_csv(filepath)
        else:
            df = pd.read_excel(filepath)
    except Exception as e:
        flash(f'Error reading file: {e}', 'danger')
        return redirect(url_for('diagnostics.index'))

    # Validate required columns
    required_cols = ['tracking_id']
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        flash(f'Missing required columns: {", ".join(missing)}', 'danger')
        return redirect(url_for('diagnostics.index'))

    # Preview
    preview = df.head(10).to_html(classes='table table-sm table-bordered', index=False)
    return render_template('diagnostics/import.html',
                           preview=preview,
                           filepath=filepath,
                           row_count=len(df),
                           recent_imports=[])


@diagnostics_bp.route('/confirm-import', methods=['POST'])
@login_required
@role_required('pi', 'co_pi', 'bioinformatician')
def confirm_import():
    filepath = request.form.get('filepath', '')
    if not filepath or not os.path.exists(filepath):
        flash('Import file not found.', 'danger')
        return redirect(url_for('diagnostics.index'))

    try:
        if filepath.endswith('.csv'):
            df = pd.read_csv(filepath)
        else:
            df = pd.read_excel(filepath)
    except Exception as e:
        flash(f'Error reading file: {e}', 'danger')
        return redirect(url_for('diagnostics.index'))

    batch_id = f"DIAG-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    errors = []
    imported = 0

    # Column mapping (flexible — maps common header names)
    col_map = {
        'tracking_id': 'tracking_id',
        'lab_name': 'lab_name',
        'fasting_glucose': 'fasting_glucose_mg_dl',
        'fasting_glucose_mg_dl': 'fasting_glucose_mg_dl',
        'insulin': 'insulin_uiu_ml',
        'insulin_uiu_ml': 'insulin_uiu_ml',
        'cortisol_serum': 'cortisol_serum_ug_dl',
        'cortisol_serum_ug_dl': 'cortisol_serum_ug_dl',
        'igf1': 'igf1_ng_ml',
        'igf1_ng_ml': 'igf1_ng_ml',
        'total_cholesterol': 'total_cholesterol_mg_dl',
        'total_cholesterol_mg_dl': 'total_cholesterol_mg_dl',
        'hdl': 'hdl_mg_dl',
        'hdl_mg_dl': 'hdl_mg_dl',
        'ldl': 'ldl_mg_dl',
        'ldl_mg_dl': 'ldl_mg_dl',
        'triglycerides': 'triglycerides_mg_dl',
        'triglycerides_mg_dl': 'triglycerides_mg_dl',
    }

    # Validation ranges
    ranges = {
        'fasting_glucose_mg_dl': (30, 500),
        'insulin_uiu_ml': (0.5, 300),
        'cortisol_serum_ug_dl': (1, 60),
        'igf1_ng_ml': (10, 1000),
        'total_cholesterol_mg_dl': (50, 500),
        'hdl_mg_dl': (5, 150),
        'ldl_mg_dl': (10, 400),
        'triglycerides_mg_dl': (20, 1000),
    }

    for idx, row in df.iterrows():
        tid = str(row.get('tracking_id', '')).strip().upper()
        if not tid:
            errors.append(f'Row {idx + 2}: Missing tracking_id')
            continue

        participant = db.session.get(Participant, tid)
        if not participant:
            errors.append(f'Row {idx + 2}: Participant {tid} not found')
            continue

        result = HormoneResult(
            tracking_id=tid,
            lab_name=str(row.get('lab_name', '')).strip() or None,
            import_batch_id=batch_id,
            import_date=datetime.now(),
        )

        # Map columns
        for src_col, dest_field in col_map.items():
            if src_col in df.columns and dest_field != 'tracking_id':
                val = row.get(src_col)
                if pd.notna(val):
                    # Range validation
                    if dest_field in ranges:
                        lo, hi = ranges[dest_field]
                        try:
                            fval = float(val)
                            if fval < lo or fval > hi:
                                errors.append(f'Row {idx + 2}: {dest_field}={fval} outside range [{lo}, {hi}]')
                                continue
                        except (ValueError, TypeError):
                            errors.append(f'Row {idx + 2}: {dest_field} non-numeric value "{val}"')
                            continue
                    setattr(result, dest_field, val)

        db.session.add(result)
        imported += 1

    if errors and imported == 0:
        db.session.rollback()
        flash(f'Import failed. {len(errors)} errors found.', 'danger')
    else:
        db.session.commit()
        flash(f'Imported {imported} records (batch: {batch_id}). {len(errors)} warnings.', 'success')

    if errors:
        for e in errors[:20]:
            flash(e, 'warning')
        if len(errors) > 20:
            flash(f'... and {len(errors) - 20} more warnings.', 'warning')

    return redirect(url_for('diagnostics.index'))
