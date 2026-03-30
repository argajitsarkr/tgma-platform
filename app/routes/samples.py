from collections import OrderedDict
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required
from datetime import date

from app.extensions import db
from app.models import Sample, Participant
from app.utils.decorators import role_required
from app.utils.helpers import generate_sample_id

samples_bp = Blueprint('samples', __name__, url_prefix='/samples')

ALLOWED_SAMPLE_TYPES = ['stool', 'saliva_cortisol']


@samples_bp.route('/')
@login_required
def tracker():
    sample_type = request.args.get('type', '')
    storage_status = request.args.get('storage_status', '')
    dispatch_status = request.args.get('dispatch', '')

    query = Sample.query

    if sample_type:
        query = query.filter_by(sample_type=sample_type)
    if storage_status:
        query = query.filter_by(storage_status=storage_status)
    if dispatch_status == 'dispatched':
        query = query.filter(Sample.dispatch_date.isnot(None))
    elif dispatch_status == 'not_dispatched':
        query = query.filter(Sample.dispatch_date.is_(None))

    samples = query.order_by(Sample.created_at.desc()).all()
    return render_template('samples/tracker.html', samples=samples)


@samples_bp.route('/<sample_id>')
@login_required
def detail(sample_id):
    sample = db.session.get(Sample, sample_id)
    if not sample:
        flash('Sample not found.', 'danger')
        return redirect(url_for('samples.tracker'))
    return render_template('samples/detail.html', sample=sample)


@samples_bp.route('/register', methods=['GET', 'POST'])
@login_required
def register():
    if request.method == 'POST':
        tracking_id = request.form.get('tracking_id', '').strip().upper()
        participant = db.session.get(Participant, tracking_id)
        if not participant:
            flash(f'Participant {tracking_id} not found.', 'danger')
            return redirect(url_for('samples.register'))

        sample_types = request.form.getlist('sample_types')
        # Only allow permitted sample types
        sample_types = [st for st in sample_types if st in ALLOWED_SAMPLE_TYPES]
        if not sample_types:
            flash('No valid sample types selected.', 'warning')
            return redirect(url_for('samples.register'))

        registered = []
        for st in sample_types:
            sample_id = generate_sample_id(tracking_id, st)
            if db.session.get(Sample, sample_id):
                flash(f'Sample {sample_id} already exists.', 'warning')
                continue
            sample = Sample(
                sample_id=sample_id,
                tracking_id=tracking_id,
                sample_type=st,
                collection_status='collected',
                storage_status='stored',
                storage_date=date.today(),
            )
            db.session.add(sample)
            registered.append(sample_id)

        if registered:
            db.session.commit()
            flash(f'Registered {len(registered)} samples: {", ".join(registered)}', 'success')

        return redirect(url_for('participants.detail', tracking_id=tracking_id))

    participants = Participant.query.filter(
        Participant.enrollment_status.in_(['enrolled', 'completed'])
    ).order_by(Participant.tracking_id).all()
    return render_template('samples/register.html',
                           participants=participants,
                           allowed_sample_types=ALLOWED_SAMPLE_TYPES)


@samples_bp.route('/freezer')
@login_required
def freezer():
    samples = Sample.query.filter(
        Sample.storage_status == 'stored',
        Sample.freezer_id.isnot(None)
    ).order_by(Sample.shelf, Sample.box_number, Sample.box_row, Sample.box_column).all()

    # Group by shelf (1-4) then by box_name (box_number, e.g. "WT-MAR26")
    shelves = OrderedDict()
    for s in samples:
        shelf_key = s.shelf or 'Unassigned'
        box_key = s.box_number or 'Unassigned'
        if shelf_key not in shelves:
            shelves[shelf_key] = OrderedDict()
        if box_key not in shelves[shelf_key]:
            shelves[shelf_key][box_key] = []
        shelves[shelf_key][box_key].append(s)

    return render_template('samples/freezer.html', shelves=shelves)


@samples_bp.route('/dispatch', methods=['GET', 'POST'])
@login_required
@role_required('pi', 'co_pi', 'bioinformatician')
def dispatch():
    if request.method == 'POST':
        sample_ids = request.form.getlist('sample_ids')
        vendor = request.form.get('vendor', 'Nucleome Informatics')
        tracking_number = request.form.get('tracking_number', '').strip()
        manifest_id = request.form.get('manifest_id', '').strip()

        if not sample_ids:
            flash('No samples selected.', 'warning')
            return redirect(url_for('samples.dispatch'))

        count = 0
        for sid in sample_ids:
            sample = db.session.get(Sample, sid)
            if sample and sample.storage_status == 'stored':
                sample.storage_status = 'dispatched'
                sample.dispatched_to = vendor
                sample.dispatch_date = date.today()
                sample.dispatch_tracking_number = tracking_number
                sample.dispatch_manifest_id = manifest_id
                count += 1

        db.session.commit()
        flash(f'Dispatched {count} samples to {vendor}.', 'success')
        return redirect(url_for('samples.tracker'))

    # Show stored stool samples eligible for dispatch
    eligible = Sample.query.filter_by(
        sample_type='stool', storage_status='stored'
    ).order_by(Sample.tracking_id).all()
    return render_template('samples/dispatch.html', eligible=eligible)
