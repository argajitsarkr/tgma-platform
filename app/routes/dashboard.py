from flask import Blueprint, render_template, current_app
from flask_login import login_required

from app.extensions import db
from app.models import Participant, Sample

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
@login_required
def index():
    config = current_app.config
    target_year1 = config.get('TARGET_SAMPLES_YEAR1', 160)

    # Enrollment stats
    total_enrolled = Participant.query.filter(
        Participant.enrollment_status.in_(['enrolled', 'completed'])
    ).count()

    # Samples collected (stool with collection_status='collected')
    samples_collected = Sample.query.filter(
        Sample.sample_type == 'stool',
        Sample.collection_status == 'collected',
    ).count()

    # Batches dispatched (distinct dispatch_manifest_id where not null)
    batches_dispatched = db.session.query(
        db.func.count(db.distinct(Sample.dispatch_manifest_id))
    ).filter(
        Sample.dispatch_manifest_id.isnot(None)
    ).scalar() or 0

    # Pending = enrolled participants who don't have a collected stool sample yet
    participants_with_stool = db.session.query(Sample.tracking_id).filter(
        Sample.sample_type == 'stool',
        Sample.collection_status == 'collected',
    ).distinct().subquery()

    pending_samples = Participant.query.filter(
        Participant.enrollment_status.in_(['enrolled', 'completed']),
        ~Participant.tracking_id.in_(db.session.query(participants_with_stool))
    ).count()

    # District counts
    by_district = db.session.query(
        Participant.district, db.func.count(Participant.tracking_id)
    ).filter(
        Participant.enrollment_status.in_(['enrolled', 'completed'])
    ).group_by(Participant.district).all()
    district_counts = dict(by_district)

    # Gender counts
    by_gender = db.session.query(
        Participant.gender, db.func.count(Participant.tracking_id)
    ).filter(
        Participant.enrollment_status.in_(['enrolled', 'completed'])
    ).group_by(Participant.gender).all()
    gender_counts = dict(by_gender)

    # Lifestyle counts
    by_lifestyle = db.session.query(
        Participant.lifestyle_group_assigned, db.func.count(Participant.tracking_id)
    ).filter(
        Participant.enrollment_status.in_(['enrolled', 'completed']),
        Participant.lifestyle_group_assigned.isnot(None)
    ).group_by(Participant.lifestyle_group_assigned).all()
    lifestyle_counts = dict(by_lifestyle)

    return render_template('dashboard.html',
                           total_enrolled=total_enrolled,
                           samples_collected=samples_collected,
                           batches_dispatched=batches_dispatched,
                           pending_samples=pending_samples,
                           district_counts=district_counts,
                           gender_counts=gender_counts,
                           lifestyle_counts=lifestyle_counts,
                           target_year1=target_year1)
