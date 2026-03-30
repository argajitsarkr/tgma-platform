from flask import Blueprint, render_template, current_app
from flask_login import login_required

from app.extensions import db
from app.models import Participant, Sample, AuditLog

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
@login_required
def index():
    # Enrollment stats
    total_enrolled = Participant.query.filter(
        Participant.enrollment_status.in_(['enrolled', 'completed'])
    ).count()

    by_district = db.session.query(
        Participant.district, db.func.count(Participant.tracking_id)
    ).filter(
        Participant.enrollment_status.in_(['enrolled', 'completed'])
    ).group_by(Participant.district).all()
    district_counts = dict(by_district)

    by_lifestyle = db.session.query(
        Participant.lifestyle_group_assigned, db.func.count(Participant.tracking_id)
    ).filter(
        Participant.enrollment_status.in_(['enrolled', 'completed']),
        Participant.lifestyle_group_assigned.isnot(None)
    ).group_by(Participant.lifestyle_group_assigned).all()
    lifestyle_counts = dict(by_lifestyle)

    by_gender = db.session.query(
        Participant.gender, db.func.count(Participant.tracking_id)
    ).filter(
        Participant.enrollment_status.in_(['enrolled', 'completed'])
    ).group_by(Participant.gender).all()
    gender_counts = dict(by_gender)

    # Sample stats
    total_samples = Sample.query.filter_by(collection_status='collected').count()
    dispatched_samples = Sample.query.filter_by(storage_status='dispatched').count()

    # Participants with complete sample sets
    complete_count = 0
    participants_with_samples = Participant.query.filter(
        Participant.enrollment_status.in_(['enrolled', 'completed'])
    ).all()
    for p in participants_with_samples:
        if p.sample_completeness:
            complete_count += 1

    # Recent activity (last 10 enrollments)
    recent = Participant.query.order_by(
        Participant.created_at.desc()
    ).limit(10).all()

    # Budget tracking
    config = current_app.config
    budget_total = config['BUDGET_SEQUENCING'] + config['BUDGET_HORMONES'] + config['BUDGET_SHIPMENT']
    # Estimate cost per dispatched batch (30L / 5 batches of 32 = 6L per batch)
    cost_per_sample_seq = config['BUDGET_SEQUENCING'] / config['TARGET_SEQUENCING'] if config['TARGET_SEQUENCING'] else 0
    spent_sequencing = dispatched_samples * float(cost_per_sample_seq)

    return render_template('dashboard.html',
                           total_enrolled=total_enrolled,
                           target=config['TARGET_ENROLLMENT'],
                           district_counts=district_counts,
                           district_targets=config['DISTRICT_TARGETS'],
                           lifestyle_counts=lifestyle_counts,
                           gender_counts=gender_counts,
                           total_samples=total_samples,
                           dispatched_samples=dispatched_samples,
                           complete_count=complete_count,
                           recent=recent,
                           budget_total=budget_total,
                           spent_sequencing=spent_sequencing,
                           budget_sequencing=config['BUDGET_SEQUENCING'],
                           budget_hormones=config['BUDGET_HORMONES'],
                           budget_shipment=config['BUDGET_SHIPMENT'])
