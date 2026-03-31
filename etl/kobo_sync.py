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
from app.utils.helpers import validate_tracking_id, validate_gps, validate_age

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
    """
    tracking_id = str(submission.get('tracking_id', '')).strip().upper()
    if not tracking_id:
        kobo_id = submission.get('_id', '?')
        return None, f'Kobo #{kobo_id}: Missing tracking_id — skipped'

    if not validate_tracking_id(tracking_id):
        return tracking_id, f'{tracking_id}: Invalid format (expected TGMA-XX-X-0000) — skipped'

    full_name = str(submission.get('full_name', '')).strip()
    if not full_name:
        return tracking_id, f'{tracking_id}: Missing full_name — skipped'

    gender = str(submission.get('gender', '')).strip().upper()
    if gender not in ('M', 'F'):
        # Try to derive from tracking_id (TGMA-WT-F-0001 → F)
        parts = tracking_id.split('-')
        if len(parts) >= 3 and parts[2] in ('M', 'F'):
            gender = parts[2]
        else:
            return tracking_id, f'{tracking_id}: Missing/invalid gender — skipped'

    district = str(submission.get('district', '')).strip().upper()
    if district not in ('WT', 'ST', 'DL'):
        # Derive from tracking_id
        parts = tracking_id.split('-')
        if len(parts) >= 2 and parts[1] in ('WT', 'ST', 'DL'):
            district = parts[1]
        else:
            return tracking_id, f'{tracking_id}: Missing/invalid district — skipped'

    return tracking_id, None  # Valid


def map_submission(submission):
    """Map a KoboToolbox submission dict to our model dicts.

    Returns (mapped_dict, None) on success, (None, error_string) on validation failure.
    Optional sections that are empty come through as NULL — that's fine.
    """
    # --- Critical field validation ---
    tracking_id, error = validate_submission(submission)
    if error:
        return None, error

    # --- Parse all fields (NULLs are OK for optional ones) ---
    age = safe_int(submission.get('age'))
    if age is not None and not validate_age(age):
        return None, f'{tracking_id}: Age {age} outside study range 12-18 — skipped'

    # GPS — optional, but if present must be within Tripura bounds
    geoloc = submission.get('_geolocation', [None, None])
    lat = geoloc[0] if geoloc and len(geoloc) > 0 else None
    lon = geoloc[1] if geoloc and len(geoloc) > 1 else None
    lat = lat or safe_float(submission.get('gps_latitude'))
    lon = lon or safe_float(submission.get('gps_longitude'))

    if lat is not None and lon is not None:
        if not validate_gps(lat, lon):
            # GPS out of bounds is a WARNING, not a rejection — accept with flag
            logger.warning(f'{tracking_id}: GPS ({lat}, {lon}) outside Tripura bounds — accepted anyway')

    gender = str(submission.get('gender', '')).strip().upper()
    if gender not in ('M', 'F'):
        gender = tracking_id.split('-')[2] if len(tracking_id.split('-')) >= 3 else 'M'

    district = tracking_id.split('-')[1] if len(tracking_id.split('-')) >= 2 else ''

    # --- Participant (demographics) ---
    participant_data = {
        'tracking_id': tracking_id,
        'full_name': str(submission.get('full_name', '')).strip(),
        'age': age,
        'gender': gender,
        'district': district,
        'dob': parse_date(submission.get('dob')),
        'village_town': str(submission.get('village_town', '')).strip() or None,
        'guardian_phone': str(submission.get('guardian_phone', '')).strip() or None,
        'school_class': str(submission.get('school_class', '')).strip() or None,
        'religion': str(submission.get('religion', '')).strip() or None,
        'community_tribe': str(submission.get('community_tribe', '')).strip() or None,
        'mother_tongue': str(submission.get('mother_tongue', '')).strip() or None,
        'enrollment_date': parse_date(submission.get('_submission_time', '').split('T')[0]),
        'enrollment_status': 'enrolled',
        'field_worker_name': str(submission.get('field_worker', '')).strip() or None,
        'gps_latitude': lat,
        'gps_longitude': lon,
        'consent_parent': bool(submission.get('consent_parent')),
        'assent_participant': bool(submission.get('assent_participant')),
        'photo_consent': bool(submission.get('photo_consent')),
        'kobo_submission_id': str(submission.get('_id', '')),
    }

    # --- Health screening (Part B) ---
    health_data = {
        'chronic_illness': bool(submission.get('chronic_illness')),
        'antibiotics_3mo': bool(submission.get('antibiotics_3mo')),
        'hospital_3mo': bool(submission.get('hospital_3mo')),
        'genetic_disorder': bool(submission.get('genetic_disorder')),
        'pregnant': bool(submission.get('pregnant')),
        'regular_medication': bool(submission.get('regular_medication')),
        'medication_details': str(submission.get('medication_details', '')).strip() or None,
        'fam_diabetes': submission.get('fam_diabetes'),
        'fam_obesity': submission.get('fam_obesity'),
        'fam_hypertension': submission.get('fam_hypertension'),
        'delivery_mode': submission.get('delivery_mode'),
        'breastfed': bool(submission.get('breastfed')),
        'bf_duration': submission.get('bf_duration'),
    }

    # --- Anthropometrics (Part G) — field worker may fill this later ---
    anthro_data = {
        'height_cm': safe_float(submission.get('height_cm')),
        'weight_kg': safe_float(submission.get('weight_kg')),
        'waist_cm': safe_float(submission.get('waist_cm')),
        'hip_cm': safe_float(submission.get('hip_cm')),
        'bp_systolic': safe_int(submission.get('bp_systolic')),
        'bp_diastolic': safe_int(submission.get('bp_diastolic')),
        'heart_rate': safe_int(submission.get('heart_rate')),
        'tanner_stage': safe_int(submission.get('tanner_stage')),
        'measurement_date': parse_date(submission.get('_submission_time', '').split('T')[0]),
    }

    # --- Lifestyle & FFQ (Part D/E) ---
    lifestyle_data = {
        'vigorous_activity': submission.get('vigorous_activity'),
        'moderate_activity': submission.get('moderate_activity'),
        'sedentary_weekday': safe_float(submission.get('sedentary_weekday')),
        'sedentary_weekend': safe_float(submission.get('sedentary_weekend')),
        'meals_per_day': safe_int(submission.get('meals_per_day')),
        'sleep_quality': submission.get('sleep_quality'),
        'daily_screen': safe_float(submission.get('daily_screen')),
        'pss_control': safe_int(submission.get('pss_control')),
        'pss_confident': safe_int(submission.get('pss_confident')),
        'pss_going_well': safe_int(submission.get('pss_going_well')),
        'pss_overwhelmed': safe_int(submission.get('pss_overwhelmed')),
        'passive_smoke': bool(submission.get('passive_smoke')) if submission.get('passive_smoke') is not None else None,
    }

    # --- Environment & SES (Part F) ---
    env_data = {
        'water_source': submission.get('water_source'),
        'cooking_fuel': submission.get('cooking_fuel'),
        'toilet_type': submission.get('toilet_type'),
        'household_income': submission.get('household_income'),
        'household_size': safe_int(submission.get('household_size')),
        'father_edu': submission.get('father_edu'),
        'mother_edu': submission.get('mother_edu'),
    }

    # --- Menstrual data (Part C, girls only) ---
    menstrual_data = None
    if gender == 'F' and submission.get('menstruation_started') is not None:
        menstrual_data = {
            'menstruation_started': bool(submission.get('menstruation_started')),
            'menarche_age': safe_int(submission.get('menarche_age')),
            'cycle_regularity': submission.get('cycle_regularity'),
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

def run_sync(app, triggered_by='cli', full_sync=False):
    """Execute a KoboToolbox sync run.

    Args:
        app: Flask app instance (for config and app context)
        triggered_by: username of the person who triggered the sync
        full_sync: if True, re-fetch all submissions; otherwise incremental

    Returns:
        KoboSyncLog instance with results
    """
    with app.app_context():
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
