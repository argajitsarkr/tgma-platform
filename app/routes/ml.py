import io
import csv
from datetime import date

from flask import Blueprint, render_template, Response, request, flash, redirect, url_for
from flask_login import login_required

from app.extensions import db
from app.models import (Participant, Anthropometrics, LifestyleData, EnvironmentSES,
                         HormoneResult, SequencingResult, MetabolicRisk)
from app.utils.decorators import role_required

ml_bp = Blueprint('ml', __name__, url_prefix='/ml')


@ml_bp.route('/')
@login_required
@role_required('pi', 'co_pi', 'bioinformatician')
def status():
    # Count participants with data in each domain
    total = Participant.query.filter(
        Participant.enrollment_status.in_(['enrolled', 'completed'])
    ).count()
    with_anthro = Anthropometrics.query.count()
    with_lifestyle = LifestyleData.query.count()
    with_hormones = db.session.query(
        db.func.count(db.distinct(HormoneResult.tracking_id))
    ).scalar()
    with_sequencing = db.session.query(
        db.func.count(db.distinct(SequencingResult.tracking_id))
    ).scalar()
    with_risk = MetabolicRisk.query.count()

    # Latest model info
    latest_model = MetabolicRisk.query.order_by(MetabolicRisk.prediction_date.desc()).first()

    return render_template('ml/status.html',
                           total=total,
                           with_anthro=with_anthro,
                           with_lifestyle=with_lifestyle,
                           with_hormones=with_hormones,
                           with_sequencing=with_sequencing,
                           with_risk=with_risk,
                           latest_model=latest_model)


@ml_bp.route('/export')
@login_required
@role_required('pi', 'co_pi', 'bioinformatician')
def export():
    """Export feature matrix as CSV — one row per participant, all domains."""
    participants = Participant.query.filter(
        Participant.enrollment_status.in_(['enrolled', 'completed'])
    ).all()

    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    header = [
        'tracking_id', 'age', 'gender', 'district', 'lifestyle_group',
        # Anthropometrics
        'height_cm', 'weight_kg', 'bmi', 'waist_cm', 'hip_cm', 'waist_hip_ratio',
        'muac_cm', 'body_fat_pct', 'bp_systolic', 'bp_diastolic', 'heart_rate', 'tanner_stage',
        # Lifestyle
        'vigorous_activity', 'moderate_activity', 'sedentary_weekday', 'sedentary_weekend',
        'meals_per_day', 'sleep_quality', 'daily_screen', 'pss4_score',
        'passive_smoke', 'personal_substance',
        # Environment
        'water_source', 'cooking_fuel', 'toilet_type', 'household_income', 'household_size',
        'father_edu', 'mother_edu',
        # Hormones
        'fasting_glucose_mg_dl', 'insulin_uiu_ml', 'homa_ir',
        'cortisol_serum_ug_dl', 'igf1_ng_ml',
        'total_cholesterol_mg_dl', 'hdl_mg_dl', 'ldl_mg_dl', 'triglycerides_mg_dl', 'tg_hdl_ratio',
        # Sequencing
        'total_reads', 'reads_post_qc', 'host_removal_pct', 'mag_count', 'hq_mag_count',
    ]
    writer.writerow(header)

    for p in participants:
        a = p.anthropometrics
        l = p.lifestyle_data
        e = p.environment_ses
        # Latest hormone result
        h = HormoneResult.query.filter_by(tracking_id=p.tracking_id).order_by(
            HormoneResult.report_date.desc()
        ).first()
        # Latest sequencing
        s = SequencingResult.query.filter_by(tracking_id=p.tracking_id).order_by(
            SequencingResult.data_received_date.desc()
        ).first()

        row = [
            p.tracking_id, p.age, p.gender, p.district,
            p.lifestyle_group_final or p.lifestyle_group_assigned,
            # Anthropometrics
            float(a.height_cm) if a and a.height_cm else '',
            float(a.weight_kg) if a and a.weight_kg else '',
            a.bmi if a else '',
            float(a.waist_cm) if a and a.waist_cm else '',
            float(a.hip_cm) if a and a.hip_cm else '',
            a.waist_hip_ratio if a else '',
            float(a.muac_cm) if a and a.muac_cm else '',
            float(a.body_fat_pct) if a and a.body_fat_pct else '',
            a.bp_systolic if a else '',
            a.bp_diastolic if a else '',
            a.heart_rate if a else '',
            a.tanner_stage if a else '',
            # Lifestyle
            l.vigorous_activity if l else '',
            l.moderate_activity if l else '',
            float(l.sedentary_weekday) if l and l.sedentary_weekday else '',
            float(l.sedentary_weekend) if l and l.sedentary_weekend else '',
            l.meals_per_day if l else '',
            l.sleep_quality if l else '',
            float(l.daily_screen) if l and l.daily_screen else '',
            l.pss4_score if l else '',
            l.passive_smoke if l else '',
            l.personal_substance if l else '',
            # Environment
            e.water_source if e else '',
            e.cooking_fuel if e else '',
            e.toilet_type if e else '',
            e.household_income if e else '',
            e.household_size if e else '',
            e.father_edu if e else '',
            e.mother_edu if e else '',
            # Hormones
            float(h.fasting_glucose_mg_dl) if h and h.fasting_glucose_mg_dl else '',
            float(h.insulin_uiu_ml) if h and h.insulin_uiu_ml else '',
            h.homa_ir if h else '',
            float(h.cortisol_serum_ug_dl) if h and h.cortisol_serum_ug_dl else '',
            float(h.igf1_ng_ml) if h and h.igf1_ng_ml else '',
            float(h.total_cholesterol_mg_dl) if h and h.total_cholesterol_mg_dl else '',
            float(h.hdl_mg_dl) if h and h.hdl_mg_dl else '',
            float(h.ldl_mg_dl) if h and h.ldl_mg_dl else '',
            float(h.triglycerides_mg_dl) if h and h.triglycerides_mg_dl else '',
            h.tg_hdl_ratio if h else '',
            # Sequencing
            s.total_reads if s else '',
            s.reads_post_qc if s else '',
            float(s.host_removal_pct) if s and s.host_removal_pct else '',
            s.mag_count if s else '',
            s.hq_mag_count if s else '',
        ]
        writer.writerow(row)

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=tgma_feature_matrix_{date.today()}.csv'}
    )
