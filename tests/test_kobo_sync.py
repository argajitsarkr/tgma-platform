"""Tests for KoboToolbox sync validation and mapping logic."""

import sys
import os
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from etl.kobo_sync import (validate_submission, map_submission, safe_float, safe_int,
                            parse_date, yn_to_bool, flatten_kobo_submission)


class TestValidateSubmission:
    """Test critical-field validation — submissions missing required fields are rejected."""

    def test_valid_submission(self):
        sub = {
            'tracking_id': 'TGMA-WT-F-0001',
            'full_name': 'Test Person',
            'gender': 'F',
            'district': 'WT',
        }
        tid, error = validate_submission(sub)
        assert tid == 'TGMA-WT-F-0001'
        assert error is None

    def test_missing_tracking_id(self):
        sub = {'full_name': 'Test', 'gender': 'F', '_id': '999'}
        tid, error = validate_submission(sub)
        assert tid is None
        assert 'Missing tracking_id' in error

    def test_invalid_tracking_id_format(self):
        sub = {'tracking_id': 'BAD-ID', 'full_name': 'Test', 'gender': 'F'}
        tid, error = validate_submission(sub)
        assert 'Invalid format' in error

    def test_missing_full_name(self):
        sub = {'tracking_id': 'TGMA-WT-F-0001', 'full_name': '', 'gender': 'F'}
        tid, error = validate_submission(sub)
        assert 'Missing full_name' in error

    def test_gender_derived_from_tracking_id(self):
        """If gender field is missing, derive from tracking_id."""
        sub = {
            'tracking_id': 'TGMA-WT-M-0005',
            'full_name': 'Test',
            'gender': '',
        }
        tid, error = validate_submission(sub)
        assert error is None  # Accepted — gender derived from ID

    def test_district_derived_from_tracking_id(self):
        """If district field is missing, derive from tracking_id."""
        sub = {
            'tracking_id': 'TGMA-DL-F-0010',
            'full_name': 'Test',
            'gender': 'F',
            'district': '',
        }
        tid, error = validate_submission(sub)
        assert error is None  # Accepted — district derived from ID

    def test_district_slug_accepted_v3(self):
        """XLSForm v3 sends district as a slug (e.g. 'north_tripura'), not 2-letter code."""
        for slug, tid in [
            ('north_tripura', 'TGMA-NT-F-001'),
            ('gomati', 'TGMA-GT-M-002'),
            ('unakoti', 'TGMA-UK-F-003'),
            ('west_tripura', 'TGMA-WT-F-004'),
        ]:
            sub = {'tracking_id': tid, 'full_name': 'Test', 'gender': tid.split('-')[2], 'district': slug}
            _, error = validate_submission(sub)
            assert error is None, f'{slug} should be accepted: {error}'

    def test_district_other_rejected(self):
        """Participants from outside Tripura (district=other on the form) cannot be enrolled
        because tracking IDs only cover the 6 Tripura districts."""
        sub = {
            'tracking_id': 'TGMA-WT-F-001',
            'full_name': 'Test',
            'gender': 'F',
            'district': 'other',
        }
        _, error = validate_submission(sub)
        assert error is not None
        assert 'other' in error.lower()

    def test_completely_invalid_gender_and_no_id_fallback(self):
        """If gender is wrong AND tracking_id has invalid gender, reject at format level."""
        sub = {
            'tracking_id': 'TGMA-WT-X-0001',  # X is not M or F — fails tracking_id format
            'full_name': 'Test',
            'gender': 'X',
        }
        tid, error = validate_submission(sub)
        assert error is not None  # Rejected (invalid tracking_id format since X not in M/F)


class TestMapSubmission:
    """Test full mapping of KoboToolbox submissions to model dicts."""

    def _make_submission(self, **overrides):
        """Create a valid base submission dict."""
        base = {
            'tracking_id': 'TGMA-WT-F-0001',
            'full_name': 'Riya Debbarma',
            'gender': 'F',
            'district': 'WT',
            'age': '15',
            '_id': '12345',
            '_submission_time': '2026-03-15T10:30:00',
        }
        base.update(overrides)
        return base

    def test_successful_mapping(self):
        sub = self._make_submission()
        mapped, error = map_submission(sub)
        assert error is None
        assert mapped['participant']['tracking_id'] == 'TGMA-WT-F-0001'
        assert mapped['participant']['full_name'] == 'Riya Debbarma'
        assert mapped['participant']['age'] == 15
        assert mapped['participant']['gender'] == 'F'

    def test_optional_fields_null(self):
        """Optional sections (anthro, lifestyle) can be completely empty."""
        sub = self._make_submission()
        mapped, error = map_submission(sub)
        assert error is None
        # Anthropometrics should all be None
        assert mapped['anthro']['height_cm'] is None
        assert mapped['anthro']['weight_kg'] is None
        # Lifestyle should all be None
        assert mapped['lifestyle']['vigorous_activity'] is None

    def test_age_out_of_range_rejected(self):
        sub = self._make_submission(age='25')
        mapped, error = map_submission(sub)
        assert mapped is None
        assert 'outside study range' in error

    def test_age_null_accepted(self):
        sub = self._make_submission(age=None)
        mapped, error = map_submission(sub)
        assert error is None
        assert mapped['participant']['age'] is None

    def test_gps_from_geolocation(self):
        sub = self._make_submission(_geolocation=[23.5, 91.5])
        mapped, error = map_submission(sub)
        assert error is None
        assert mapped['participant']['gps_latitude'] == 23.5
        assert mapped['participant']['gps_longitude'] == 91.5

    def test_anthro_with_data(self):
        sub = self._make_submission(height_cm='155.5', weight_kg='48.2')
        mapped, error = map_submission(sub)
        assert error is None
        assert mapped['anthro']['height_cm'] == 155.5
        assert mapped['anthro']['weight_kg'] == 48.2

    def test_menstrual_data_for_female(self):
        sub = self._make_submission(gender='F', menstruation_started='1', menarche_age='13')
        mapped, error = map_submission(sub)
        assert error is None
        assert mapped['menstrual'] is not None
        assert mapped['menstrual']['menarche_age'] == 13

    def test_menstrual_data_not_for_male(self):
        sub = self._make_submission(
            tracking_id='TGMA-WT-M-0002', gender='M',
            menstruation_started='1'
        )
        mapped, error = map_submission(sub)
        assert error is None
        assert mapped['menstrual'] is None

    def test_idempotent_kobo_id(self):
        sub = self._make_submission(_id='67890')
        mapped, error = map_submission(sub)
        assert mapped['participant']['kobo_submission_id'] == '67890'


class TestYnToBool:
    """XLSForm `select_one yn` fields arrive as strings, not booleans.
    Regression: `bool('no')` is True in Python — the old code stored every 'no'
    answer as True. yn_to_bool fixes that.
    """

    def test_yes_variants(self):
        assert yn_to_bool('yes') is True
        assert yn_to_bool('YES') is True
        assert yn_to_bool('Yes') is True
        assert yn_to_bool(True) is True
        assert yn_to_bool('1') is True

    def test_no_variants(self):
        assert yn_to_bool('no') is False
        assert yn_to_bool('NO') is False
        assert yn_to_bool(False) is False
        assert yn_to_bool('0') is False

    def test_blank_returns_none(self):
        assert yn_to_bool(None) is None
        assert yn_to_bool('') is None


class TestHealthYnRegression:
    """Verify yn_to_bool is wired into the health-screening mapping."""

    def test_chronic_illness_no_string_stored_as_false(self):
        sub = {
            'tracking_id': 'TGMA-WT-F-0001',
            'full_name': 'Riya Debbarma',
            'gender': 'F',
            'district': 'WT',
            'chronic_illness': 'no',
            'antibiotics_3mo': 'yes',
            '_id': '1',
            '_submission_time': '2026-04-15T10:00:00',
        }
        mapped, error = map_submission(sub)
        assert error is None
        assert mapped['health']['chronic_illness'] is False
        assert mapped['health']['antibiotics_3mo'] is True


class TestV41GroupFlattening:
    """XLSForm v4.1 has heavy `begin_group` nesting. KoboToolbox API v2 returns
    submission keys with the group path prefixed (e.g. `part_a/tracking_id`).
    Without flattening, `submission.get('tracking_id')` returns None and every
    submission is silently rejected as `Missing tracking_id` — sync log shows
    `status='success'` while persisting zero rows.

    These tests guard against that regression.
    """

    def test_flatten_strips_group_prefix(self):
        sub = {
            'part_a/tracking_id': 'TGMA-WT-F-001',
            'part_a/full_name': 'Riya Debbarma',
            'part_b/b1/b1_chronic_illness': 'no',
            '_id': '42',                # underscore-prefixed Kobo metadata preserved
            '_submission_time': '2026-04-27T10:30:00',
        }
        flat = flatten_kobo_submission(sub)
        assert flat['tracking_id'] == 'TGMA-WT-F-001'
        assert flat['full_name'] == 'Riya Debbarma'
        assert flat['b1_chronic_illness'] == 'no'   # last segment of deep nesting
        assert flat['_id'] == '42'                  # untouched
        assert flat['_submission_time'] == '2026-04-27T10:30:00'

    def test_flatten_idempotent_on_flat_dict(self):
        sub = {'tracking_id': 'TGMA-WT-F-001', 'full_name': 'X'}
        assert flatten_kobo_submission(sub) == sub

    def test_validate_accepts_v41_grouped_submission(self):
        sub = {
            'part_a/tracking_id': 'TGMA-NT-F-007',
            'part_a/full_name': 'Test',
            'part_a/gender': 'female',  # v4.1 slug
            'part_a/district': 'NT',    # v4.1 direct 2-letter
        }
        tid, error = validate_submission(sub)
        assert error is None
        assert tid == 'TGMA-NT-F-007'

    def test_map_v41_grouped_submission_full_path(self):
        """End-to-end: a realistic v4.1 submission produces populated dicts
        for participant + health + anthro + lifestyle + environment."""
        sub = {
            'part_a/tracking_id': 'TGMA-WT-F-001',
            'part_a/full_name': 'Riya Debbarma',
            'part_a/gender': 'female',
            'part_a/district': 'WT',
            'part_a/date_of_birth': '2010-05-15',
            'part_a/age_years': '15',
            'part_a/village_town_ward': 'Agartala Ward 7',
            'part_a/school_name': 'Govt HS Agartala',
            'part_a/class_grade': 'class_10',
            'part_a/religion': 'hindu',
            'part_a/community_tribe': 'tripuri',
            'part_a/mother_tongue': 'kokborok',
            'part_b/b1/b1_chronic_illness': 'no',
            'part_b/b1/b1_recent_antibiotics': 'yes',
            'part_b/b3/b3_delivery_mode': 'c_section',
            'part_b/b3/b3_breastfed': 'exclusive',
            'part_c/c1/c1_sitting_weekday': '2_4',
            'part_c/c1/c1_sitting_weekend': '6_8',
            'part_c/c3/c3_meals_per_day': '3_plus_snacks',
            'part_c/c4/c4_screen_total': '4_6',
            'part_c/c4/c4_sleep_quality': 'good',
            'part_c/c5/c5_q1': '2',
            'part_c/c5/c5_q2': '3',
            'part_c/c6/c6_household_smoke': 'no',
            'part_d/d1/d1_water_source': 'municipal',
            'part_d/d2/d2_income': 'le_10k',
            'part_d/d2/d2_family_size': '4_5',
            'part_d/d2/d2_father_education': 'higher_sec',
            'part_e/e_menarche': 'yes',
            'part_e/e_menarche_age': '13',
            'part_e/e_cycle_regular': 'regular',
            'part_f/anthro/anthro_height_cm': '155.5',
            'part_f/anthro/anthro_weight_kg': '48.2',
            'part_f/anthro/anthro_waist_cm': '68.0',
            'part_f/anthro/anthro_hip_cm': '85.0',
            'part_f/consent/consent_signed_paper': 'yes',
            'part_f/consent/assent_signed_paper': 'yes',
            'part_f/consent/photo_consent': 'yes',
            '_id': '999',
            '_submission_time': '2026-04-27T10:30:00',
            '_geolocation': [23.5, 91.5],
        }
        mapped, error = map_submission(sub)
        assert error is None, f'unexpected error: {error}'

        # Participant
        p = mapped['participant']
        assert p['tracking_id'] == 'TGMA-WT-F-001'
        assert p['gender'] == 'F'                      # slug 'female' translated
        assert p['district'] == 'WT'
        assert p['village_town'] == 'Agartala Ward 7'  # v4.1 field name
        assert p['school_class'] == 'Govt HS Agartala — Class 10'  # concatenated
        assert p['religion'] == 'hindu'
        assert p['consent_parent'] is True             # v4.1 field name
        assert p['assent_participant'] is True

        # Health: bool('no') would be True; yn_to_bool fixes that
        assert mapped['health']['chronic_illness'] is False
        assert mapped['health']['antibiotics_3mo'] is True
        assert mapped['health']['delivery_mode'] == 'csection'   # c_section normalized
        assert mapped['health']['breastfed'] is True             # exclusive → True

        # Anthro: numeric coercion via anthro_* names
        assert mapped['anthro']['height_cm'] == 155.5
        assert mapped['anthro']['weight_kg'] == 48.2

        # Lifestyle: slug → midpoint conversion
        assert mapped['lifestyle']['sedentary_weekday'] == 3.0   # '2_4' midpoint
        assert mapped['lifestyle']['sedentary_weekend'] == 7.0   # '6_8' midpoint
        assert mapped['lifestyle']['meals_per_day'] == 3         # '3_plus_snacks' → 3
        assert mapped['lifestyle']['daily_screen'] == 5.0        # '4_6' midpoint
        assert mapped['lifestyle']['sleep_quality'] == 'good'
        assert mapped['lifestyle']['pss_control'] == 2
        assert mapped['lifestyle']['passive_smoke'] is False

        # Environment
        assert mapped['environment']['water_source'] == 'municipal'
        assert mapped['environment']['household_income'] == 'le_10k'
        assert mapped['environment']['household_size'] == 5      # '4_5' midpoint

        # Menstrual
        assert mapped['menstrual']['menstruation_started'] is True
        assert mapped['menstrual']['menarche_age'] == 13
        assert mapped['menstrual']['cycle_regularity'] == 'regular'

    def test_v3_flat_submission_still_works(self):
        """Regression guard: pre-v4.1 flat submissions must still parse correctly."""
        sub = {
            'tracking_id': 'TGMA-WT-F-0001',
            'full_name': 'Legacy Person',
            'gender': 'F',                # 2-letter (pre-v4.1)
            'district': 'west_tripura',   # v3 slug
            'chronic_illness': 'no',
            'delivery_mode': 'csection',
            'sedentary_weekday': '4.5',   # legacy numeric
            'meals_per_day': '3',
            '_id': '1',
            '_submission_time': '2026-03-01T10:00:00',
        }
        mapped, error = map_submission(sub)
        assert error is None
        assert mapped['participant']['district'] == 'WT'
        assert mapped['participant']['gender'] == 'F'
        assert mapped['health']['chronic_illness'] is False
        assert mapped['health']['delivery_mode'] == 'csection'
        assert mapped['lifestyle']['sedentary_weekday'] == 4.5
        assert mapped['lifestyle']['meals_per_day'] == 3


class TestHelpers:
    """Test safe type conversion helpers."""

    def test_safe_float(self):
        assert safe_float('3.14') == 3.14
        assert safe_float('') is None
        assert safe_float(None) is None
        assert safe_float('abc') is None

    def test_safe_int(self):
        assert safe_int('15') == 15
        assert safe_int('15.7') == 15  # Truncates
        assert safe_int('') is None
        assert safe_int(None) is None

    def test_parse_date(self):
        d = parse_date('2026-03-15')
        assert d is not None
        assert d.year == 2026
        assert d.month == 3
        assert parse_date('') is None
        assert parse_date(None) is None
        assert parse_date('not-a-date') is None
