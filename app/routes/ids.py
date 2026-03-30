from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required

from app.extensions import db
from app.models import IdAllocation, Participant
from app.utils.decorators import role_required
from app.utils.helpers import generate_tracking_id

ids_bp = Blueprint('ids', __name__, url_prefix='/ids')


@ids_bp.route('/')
@login_required
def index():
    # Current allocation state per district/gender
    allocations = IdAllocation.query.order_by(IdAllocation.tracking_id.desc()).all()

    # Summary: next available sequence per district/gender
    summaries = {}
    for district in ['WT', 'ST', 'DL']:
        for gender in ['M', 'F']:
            key = f"{district}-{gender}"
            # Find max sequence from both allocations and participants
            max_alloc = db.session.query(db.func.max(IdAllocation.tracking_id)).filter(
                IdAllocation.tracking_id.like(f'TGMA-{district}-{gender}-%')
            ).scalar()
            max_part = db.session.query(db.func.max(Participant.tracking_id)).filter(
                Participant.tracking_id.like(f'TGMA-{district}-{gender}-%')
            ).scalar()

            max_seq = 0
            for tid in [max_alloc, max_part]:
                if tid:
                    try:
                        seq = int(tid.split('-')[-1])
                        max_seq = max(max_seq, seq)
                    except (ValueError, IndexError):
                        pass

            summaries[key] = {
                'district': district,
                'gender': gender,
                'last_sequence': max_seq,
                'next_sequence': max_seq + 1,
            }

    return render_template('ids/allocate.html', allocations=allocations, summaries=summaries)


@ids_bp.route('/allocate', methods=['POST'])
@login_required
@role_required('pi', 'co_pi', 'field_supervisor')
def allocate():
    district = request.form.get('district', '').upper()
    gender = request.form.get('gender', '').upper()
    count = request.form.get('count', 1, type=int)
    field_worker = request.form.get('field_worker', '').strip()

    if district not in ('WT', 'ST', 'DL'):
        flash('Invalid district.', 'danger')
        return redirect(url_for('ids.index'))
    if gender not in ('M', 'F'):
        flash('Invalid gender.', 'danger')
        return redirect(url_for('ids.index'))
    if count < 1 or count > 50:
        flash('Count must be between 1 and 50.', 'danger')
        return redirect(url_for('ids.index'))

    # Find current max sequence for this district/gender
    max_alloc = db.session.query(db.func.max(IdAllocation.tracking_id)).filter(
        IdAllocation.tracking_id.like(f'TGMA-{district}-{gender}-%')
    ).scalar()
    max_part = db.session.query(db.func.max(Participant.tracking_id)).filter(
        Participant.tracking_id.like(f'TGMA-{district}-{gender}-%')
    ).scalar()

    max_seq = 0
    for tid in [max_alloc, max_part]:
        if tid:
            try:
                seq = int(tid.split('-')[-1])
                max_seq = max(max_seq, seq)
            except (ValueError, IndexError):
                pass

    allocated_ids = []
    for i in range(count):
        seq = max_seq + i + 1
        tracking_id = generate_tracking_id(district, gender, seq)
        alloc = IdAllocation(
            tracking_id=tracking_id,
            allocated_date=date.today(),
            allocated_to=field_worker,
            status='allocated',
        )
        db.session.add(alloc)
        allocated_ids.append(tracking_id)

    db.session.commit()
    flash(f'Allocated {count} IDs: {", ".join(allocated_ids)}', 'success')
    return redirect(url_for('ids.index'))


@ids_bp.route('/<tracking_id>/status', methods=['POST'])
@login_required
@role_required('pi', 'co_pi', 'field_supervisor')
def update_status(tracking_id):
    alloc = db.session.get(IdAllocation, tracking_id)
    if not alloc:
        flash('Allocation not found.', 'danger')
        return redirect(url_for('ids.index'))

    new_status = request.form.get('status', '')
    if new_status not in ('allocated', 'used', 'returned', 'void'):
        flash('Invalid status.', 'danger')
        return redirect(url_for('ids.index'))

    alloc.status = new_status
    if new_status == 'used':
        alloc.used_date = date.today()

    db.session.commit()
    flash(f'{tracking_id} marked as {new_status}.', 'success')
    return redirect(url_for('ids.index'))
