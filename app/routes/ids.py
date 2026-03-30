from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required

from app.extensions import db
from app.models import IdAllocation, Participant
from app.utils.helpers import generate_tracking_id

ids_bp = Blueprint('ids', __name__, url_prefix='/ids')


@ids_bp.route('/')
@login_required
def index():
    # Summary: current sequence per district/gender (6 combos)
    summaries = {}
    for district in ['WT', 'ST', 'DL']:
        for gender in ['M', 'F']:
            key = f"{district}-{gender}"
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

    return render_template('ids/allocate.html', summaries=summaries)


@ids_bp.route('/allocate', methods=['POST'])
@login_required
def allocate():
    district = request.form.get('district', '').upper()
    gender = request.form.get('gender', '').upper()

    if district not in ('WT', 'ST', 'DL'):
        flash('Invalid district.', 'danger')
        return redirect(url_for('ids.index'))
    if gender not in ('M', 'F'):
        flash('Invalid gender.', 'danger')
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

    seq = max_seq + 1
    tracking_id = generate_tracking_id(district, gender, seq)
    alloc = IdAllocation(
        tracking_id=tracking_id,
        allocated_date=date.today(),
        allocated_to=request.form.get('field_worker', '').strip(),
        status='allocated',
    )
    db.session.add(alloc)
    db.session.commit()

    flash(f'Allocated ID: {tracking_id}', 'success')
    return redirect(url_for('ids.index'))
