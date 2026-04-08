"""ID Allocation — pre-allocate tracking IDs for field workers before they go to field."""

from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from app.extensions import db
from app.models import IdAllocation, Participant
from app.utils.helpers import generate_tracking_id
from app.utils.decorators import role_required

ids_bp = Blueprint('ids', __name__, url_prefix='/ids')


def _get_next_seq(district, gender):
    """Return the next available sequence number for a district/gender combination."""
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
    return max_seq + 1


@ids_bp.route('/')
@login_required
def index():
    """Show allocation dashboard — current sequence status per district/gender."""
    summaries = {}
    for district in ['WT', 'ST', 'DL']:
        for gender in ['M', 'F']:
            key = f"{district}-{gender}"
            next_seq = _get_next_seq(district, gender)
            summaries[key] = {
                'district': district,
                'gender': gender,
                'last_sequence': next_seq - 1,
                'next_sequence': next_seq,
            }

    # Recent allocations
    recent = IdAllocation.query.order_by(IdAllocation.created_at.desc()).limit(30).all()

    return render_template('ids/allocate.html', summaries=summaries, recent=recent)


@ids_bp.route('/allocate', methods=['POST'])
@login_required
@role_required('pi', 'co_pi', 'bioinformatician')
def allocate():
    """Bulk-allocate a batch of IDs for a field worker."""
    district = request.form.get('district', '').upper()
    gender = request.form.get('gender', '').upper()
    field_worker = request.form.get('field_worker', '').strip()
    try:
        count = max(1, min(50, int(request.form.get('count', 1))))
    except (ValueError, TypeError):
        count = 1

    if district not in ('WT', 'ST', 'DL'):
        flash('Invalid district.', 'danger')
        return redirect(url_for('ids.index'))
    if gender not in ('M', 'F'):
        flash('Invalid gender.', 'danger')
        return redirect(url_for('ids.index'))

    start_seq = _get_next_seq(district, gender)
    allocated_ids = []

    for i in range(count):
        seq = start_seq + i
        tracking_id = generate_tracking_id(district, gender, seq)
        alloc = IdAllocation(
            tracking_id=tracking_id,
            allocated_date=date.today(),
            allocated_to=field_worker or None,
            status='allocated',
        )
        db.session.add(alloc)
        allocated_ids.append(tracking_id)

    db.session.commit()

    flash(f'Allocated {count} ID{"s" if count > 1 else ""}: '
          f'{allocated_ids[0]} → {allocated_ids[-1]}', 'success')

    # Redirect to print-ready label sheet if batch > 1
    if count > 1:
        return redirect(url_for('ids.print_labels',
                                start=allocated_ids[0], end=allocated_ids[-1],
                                worker=field_worker))
    return redirect(url_for('ids.index'))


@ids_bp.route('/labels')
@login_required
def print_labels():
    """Print-ready label sheet for a batch of allocated IDs."""
    start = request.args.get('start', '')
    end = request.args.get('end', '')
    worker = request.args.get('worker', '')

    # Collect all IDs in the range from allocation table
    ids = IdAllocation.query.filter(
        IdAllocation.tracking_id >= start,
        IdAllocation.tracking_id <= end,
        IdAllocation.allocated_to == (worker or None)
            if worker else IdAllocation.tracking_id >= start,
    ).order_by(IdAllocation.tracking_id).all()

    # Fallback: generate list from start/end directly
    if not ids and start and end:
        try:
            parts_s = start.split('-')
            parts_e = end.split('-')
            district, gender = parts_s[1], parts_s[2]
            seq_s = int(parts_s[3])
            seq_e = int(parts_e[3])
            label_ids = [generate_tracking_id(district, gender, s)
                         for s in range(seq_s, seq_e + 1)]
        except (IndexError, ValueError):
            label_ids = []
    else:
        label_ids = [a.tracking_id for a in ids]

    return render_template('ids/labels.html',
                           label_ids=label_ids,
                           worker=worker,
                           today=date.today())
