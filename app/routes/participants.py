from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required

from app.extensions import db
from app.models import (Participant, HealthScreening, Anthropometrics, MenstrualData,
                         LifestyleData, EnvironmentSES, Sample, HormoneResult,
                         SequencingResult, MetabolicRisk, AuditLog)
from app.utils.decorators import role_required

participants_bp = Blueprint('participants', __name__, url_prefix='/participants')


@participants_bp.route('/')
@login_required
def list_participants():
    from sqlalchemy import func as sa_func

    total_enrolled = Participant.query.filter(
        Participant.enrollment_status.in_(['enrolled', 'completed'])
    ).count()

    by_gender = db.session.query(
        Participant.gender, db.func.count(Participant.tracking_id)
    ).filter(
        Participant.enrollment_status.in_(['enrolled', 'completed'])
    ).group_by(Participant.gender).all()
    gender_counts = dict(by_gender)

    by_district = db.session.query(
        Participant.district, db.func.count(Participant.tracking_id)
    ).filter(
        Participant.enrollment_status.in_(['enrolled', 'completed'])
    ).group_by(Participant.district).all()
    district_counts = dict(by_district)

    complete_sub = db.session.query(
        Sample.tracking_id
    ).filter(
        Sample.collection_status == 'collected'
    ).group_by(Sample.tracking_id).having(
        sa_func.count(db.distinct(Sample.sample_type)) >= 6
    ).subquery()
    complete_samples = db.session.query(sa_func.count()).select_from(complete_sub).scalar() or 0

    return render_template('participants/list.html',
                           total_enrolled=total_enrolled,
                           gender_counts=gender_counts,
                           district_counts=district_counts,
                           complete_samples=complete_samples)


@participants_bp.route('/api/data')
@login_required
def api_data():
    """Server-side DataTables JSON endpoint."""
    draw = request.args.get('draw', 1, type=int)
    start = request.args.get('start', 0, type=int)
    length = request.args.get('length', 25, type=int)
    search_value = request.args.get('search[value]', '').strip()

    # Filters
    district = request.args.get('district', '')
    gender = request.args.get('gender', '')
    status = request.args.get('status', '')
    lifestyle = request.args.get('lifestyle', '')

    query = Participant.query

    if district:
        query = query.filter_by(district=district)
    if gender:
        query = query.filter_by(gender=gender)
    if status:
        query = query.filter_by(enrollment_status=status)
    if lifestyle:
        query = query.filter_by(lifestyle_group_assigned=lifestyle)
    if search_value:
        query = query.filter(
            db.or_(
                Participant.tracking_id.ilike(f'%{search_value}%'),
                Participant.full_name.ilike(f'%{search_value}%'),
                Participant.village_town.ilike(f'%{search_value}%'),
            )
        )

    total = Participant.query.count()
    filtered = query.count()

    participants = query.order_by(Participant.created_at.desc()).offset(start).limit(length).all()

    data = []
    for p in participants:
        sample_count = Sample.query.filter_by(tracking_id=p.tracking_id,
                                               collection_status='collected').count()
        data.append({
            'tracking_id': p.tracking_id,
            'full_name': p.full_name,
            'age': p.age,
            'gender': p.gender,
            'district': p.display_district,
            'lifestyle_group': p.lifestyle_group_assigned or '-',
            'enrollment_status': p.enrollment_status,
            'samples': f'{sample_count}/6',
            'enrollment_date': p.enrollment_date.isoformat() if p.enrollment_date else '-',
        })

    return jsonify({
        'draw': draw,
        'recordsTotal': total,
        'recordsFiltered': filtered,
        'data': data,
    })


@participants_bp.route('/<tracking_id>')
@login_required
def detail(tracking_id):
    participant = db.session.get(Participant, tracking_id)
    if not participant:
        flash('Participant not found.', 'danger')
        return redirect(url_for('participants.list_participants'))

    samples = Sample.query.filter_by(tracking_id=tracking_id).order_by(Sample.sample_type).all()
    hormone_results = HormoneResult.query.filter_by(tracking_id=tracking_id).all()
    seq_results = SequencingResult.query.filter_by(tracking_id=tracking_id).all()
    audit_entries = AuditLog.query.filter_by(
        record_id=tracking_id
    ).order_by(AuditLog.changed_at.desc()).limit(50).all()

    return render_template('participants/detail.html',
                           p=participant,
                           samples=samples,
                           hormone_results=hormone_results,
                           seq_results=seq_results,
                           audit_entries=audit_entries)


@participants_bp.route('/new', methods=['GET', 'POST'])
@login_required
@role_required('pi', 'co_pi', 'bioinformatician')
def create():
    if request.method == 'POST':
        tracking_id = request.form.get('tracking_id', '').strip().upper()

        # Check for duplicate
        if db.session.get(Participant, tracking_id):
            flash(f'Participant {tracking_id} already exists.', 'danger')
            return redirect(url_for('participants.create'))

        from app.utils.helpers import validate_tracking_id
        if not validate_tracking_id(tracking_id):
            flash('Invalid tracking ID format. Expected: TGMA-XX-X-XXXX', 'danger')
            return redirect(url_for('participants.create'))

        participant = Participant(
            tracking_id=tracking_id,
            full_name=request.form.get('full_name', '').strip(),
            age=request.form.get('age', type=int),
            gender=request.form.get('gender', ''),
            district=request.form.get('district', ''),
            village_town=request.form.get('village_town', '').strip(),
            guardian_phone=request.form.get('guardian_phone', '').strip(),
            school_class=request.form.get('school_class', '').strip(),
            enrollment_date=request.form.get('enrollment_date') or None,
            enrollment_status='enrolled',
            consent_parent=bool(request.form.get('consent_parent')),
            assent_participant=bool(request.form.get('assent_participant')),
            notes=request.form.get('notes', '').strip(),
        )

        db.session.add(participant)
        db.session.commit()
        flash(f'Participant {tracking_id} enrolled successfully.', 'success')
        return redirect(url_for('participants.detail', tracking_id=tracking_id))

    return render_template('participants/detail.html', p=None, create_mode=True,
                           samples=[], hormone_results=[], seq_results=[], audit_entries=[])


@participants_bp.route('/<tracking_id>/edit', methods=['POST'])
@login_required
@role_required('pi', 'co_pi', 'bioinformatician')
def edit(tracking_id):
    participant = db.session.get(Participant, tracking_id)
    if not participant:
        flash('Participant not found.', 'danger')
        return redirect(url_for('participants.list_participants'))

    # Update fields from form
    for field in ['full_name', 'village_town', 'guardian_phone', 'school_class',
                  'religion', 'community_tribe', 'mother_tongue',
                  'lifestyle_group_assigned', 'lifestyle_group_final',
                  'enrollment_status', 'field_worker_name', 'notes']:
        val = request.form.get(field, '').strip()
        if val:
            setattr(participant, field, val)

    age = request.form.get('age')
    if age:
        participant.age = int(age)

    db.session.commit()
    flash('Participant updated.', 'success')
    return redirect(url_for('participants.detail', tracking_id=tracking_id))
