import io
import csv
from datetime import date

from flask import Blueprint, render_template, Response, current_app
from flask_login import login_required

from app.extensions import db
from app.models import Participant, Sample, HormoneResult, SequencingResult
from app.utils.decorators import role_required

reports_bp = Blueprint('reports', __name__, url_prefix='/reports')


@reports_bp.route('/')
@login_required
@role_required('pi', 'co_pi', 'bioinformatician')
def index():
    return render_template('reports/index.html')


@reports_bp.route('/icmr-progress')
@login_required
@role_required('pi', 'co_pi')
def icmr_progress():
    config = current_app.config
    total = Participant.query.filter(
        Participant.enrollment_status.in_(['enrolled', 'completed'])
    ).count()

    by_district = dict(db.session.query(
        Participant.district, db.func.count(Participant.tracking_id)
    ).filter(
        Participant.enrollment_status.in_(['enrolled', 'completed'])
    ).group_by(Participant.district).all())

    by_lifestyle = dict(db.session.query(
        Participant.lifestyle_group_assigned, db.func.count(Participant.tracking_id)
    ).filter(
        Participant.enrollment_status.in_(['enrolled', 'completed']),
        Participant.lifestyle_group_assigned.isnot(None)
    ).group_by(Participant.lifestyle_group_assigned).all())

    # Samples
    total_samples = Sample.query.filter_by(collection_status='collected').count()
    dispatched = Sample.query.filter_by(storage_status='dispatched').count()
    stool_collected = Sample.query.filter_by(sample_type='stool', collection_status='collected').count()

    # Hormone results
    hormone_count = db.session.query(
        db.func.count(db.distinct(HormoneResult.tracking_id))
    ).scalar()

    # Sequencing
    seq_count = db.session.query(
        db.func.count(db.distinct(SequencingResult.tracking_id))
    ).scalar()

    return render_template('reports/icmr_progress.html',
                           total=total,
                           target=config['TARGET_ENROLLMENT'],
                           by_district=by_district,
                           district_targets=config['DISTRICT_TARGETS'],
                           by_lifestyle=by_lifestyle,
                           total_samples=total_samples,
                           dispatched=dispatched,
                           stool_collected=stool_collected,
                           target_sequencing=config['TARGET_SEQUENCING'],
                           hormone_count=hormone_count,
                           seq_count=seq_count,
                           budget_sequencing=config['BUDGET_SEQUENCING'],
                           budget_hormones=config['BUDGET_HORMONES'],
                           budget_shipment=config['BUDGET_SHIPMENT'])


@reports_bp.route('/enrollment-csv')
@login_required
@role_required('pi', 'co_pi', 'bioinformatician')
def enrollment_csv():
    """Export enrollment data as CSV."""
    participants = Participant.query.order_by(Participant.tracking_id).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['tracking_id', 'full_name', 'age', 'gender', 'district',
                     'lifestyle_group', 'enrollment_date', 'enrollment_status'])

    for p in participants:
        writer.writerow([
            p.tracking_id, p.full_name, p.age, p.gender, p.display_district,
            p.lifestyle_group_assigned or '', p.enrollment_date or '', p.enrollment_status,
        ])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=enrollment_report_{date.today()}.csv'}
    )


@reports_bp.route('/sample-inventory-csv')
@login_required
@role_required('pi', 'co_pi', 'bioinformatician')
def sample_inventory_csv():
    """Export sample inventory as CSV."""
    samples = Sample.query.order_by(Sample.tracking_id, Sample.sample_type).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['sample_id', 'tracking_id', 'sample_type', 'collection_status',
                     'storage_status', 'freezer_id', 'rack', 'shelf', 'box_number',
                     'dispatch_date', 'dispatched_to'])

    for s in samples:
        writer.writerow([
            s.sample_id, s.tracking_id, s.sample_type, s.collection_status,
            s.storage_status, s.freezer_id or '', s.rack or '', s.shelf or '',
            s.box_number or '', s.dispatch_date or '', s.dispatched_to or '',
        ])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=sample_inventory_{date.today()}.csv'}
    )
