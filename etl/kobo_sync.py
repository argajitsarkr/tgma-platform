#!/usr/bin/env python3
"""KoboToolbox → PostgreSQL sync engine.

Handles manual "Sync Now" from the UI and optional CLI usage.
KoboToolbox only stores fully submitted forms — drafts stay on the phone.
Field workers may skip optional sections; those arrive as NULL.

Sync strategy:
  - Manual trigger via UI button (PI/bioinformatician clicks "Sync Now")
  - Validation: reject any submission missing tracking_id, full_name, gender, district
  - Idempotent: upsert by tracking_id — same submission twice just updates
  - Sync log: every run is recorded with inserted/updated/skipped counts + details

Usage (CLI):
    python etl/kobo_sync.py                # Incremental sync (since last run)
    python etl/kobo_sync.py --full         # Full re-sync (all submissions)
"""

import os
import sys
import json
import logging
from datetime import datetime

import requests

# Add project root when run as script
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.extensions import db
from app.models import (Participant, HealthScreening, Anthropometrics, MenstrualData,
                         LifestyleData, EnvironmentSES, KoboSyncLog)
from app.utils.helpers import (validate_tracking_id, validate_gps, validate_age,
                                DISTRICT_CODES, DISTRICT_SLUG_TO_CODE)

logger = logging.getLogger(__name__)

# Sync state file — stores the last sync timestamp for incremental fetches
SYNC_STATE_FILE = os.path.join(os.path.dirname(__file__), '.kobo_sync_state.json')

# Critical fields that MUST be present — reject the submission without these
REQUIRED_FIELDS = ('tracking_id', 'full_name', 'gender', 'district')


# ---------------------------------------------------------------------------
# API fetch
# ---------------------------------------------------------------------------

def load_sync_state():
    if os.path.exists(SYNC_STATE_FILE):
        with open(SYNC_STATE_FILE, 'r') as f:
            return json.load(f)
    return {'last_sync': None}


def save_sync_state(state):
    with open(SYNC_STATE_FILE, 'w') as f:
        json.dump(state, f)


def fetch_submissions(api_url, token, form_id, since=None):
    """Fetch submissions from KoboToolbox API v2 with pagination."""
    headers = {'Authorization': f'Token {token}'}
    url = f'{api_url}/api/v2/assets/{form_id}/data.json'
    params = {'limit': 100, 'sort': '{"_submission_time": 1}'}

    if since:
        params['query'] = json.dumps({'_submission_time': {'$gte': since}})

    all_results = []
    while url:
        logger.info(f'Fetching: {url}')
        resp = requests.get(url, headers=headers, params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        results = data.get('results', [])
        all_results.extend(results)
        url = data.get('next')
        params = {}  # Next URL already includes params

    logger.info(f'Fetched {len(all_results)} submissions from KoboToolbox')
    return all_results


# ---------------------------------------------------------------------------
# Field mapping & validation
# ---------------------------------------------------------------------------

def safe_float(val):
    if val is None or val == '':
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def safe_int(val):
    if val is None or val == '':
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def yn_to_bool(val):
    """XLSForm `select_one yes_no` fields arrive as the string 'yes'/'no', not as bool.
    Returns True for 'yes', False for 'no', None for blank/missing/'dk'/'na'.
    """
    if val is None or val == '':
        return None
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    if s in ('yes', 'true', '1'):
        return True
    if s in ('no', 'false', '0'):
        return False
    return None  # 'dk', 'na', 'declined', etc.


# ---------------------------------------------------------------------------
# v4.1 form helpers — group-prefix flattening + slug-to-value lookups
# ---------------------------------------------------------------------------

def flatten_kobo_submission(sub):
    """KoboToolbox API v2 returns grouped XLSForm fields with the group path
    prefixed: e.g. `part_a/tracking_id`, `part_b/b1/b1_chronic_illness`. The
    rest of this module reads bare field names, so flatten the dict.

    Last-segment-wins on collisions, which is safe because XLSForm field names
    are globally unique within a form. Reserved Kobo metadata keys (start with
    '_' or contain a colon) are passed through untouched.

    Idempotent: a submission with already-flat keys round-trips unchanged.
    """
    if not isinstance(sub, dict):
        return sub
    out = {}
    for k, v in sub.items():
        if not isinstance(k, str) or k.startswith('_') or ':' in k:
            out[k] = v
        else:
            out[k.rsplit('/', 1)[-1]] = v
    return out


def _first(sub, *names, default=None):
    """Return the first present, non-empty value from `sub` for any of `names`.
    Used to read fields by their v4.1 name with v3 name as fallback."""
    for n in names:
        if n in sub:
            v = sub[n]
            if v is not None and v != '':
                return v
    return default


# Slug → midpoint number for v4.1 select_one fields that target numeric DB columns.
SITTING_HOURS_MIDPOINT = {'lt_2': 1.0, '2_4': 3.0, '4_6': 5.0, '6_8': 7.0, 'gt_8': 9.0}
SCREEN_TOTAL_MIDPOINT  = {'lt_1': 0.5, '1_2': 1.5, '2_4': 3.0, '4_6': 5.0, 'gt_6': 7.0}
MEALS_PER_DAY_MIDPOINT = {'1_2': 2,   '3': 3, '3_plus_snacks': 3, '4_plus': 4}
FAMILY_SIZE_MIDPOINT   = {'2_3': 3,   '4_5': 5, '6_7': 7, '8_plus': 8}
CLASS_GRADE_LABEL      = {f'class_{n}': f'Class {n}' for n in range(7, 13)}
GENDER_SLUG_TO_CODE    = {'male': 'M', 'female': 'F', 'm': 'M', 'f': 'F'}
DELIVERY_MODE_NORMALIZE = {'c_section': 'csection'}  # back-compat with v3 stored values
BREASTFED_TO_BOOL      = {'exclusive': True, 'mixed': True, 'formula': False, 'formula_only': False}


def _slug_or_number(val, slug_map):
    """If `val` is a slug in `slug_map`, return the mapped number.
    If `val` is already a number-like string/int/float, coerce to int/float.
    Returns None on missing or unrecognized."""
    if val is None or val == '':
        return None
    s = str(val).strip()
    if s in slug_map:
        return slug_map[s]
    # Try numeric coercion (in case form is older or value is already numeric)
    try:
        f = float(s)
        return int(f) if f.is_integer() else f
    except (ValueError, TypeError):
        return None


def parse_date(val):
    if not val or val == '':
        return None
    try:
        return datetime.strptime(str(val)[:10], '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None


def validate_submission(submission):
    """Validate critical fields. Returns (tracking_id_or_None, error_string_or_None).

    A submission is REJECTED if any of: tracking_id, full_name, gender, district is missing.
    Optional fields (age, GPS, anthropometrics, etc.) are accepted as NULL.

    Group-prefixed Kobo keys (`part_a/tracking_id`, …) are flattened first, so this
    works with v4.1 (heavy grouping) and earlier flat forms alike.
    """
    submission = flatten_kobo_submission(submission)

    tracking_id = str(submission.get('tracking_id', '')).strip().upper()
    if not tracking_id:
        kobo_id = submission.get('_id', '?')
        return None, f'Kobo #{kobo_id}: Missing tracking_id — skipped'

    if not validate_tracking_id(tracking_id):
        return tracking_id, f'{tracking_id}: Invalid format (expected TGMA-XX-X-0000) — skipped'

    full_name = str(submission.get('full_name', '')).strip()
    if not full_name:
        return tracking_id, f'{tracking_id}: Missing full_name — skipped'

    # v4.1 sends gender slug 'male'/'female'; v3 and earlier sent 'M'/'F'. Accept both.
    gender_raw = str(submission.get('gender', '')).strip().lower()
    gender = GENDER_SLUG_TO_CODE.get(gender_raw)
    if gender not in ('M', 'F'):
        # Fallback: derive from tracking_id (TGMA-WT-F-0001 → F)
        parts = tracking_id.split('-')
        if len(parts) >= 3 and parts[2] in ('M', 'F'):
            gender = parts[2]
        else:
            return tracking_id, f'{tracking_id}: Missing/invalid gender — skipped'

    # Districts:
    #   v4.1: 2-letter code directly ('WT', 'NT', …)
    #   v3:   slug ('west_tripura', 'north_tripura', …) or 'other' for non-Tripura
    district_raw = str(submission.get('district', '')).strip().lower()
    if district_raw == 'other':
        return tracking_id, f'{tracking_id}: district=other not supported (tracking IDs cover only the 6 Tripura districts) — skipped'

    district = DISTRICT_SLUG_TO_CODE.get(district_raw)
    if not district:
        # Try uppercase 2-letter (v4.1 path)
        upper = district_raw.upper()
        if upper in DISTRICT_CODES:
            district = upper
        else:
            # Last resort: derive from tracking_id
            parts = tracking_id.split('-')
            if len(parts) >= 2 and parts[1] in DISTRICT_CODES:
                district = parts[1]
            else:
                return tracking_id, f'{tracking_id}: Missing/invalid district — skipped'

    return tracking_id, None  # Valid


def map_submission(submission):
    """Map a KoboToolbox submission dict to our model dicts.

    Returns (mapped_dict, None) on success, (None, error_string) on validation failure.
    Optional sections that are empty come through as NULL — that's fine.

    Reads v4.1 field names first; falls back to v3/earlier names so older submissions
    in the same backfill still parse.
    """
    submission = flatten_kobo_submission(submission)

    # --- Critical field validation (also flattens internally — safe to re-call) ---
    tracking_id, error = validate_submission(submission)
    if error:
        return None, error

    # --- Parse all fields (NULLs are OK for optional ones) ---
    age = safe_int(_first(submission, 'age_years', 'age'))
    if age is not None and not validate_age(age):
        return None, f'{tracking_id}: Age {age} outside study range 12-18 — skipped'

    # GPS — v4.1 has `gps_location` (single geopoint string "lat lon alt acc"),
    # KoboToolbox also exposes parsed `_geolocation: [lat, lon]`.
    geoloc = submission.get('_geolocation') or [None, None]
    lat = geoloc[0] if geoloc and len(geoloc) > 0 else None
    lon = geoloc[1] if geoloc and len(geoloc) > 1 else None
    if lat is None or lon is None:
        # Try parsing the geopoint string from gps_location
        gps_str = submission.get('gps_location') or ''
        if gps_str:
            parts = str(gps_str).split()
            if len(parts) >= 2:
                lat = lat or safe_float(parts[0])
                lon = lon or safe_float(parts[1])
    lat = lat if lat is not None else safe_float(submission.get('gps_latitude'))
    lon = lon if lon is not None else safe_float(submission.get('gps_longitude'))

    if lat is not None and lon is not None:
        if not validate_gps(lat, lon):
            logger.warning(f'{tracking_id}: GPS ({lat}, {lon}) outside Tripura bounds — accepted anyway')

    # Gender (revalidated for use here; validate_submission already checked)
    gender = GENDER_SLUG_TO_CODE.get(str(submission.get('gender', '')).strip().lower())
    if gender not in ('M', 'F'):
        gender = tracking_id.split('-')[2] if len(tracking_id.split('-')) >= 3 else 'M'

    district = tracking_id.split('-')[1] if len(tracking_id.split('-')) >= 2 else ''

    # School: v4.1 splits into name + class_grade slug; concatenate into the existing column.
    school_name = str(_first(submission, 'school_name', default='') or '').strip()
    class_grade = str(_first(submission, 'class_grade', default='') or '').strip().lower()
    class_label = CLASS_GRADE_LABEL.get(class_grade, '')
    if school_name and class_label:
        school_class = f'{school_name} — {class_label}'
    elif school_name:
        school_class = school_name
    elif class_label:
        school_class = class_label
    else:
        school_class = str(_first(submission, 'school_class', default='') or '').strip() or None

    # Free-text "other" overrides for slug-coded fields
    religion = _first(submission, 'religion')
    if religion == 'other':
        religion = _first(submission, 'religion_other', default='other')
    community = _first(submission, 'community_tribe')
    if community == 'other':
        community = _first(submission, 'community_other', default='other')
    mtongue = _first(submission, 'mother_tongue')
    if mtongue == 'other':
        mtongue = _first(submission, 'mother_tongue_other', default='other')

    # Enrollment date: prefer v4.1 `assessment_date`, else KoboToolbox metadata.
    enrollment_date = parse_date(_first(submission, 'assessment_date', default='')) \
        or parse_date(str(submission.get('_submission_time', '')).split('T')[0])

    # --- Participant (demographics) ---
    participant_data = {
        'tracking_id': tracking_id,
        'full_name': str(submission.get('full_name', '')).strip(),
        'age': age,
        'gender': gender,
        'district': district,
        'dob': parse_date(_first(submission, 'date_of_birth', 'dob')),
        'village_town': str(_first(submission, 'village_town_ward', 'village_town', default='') or '').strip() or None,
        'guardian_phone': str(_first(submission, 'guardian_phone', default='') or '').strip() or None,
        'school_class': school_class,
        'religion': str(religion).strip() if religion else None,
        'community_tribe': str(community).strip() if community else None,
        'mother_tongue': str(mtongue).strip() if mtongue else None,
        'enrollment_date': enrollment_date,
        'enrollment_status': 'enrolled',
        'field_worker_name': str(_first(submission, 'kobo_username', 'field_worker', default='') or '').strip() or None,
        'gps_latitude': lat,
        'gps_longitude': lon,
        'consent_parent': yn_to_bool(_first(submission, 'consent_signed_paper', 'consent_parent')) or False,
        'assent_participant': yn_to_bool(_first(submission, 'assent_signed_paper', 'assent_participant')) or False,
        'photo_consent': yn_to_bool(_first(submission, 'photo_consent')) or False,
        'kobo_submission_id': str(submission.get('_id', '')),
    }

    # --- Health screening (Part B) ---
    delivery_raw = _first(submission, 'b3_delivery_mode', 'delivery_mode')
    delivery_mode = DELIVERY_MODE_NORMALIZE.get(delivery_raw, delivery_raw) if delivery_raw else None
    breastfed_raw = _first(submission, 'b3_breastfed', 'breastfed')
    health_data = {
        'chronic_illness':    yn_to_bool(_first(submission, 'b1_chronic_illness', 'chronic_illness')),
        'antibiotics_3mo':    yn_to_bool(_first(submission, 'b1_recent_antibiotics', 'antibiotics_3mo')),
        'hospital_3mo':       yn_to_bool(_first(submission, 'b1_recent_hospital', 'hospital_3mo')),
        'genetic_disorder':   yn_to_bool(_first(submission, 'b1_genetic_disorder', 'genetic_disorder')),
        'pregnant':           yn_to_bool(_first(submission, 'b1_pregnant', 'pregnant')),
        'regular_medication': yn_to_bool(_first(submission, 'b1_regular_medication', 'regular_medication')),
        'medication_details': str(_first(submission, 'b1_medication_specify', 'medication_details', default='') or '').strip() or None,
        'fam_diabetes':       _first(submission, 'fh_t2_diabetes', 'fam_diabetes'),
        'fam_obesity':        _first(submission, 'fh_obesity', 'fam_obesity'),
        'fam_hypertension':   _first(submission, 'fh_hypertension', 'fam_hypertension'),
        'delivery_mode':      delivery_mode,
        # breastfeeding_status slug → bool; v3 `formula_only` also recognized.
        'breastfed':          BREASTFED_TO_BOOL.get(breastfed_raw) if breastfed_raw else None,
        'bf_duration':        _first(submission, 'b3_breastfeed_duration', 'bf_duration'),
    }

    # --- Anthropometrics (Part F.anthro in v4.1, Part G in v3) ---
    anthro_data = {
        'height_cm':  safe_float(_first(submission, 'anthro_height_cm', 'height_cm')),
        'weight_kg':  safe_float(_first(submission, 'anthro_weight_kg', 'weight_kg')),
        'waist_cm':   safe_float(_first(submission, 'anthro_waist_cm', 'waist_cm')),
        'hip_cm':     safe_float(_first(submission, 'anthro_hip_cm', 'hip_cm')),
        'bp_systolic':  safe_int(_first(submission, 'anthro_bp_systolic', 'bp_systolic')),
        'bp_diastolic': safe_int(_first(submission, 'anthro_bp_diastolic', 'bp_diastolic')),
        'heart_rate':   safe_int(_first(submission, 'anthro_resting_hr', 'heart_rate')),
        'tanner_stage': safe_int(submission.get('tanner_stage')),
        'measurement_date': enrollment_date,
    }

    # --- Lifestyle & FFQ (Part C in v4.1) ---
    # v4.1 turned several previously-numeric fields into slug-coded select_one.
    # _slug_or_number maps slug → midpoint numeric; legacy numeric values pass through.
    lifestyle_data = {
        'vigorous_activity': _first(submission, 'c1_vigorous_days', 'vigorous_activity'),
        'moderate_activity': _first(submission, 'c1_moderate_days', 'moderate_activity'),
        'sedentary_weekday': _slug_or_number(_first(submission, 'c1_sitting_weekday', 'sedentary_weekday'), SITTING_HOURS_MIDPOINT),
        'sedentary_weekend': _slug_or_number(_first(submission, 'c1_sitting_weekend', 'sedentary_weekend'), SITTING_HOURS_MIDPOINT),
        'meals_per_day':     _slug_or_number(_first(submission, 'c3_meals_per_day', 'meals_per_day'), MEALS_PER_DAY_MIDPOINT),
        'sleep_quality':     _first(submission, 'c4_sleep_quality', 'sleep_quality'),
        'daily_screen':      _slug_or_number(_first(submission, 'c4_screen_total', 'daily_screen'), SCREEN_TOTAL_MIDPOINT),
        'pss_control':       safe_int(_first(submission, 'c5_q1', 'pss_control')),
        'pss_confident':     safe_int(_first(submission, 'c5_q2', 'pss_confident')),
        'pss_going_well':    safe_int(_first(submission, 'c5_q3', 'pss_going_well')),
        'pss_overwhelmed':   safe_int(_first(submission, 'c5_q4', 'pss_overwhelmed')),
        'passive_smoke':     yn_to_bool(_first(submission, 'c6_household_smoke', 'passive_smoke')),
    }

    # --- Environment & SES (Part D in v4.1) ---
    env_data = {
        'water_source':     _first(submission, 'd1_water_source', 'water_source'),
        'cooking_fuel':     _first(submission, 'd1_cooking_fuel', 'cooking_fuel'),
        'toilet_type':      _first(submission, 'd1_toilet', 'toilet_type'),
        'household_income': _first(submission, 'd2_income', 'household_income'),
        'household_size':   _slug_or_number(_first(submission, 'd2_family_size', 'household_size'), FAMILY_SIZE_MIDPOINT),
        'father_edu':       _first(submission, 'd2_father_education', 'father_edu'),
        'mother_edu':       _first(submission, 'd2_mother_education', 'mother_edu'),
    }

    # --- Menstrual data (Part E, girls only) ---
    menstrual_data = None
    menarche_raw = _first(submission, 'e_menarche', 'menstruation_started')
    if gender == 'F' and menarche_raw is not None:
        menstrual_data = {
            'menstruation_started': yn_to_bool(menarche_raw),
            'menarche_age':         safe_int(_first(submission, 'e_menarche_age', 'menarche_age')),
            'cycle_regularity':     _first(submission, 'e_cycle_regular', 'cycle_regularity'),
        }

    return {
        'participant': participant_data,
        'health': health_data,
        'anthro': anthro_data,
        'lifestyle': lifestyle_data,
        'environment': env_data,
        'menstrual': menstrual_data,
    }, None


# ---------------------------------------------------------------------------
# Upsert logic — idempotent by tracking_id
# ---------------------------------------------------------------------------

def upsert_submission(mapped):
    """Insert or update a participant and all related records.

    Returns 'inserted' or 'updated'.
    """
    p_data = mapped['participant']
    tid = p_data['tracking_id']

    existing = db.session.get(Participant, tid)
    if existing:
        # Update: only overwrite with non-None values (preserve existing data)
        for key, val in p_data.items():
            if key != 'tracking_id' and val is not None:
                setattr(existing, key, val)
        action = 'updated'
    else:
        participant = Participant(**p_data)
        db.session.add(participant)
        action = 'inserted'

    # Health screening
    hs = HealthScreening.query.filter_by(tracking_id=tid).first()
    if not hs:
        hs = HealthScreening(tracking_id=tid)
        db.session.add(hs)
    for key, val in mapped['health'].items():
        if val is not None:
            setattr(hs, key, val)

    # Anthropometrics (may be empty if Part G not yet filled)
    has_anthro = any(v is not None for k, v in mapped['anthro'].items() if k != 'measurement_date')
    if has_anthro:
        anthro = Anthropometrics.query.filter_by(tracking_id=tid).first()
        if not anthro:
            anthro = Anthropometrics(tracking_id=tid)
            db.session.add(anthro)
        for key, val in mapped['anthro'].items():
            if val is not None:
                setattr(anthro, key, val)

    # Lifestyle
    has_lifestyle = any(v is not None for v in mapped['lifestyle'].values())
    if has_lifestyle:
        ld = LifestyleData.query.filter_by(tracking_id=tid).first()
        if not ld:
            ld = LifestyleData(tracking_id=tid)
            db.session.add(ld)
        for key, val in mapped['lifestyle'].items():
            if val is not None:
                setattr(ld, key, val)

    # Environment
    has_env = any(v is not None for v in mapped['environment'].values())
    if has_env:
        env = EnvironmentSES.query.filter_by(tracking_id=tid).first()
        if not env:
            env = EnvironmentSES(tracking_id=tid)
            db.session.add(env)
        for key, val in mapped['environment'].items():
            if val is not None:
                setattr(env, key, val)

    # Menstrual (girls only, if section was filled)
    if mapped['menstrual']:
        md = MenstrualData.query.filter_by(tracking_id=tid).first()
        if not md:
            md = MenstrualData(tracking_id=tid)
            db.session.add(md)
        for key, val in mapped['menstrual'].items():
            if val is not None:
                setattr(md, key, val)

    return action


# ---------------------------------------------------------------------------
# Main sync engine — called from UI route or CLI
# ---------------------------------------------------------------------------

def _do_sync(app, triggered_by, full_sync):
    """Internal sync logic — must be called inside an app context."""
    # Create sync log entry
    sync_log = KoboSyncLog(
        triggered_by=triggered_by,
        sync_mode='full' if full_sync else 'incremental',
        status='running',
        started_at=datetime.utcnow(),
    )
    db.session.add(sync_log)
    db.session.commit()

    details = []  # List of {tracking_id, action, reason}

    try:
        # Get Kobo credentials
        api_url = app.config.get('KOBO_API_URL') or os.environ.get('KOBO_API_URL', '')
        token = os.environ.get('KOBO_API_TOKEN', '')
        form_id = os.environ.get('KOBO_FORM_ID', '')

        if not all([api_url, token, form_id]):
            raise ValueError(
                'Missing KoboToolbox credentials. '
                'Set KOBO_API_URL, KOBO_API_TOKEN, KOBO_FORM_ID in .env'
            )

        PLACEHOLDERS = {'your-form-asset-uid', 'your-kobo-api-token'}
        if form_id in PLACEHOLDERS:
            raise ValueError(
                'KOBO_FORM_ID is not configured — still using placeholder value. '
                'Log into kf.kobotoolbox.org, open your form, copy the asset UID '
                'from the URL, then set KOBO_FORM_ID=<uid> in .env and restart.'
            )
        if token in PLACEHOLDERS:
            raise ValueError(
                'KOBO_API_TOKEN is not configured — still using placeholder value. '
                'Go to kf.kobotoolbox.org Account Settings to get your API token, '
                'then set KOBO_API_TOKEN=<token> in .env and restart.'
            )

        # Determine start point
        state = load_sync_state()
        since = None if full_sync else state.get('last_sync')

        logger.info(f'KoboSync started by {triggered_by} (mode={"full" if full_sync else "incremental"}, since={since or "beginning"})')

        # Fetch from API
        submissions = fetch_submissions(api_url, token, form_id, since)
        sync_log.total_fetched = len(submissions)

        inserted, updated, skipped = 0, 0, 0

        for sub in submissions:
            mapped, error = map_submission(sub)

            if error:
                # Submission rejected — missing critical field
                skipped += 1
                tid = str(sub.get('tracking_id', '')).strip().upper() or f"Kobo#{sub.get('_id', '?')}"
                details.append({
                    'tracking_id': tid,
                    'action': 'skipped',
                    'reason': error,
                })
                continue

            tid = mapped['participant']['tracking_id']
            try:
                action = upsert_submission(mapped)
                if action == 'inserted':
                    inserted += 1
                else:
                    updated += 1
                details.append({
                    'tracking_id': tid,
                    'action': action,
                    'reason': None,
                })
            except Exception as e:
                db.session.rollback()
                skipped += 1
                details.append({
                    'tracking_id': tid,
                    'action': 'error',
                    'reason': str(e),
                })
                logger.error(f'{tid}: DB error — {e}')

        db.session.commit()

        # Update sync state timestamp
        state['last_sync'] = datetime.utcnow().isoformat()
        save_sync_state(state)

        # Finalize log
        sync_log.inserted = inserted
        sync_log.updated = updated
        sync_log.skipped = skipped
        sync_log.status = 'success'
        sync_log.finished_at = datetime.utcnow()
        sync_log.details_json = json.dumps(details, ensure_ascii=False)
        db.session.commit()

        logger.info(f'KoboSync complete: {inserted} new, {updated} updated, {skipped} skipped')
        return sync_log

    except Exception as e:
        sync_log.status = 'failed'
        sync_log.error_message = str(e)
        sync_log.finished_at = datetime.utcnow()
        sync_log.details_json = json.dumps(details, ensure_ascii=False) if details else None
        db.session.commit()

        logger.error(f'KoboSync FAILED: {e}')
        return sync_log


def run_sync(app, triggered_by='cli', full_sync=False):
    """Execute a KoboToolbox sync run.

    Safe to call from both Flask routes (already has app context) and CLI (no context).

    Args:
        app: Flask app instance (for config and app context)
        triggered_by: username of the person who triggered the sync
        full_sync: if True, re-fetch all submissions; otherwise incremental

    Returns:
        KoboSyncLog instance with results
    """
    # If already inside an app context (called from a Flask route), run directly.
    # If called from CLI (no context), push a new one.
    import flask
    if flask.has_app_context():
        return _do_sync(app, triggered_by, full_sync)
    else:
        with app.app_context():
            return _do_sync(app, triggered_by, full_sync)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    full_sync = '--full' in sys.argv

    from app import create_app
    app = create_app()

    result = run_sync(app, triggered_by='cli', full_sync=full_sync)
    print(f'\nSync {result.status}: {result.inserted} inserted, {result.updated} updated, {result.skipped} skipped')

    if result.error_message:
        print(f'Error: {result.error_message}')
        sys.exit(1)


if __name__ == '__main__':
    main()
