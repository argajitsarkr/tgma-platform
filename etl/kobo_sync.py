#!/usr/bin/env python3
"""KoboToolbox → PostgreSQL sync script.

Connects to the KoboToolbox REST API, downloads all submissions since
the last sync, and upserts them into the TGMA database.

Usage:
    python etl/kobo_sync.py                # Sync all new submissions
    python etl/kobo_sync.py --full         # Full re-sync (all submissions)

Can also be run via cron:
    0 0 * * * cd /opt/tgma-platform && python etl/kobo_sync.py >> /var/log/tgma_kobo_sync.log 2>&1
"""

import os
import sys
import json
import logging
from datetime import datetime, date

import requests

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.extensions import db
from app.models import (Participant, HealthScreening, Anthropometrics, MenstrualData,
                         LifestyleData, EnvironmentSES)
from app.utils.helpers import validate_tracking_id, validate_gps, validate_age

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Sync state file — stores the last sync timestamp
SYNC_STATE_FILE = os.path.join(os.path.dirname(__file__), '.kobo_sync_state.json')


def load_sync_state():
    if os.path.exists(SYNC_STATE_FILE):
        with open(SYNC_STATE_FILE, 'r') as f:
            return json.load(f)
    return {'last_sync': None}


def save_sync_state(state):
    with open(SYNC_STATE_FILE, 'w') as f:
        json.dump(state, f)


def fetch_submissions(api_url, token, form_id, since=None):
    """Fetch submissions from KoboToolbox API with pagination."""
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

    logger.info(f'Fetched {len(all_results)} submissions')
    return all_results


def map_participant(submission):
    """Map a KoboToolbox submission to participant fields.

    The actual field names depend on your KoboToolbox form design.
    Adjust the keys below to match your form's field names.
    """
    # These are example mappings — adjust to match your KoboCollect form
    tracking_id = str(submission.get('tracking_id', '')).strip().upper()
    if not tracking_id:
        return None, 'Missing tracking_id'

    if not validate_tracking_id(tracking_id):
        return None, f'Invalid tracking_id format: {tracking_id}'

    age = submission.get('age')
    if age is not None:
        try:
            age = int(age)
        except (ValueError, TypeError):
            age = None

    if not validate_age(age):
        return None, f'{tracking_id}: Age {age} outside range 12-18'

    lat = submission.get('_geolocation', [None, None])[0] or submission.get('gps_latitude')
    lon = submission.get('_geolocation', [None, None])[1] or submission.get('gps_longitude')

    if not validate_gps(lat, lon):
        return None, f'{tracking_id}: GPS ({lat}, {lon}) outside Tripura bounds'

    gender = str(submission.get('gender', '')).strip().upper()
    if gender not in ('M', 'F'):
        gender = tracking_id.split('-')[2] if len(tracking_id.split('-')) >= 3 else 'M'

    district = tracking_id.split('-')[1] if len(tracking_id.split('-')) >= 2 else ''

    participant_data = {
        'tracking_id': tracking_id,
        'full_name': str(submission.get('full_name', '')).strip(),
        'age': age,
        'gender': gender,
        'district': district,
        'dob': parse_date(submission.get('dob')),
        'village_town': str(submission.get('village_town', '')).strip(),
        'guardian_phone': str(submission.get('guardian_phone', '')).strip(),
        'school_class': str(submission.get('school_class', '')).strip(),
        'religion': str(submission.get('religion', '')).strip(),
        'community_tribe': str(submission.get('community_tribe', '')).strip(),
        'mother_tongue': str(submission.get('mother_tongue', '')).strip(),
        'enrollment_date': parse_date(submission.get('_submission_time', '').split('T')[0]),
        'enrollment_status': 'enrolled',
        'field_worker_name': str(submission.get('field_worker', '')).strip(),
        'gps_latitude': lat,
        'gps_longitude': lon,
        'consent_parent': bool(submission.get('consent_parent')),
        'assent_participant': bool(submission.get('assent_participant')),
        'photo_consent': bool(submission.get('photo_consent')),
        'kobo_submission_id': str(submission.get('_id', '')),
    }

    # Related data
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
        'passive_smoke': bool(submission.get('passive_smoke')),
    }

    env_data = {
        'water_source': submission.get('water_source'),
        'cooking_fuel': submission.get('cooking_fuel'),
        'toilet_type': submission.get('toilet_type'),
        'household_income': submission.get('household_income'),
        'household_size': safe_int(submission.get('household_size')),
        'father_edu': submission.get('father_edu'),
        'mother_edu': submission.get('mother_edu'),
    }

    menstrual_data = None
    if gender == 'F' and submission.get('menstruation_started'):
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


def upsert_submission(mapped):
    """Insert or update a participant and related records."""
    p_data = mapped['participant']
    tid = p_data['tracking_id']

    existing = db.session.get(Participant, tid)
    if existing:
        # Update existing
        for key, val in p_data.items():
            if key != 'tracking_id' and val is not None:
                setattr(existing, key, val)
        logger.info(f'  Updated: {tid}')
    else:
        participant = Participant(**p_data)
        db.session.add(participant)
        logger.info(f'  Inserted: {tid}')

    # Health screening
    hs = HealthScreening.query.filter_by(tracking_id=tid).first()
    if not hs:
        hs = HealthScreening(tracking_id=tid)
        db.session.add(hs)
    for key, val in mapped['health'].items():
        if val is not None:
            setattr(hs, key, val)

    # Anthropometrics
    anthro = Anthropometrics.query.filter_by(tracking_id=tid).first()
    if not anthro:
        anthro = Anthropometrics(tracking_id=tid)
        db.session.add(anthro)
    for key, val in mapped['anthro'].items():
        if val is not None:
            setattr(anthro, key, val)

    # Lifestyle
    ld = LifestyleData.query.filter_by(tracking_id=tid).first()
    if not ld:
        ld = LifestyleData(tracking_id=tid)
        db.session.add(ld)
    for key, val in mapped['lifestyle'].items():
        if val is not None:
            setattr(ld, key, val)

    # Environment
    env = EnvironmentSES.query.filter_by(tracking_id=tid).first()
    if not env:
        env = EnvironmentSES(tracking_id=tid)
        db.session.add(env)
    for key, val in mapped['environment'].items():
        if val is not None:
            setattr(env, key, val)

    # Menstrual (girls only)
    if mapped['menstrual']:
        md = MenstrualData.query.filter_by(tracking_id=tid).first()
        if not md:
            md = MenstrualData(tracking_id=tid)
            db.session.add(md)
        for key, val in mapped['menstrual'].items():
            if val is not None:
                setattr(md, key, val)


def main():
    full_sync = '--full' in sys.argv

    app = create_app()
    with app.app_context():
        api_url = app.config.get('KOBO_API_URL', os.environ.get('KOBO_API_URL', ''))
        token = os.environ.get('KOBO_API_TOKEN', '')
        form_id = os.environ.get('KOBO_FORM_ID', '')

        if not all([api_url, token, form_id]):
            logger.error('Missing KoboToolbox credentials. Set KOBO_API_URL, KOBO_API_TOKEN, KOBO_FORM_ID.')
            sys.exit(1)

        state = load_sync_state()
        since = None if full_sync else state.get('last_sync')

        logger.info(f'Starting KoboToolbox sync (since={since or "beginning"})')

        try:
            submissions = fetch_submissions(api_url, token, form_id, since)
        except requests.RequestException as e:
            logger.error(f'API request failed: {e}')
            sys.exit(1)

        inserted, updated, errors = 0, 0, []
        for sub in submissions:
            mapped, error = map_participant(sub)
            if error:
                errors.append(error)
                continue

            tid = mapped['participant']['tracking_id']
            existing = db.session.get(Participant, tid)
            try:
                upsert_submission(mapped)
                if existing:
                    updated += 1
                else:
                    inserted += 1
            except Exception as e:
                errors.append(f'{tid}: {e}')
                db.session.rollback()

        db.session.commit()

        # Update sync state
        state['last_sync'] = datetime.utcnow().isoformat()
        save_sync_state(state)

        logger.info(f'Sync complete: {inserted} new, {updated} updated, {len(errors)} errors')
        for err in errors:
            logger.warning(f'  Error: {err}')


if __name__ == '__main__':
    main()
