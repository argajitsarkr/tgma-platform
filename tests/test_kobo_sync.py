"""Tests for KoboToolbox sync validation and mapping logic."""

import sys
import os
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from etl.kobo_sync import (validate_submission, map_submission, safe_float, safe_int,
                            parse_date, yn_to_bool)


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
