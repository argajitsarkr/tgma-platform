from flask import Blueprint, render_template
from flask_login import login_required
from sqlalchemy import text

from app.extensions import db
from app.models import Participant, Anthropometrics, Sample

quality_bp = Blueprint('quality', __name__, url_prefix='/quality')


@quality_bp.route('/')
@login_required
def dashboard():
    # Missing data analysis
    total_participants = Participant.query.count()

    # Key fields to check for completeness
    missing_fields = {}
    field_checks = {
        'age': Participant.query.filter(Participant.age.is_(None)).count(),
        'dob': Participant.query.filter(Participant.dob.is_(None)).count(),
        'village_town': Participant.query.filter(
            db.or_(Participant.village_town.is_(None), Participant.village_town == '')
        ).count(),
        'guardian_phone': Participant.query.filter(
            db.or_(Participant.guardian_phone.is_(None), Participant.guardian_phone == '')
        ).count(),
        'lifestyle_group': Participant.query.filter(
            Participant.lifestyle_group_assigned.is_(None)
        ).count(),
        'gps_latitude': Participant.query.filter(Participant.gps_latitude.is_(None)).count(),
        'gps_longitude': Participant.query.filter(Participant.gps_longitude.is_(None)).count(),
        'consent_parent': Participant.query.filter(Participant.consent_parent == False).count(),
    }

    # GPS out-of-bounds
    gps_issues = Participant.query.filter(
        Participant.gps_latitude.isnot(None),
        Participant.gps_longitude.isnot(None),
        db.or_(
            Participant.gps_latitude < 22.9,
            Participant.gps_latitude > 24.5,
            Participant.gps_longitude < 91.1,
            Participant.gps_longitude > 92.3,
        )
    ).all()

    # Anthropometric outliers (3 SD)
    outliers = []
    anthro_stats = db.session.query(
        db.func.avg(Anthropometrics.height_cm).label('avg_h'),
        db.func.stddev(Anthropometrics.height_cm).label('sd_h'),
        db.func.avg(Anthropometrics.weight_kg).label('avg_w'),
        db.func.stddev(Anthropometrics.weight_kg).label('sd_w'),
    ).first()

    if anthro_stats and anthro_stats.sd_h and anthro_stats.sd_w:
        avg_h, sd_h = float(anthro_stats.avg_h), float(anthro_stats.sd_h)
        avg_w, sd_w = float(anthro_stats.avg_w), float(anthro_stats.sd_w)

        if sd_h > 0:
            height_outliers = Anthropometrics.query.filter(
                Anthropometrics.height_cm.isnot(None),
                db.or_(
                    Anthropometrics.height_cm < avg_h - 3 * sd_h,
                    Anthropometrics.height_cm > avg_h + 3 * sd_h,
                )
            ).all()
            for a in height_outliers:
                outliers.append({
                    'tracking_id': a.tracking_id,
                    'field': 'height_cm',
                    'value': float(a.height_cm),
                    'z_score': round((float(a.height_cm) - avg_h) / sd_h, 2),
                })

        if sd_w > 0:
            weight_outliers = Anthropometrics.query.filter(
                Anthropometrics.weight_kg.isnot(None),
                db.or_(
                    Anthropometrics.weight_kg < avg_w - 3 * sd_w,
                    Anthropometrics.weight_kg > avg_w + 3 * sd_w,
                )
            ).all()
            for a in weight_outliers:
                outliers.append({
                    'tracking_id': a.tracking_id,
                    'field': 'weight_kg',
                    'value': float(a.weight_kg),
                    'z_score': round((float(a.weight_kg) - avg_w) / sd_w, 2),
                })

    # Duplicate detection (same name + DOB)
    duplicates = []
    dup_query = db.session.query(
        Participant.full_name, Participant.dob, db.func.count(Participant.tracking_id)
    ).filter(
        Participant.full_name.isnot(None),
        Participant.dob.isnot(None)
    ).group_by(
        Participant.full_name, Participant.dob
    ).having(db.func.count(Participant.tracking_id) > 1).all()

    for name, dob, cnt in dup_query:
        participants = Participant.query.filter_by(full_name=name, dob=dob).all()
        duplicates.append({
            'name': name,
            'dob': dob,
            'count': cnt,
            'tracking_ids': [p.tracking_id for p in participants],
        })

    # Sample completeness
    incomplete_participants = []
    enrolled = Participant.query.filter(
        Participant.enrollment_status.in_(['enrolled', 'completed'])
    ).all()
    for p in enrolled:
        collected_types = {s.sample_type for s in p.samples if s.collection_status == 'collected'}
        required = {'stool', 'blood', 'saliva_1', 'saliva_2', 'saliva_3', 'saliva_4'}
        missing = required - collected_types
        if missing:
            incomplete_participants.append({
                'tracking_id': p.tracking_id,
                'full_name': p.full_name,
                'missing_samples': sorted(missing),
            })

    return render_template('quality/dashboard.html',
                           total_participants=total_participants,
                           field_checks=field_checks,
                           gps_issues=gps_issues,
                           outliers=outliers,
                           duplicates=duplicates,
                           incomplete_participants=incomplete_participants[:50])
