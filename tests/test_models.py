"""Tests for TGMA data models and utility functions."""

import pytest
from app.models import Participant, Anthropometrics, HormoneResult, Sample, User
from app.utils.helpers import (
    validate_tracking_id, generate_tracking_id, generate_sample_id,
    validate_gps, validate_age,
)


class TestTrackingIdValidation:

    def test_valid_ids(self):
        assert validate_tracking_id('TGMA-WT-F-037')      # 3-digit (new format)
        assert validate_tracking_id('TGMA-ST-M-001')
        assert validate_tracking_id('TGMA-DL-F-999')
        assert validate_tracking_id('TGMA-WT-F-0037')     # 4-digit (legacy)
        assert validate_tracking_id('TGMA-ST-M-0001')

    def test_invalid_ids(self):
        assert not validate_tracking_id('TGMA-XX-F-001')
        assert not validate_tracking_id('TGMA-WT-X-001')
        assert not validate_tracking_id('TGMA-WT-F-01')   # 2 digits
        assert not validate_tracking_id('XYZ-WT-F-001')
        assert not validate_tracking_id('')
        assert not validate_tracking_id('TGMA-WT-F-00001')  # 5 digits

    def test_generate_tracking_id(self):
        assert generate_tracking_id('WT', 'F', 37) == 'TGMA-WT-F-037'
        assert generate_tracking_id('DL', 'M', 1) == 'TGMA-DL-M-001'
        assert generate_tracking_id('ST', 'F', 999) == 'TGMA-ST-F-999'


class TestSampleIdGeneration:

    def test_generate_sample_ids(self):
        assert generate_sample_id('TGMA-WT-F-0037', 'stool') == 'TGMA-WT-F-0037-STL'
        assert generate_sample_id('TGMA-WT-F-0037', 'blood') == 'TGMA-WT-F-0037-BLD'
        assert generate_sample_id('TGMA-WT-F-0037', 'saliva_1') == 'TGMA-WT-F-0037-SLV1'
        assert generate_sample_id('TGMA-WT-F-0037', 'dna_extract') == 'TGMA-WT-F-0037-DNA'
        assert generate_sample_id('TGMA-WT-F-0037', 'serum') == 'TGMA-WT-F-0037-SRM'

    def test_invalid_sample_type(self):
        with pytest.raises(ValueError):
            generate_sample_id('TGMA-WT-F-0037', 'invalid')


class TestGPSValidation:

    def test_valid_gps(self):
        assert validate_gps(23.5, 91.5)
        assert validate_gps(22.9, 91.1)  # boundary
        assert validate_gps(24.5, 92.3)  # boundary

    def test_invalid_gps(self):
        assert not validate_gps(22.0, 91.5)  # lat too low
        assert not validate_gps(25.0, 91.5)  # lat too high
        assert not validate_gps(23.5, 90.0)  # lon too low
        assert not validate_gps(23.5, 93.0)  # lon too high

    def test_null_gps(self):
        assert validate_gps(None, None)


class TestAgeValidation:

    def test_valid_ages(self):
        assert validate_age(12)
        assert validate_age(15)
        assert validate_age(18)

    def test_invalid_ages(self):
        assert not validate_age(11)
        assert not validate_age(19)
        assert not validate_age(0)

    def test_null_age(self):
        assert validate_age(None)


class TestAnthropometrics:

    def test_bmi_calculation(self, app):
        with app.app_context():
            a = Anthropometrics(tracking_id='TGMA-WT-F-0001', height_cm=160, weight_kg=50)
            assert a.bmi == pytest.approx(19.5, rel=0.1)

    def test_bmi_none_on_missing_data(self, app):
        with app.app_context():
            a = Anthropometrics(tracking_id='TGMA-WT-F-0001', height_cm=None, weight_kg=50)
            assert a.bmi is None

    def test_waist_hip_ratio(self, app):
        with app.app_context():
            a = Anthropometrics(tracking_id='TGMA-WT-F-0001', waist_cm=68, hip_cm=80)
            assert a.waist_hip_ratio == pytest.approx(0.85, rel=0.01)


class TestHormoneResult:

    def test_homa_ir(self, app):
        with app.app_context():
            h = HormoneResult(tracking_id='TGMA-WT-F-0001',
                              fasting_glucose_mg_dl=90, insulin_uiu_ml=10)
            assert h.homa_ir == pytest.approx(2.22, rel=0.01)

    def test_tg_hdl_ratio(self, app):
        with app.app_context():
            h = HormoneResult(tracking_id='TGMA-WT-F-0001',
                              triglycerides_mg_dl=150, hdl_mg_dl=50)
            assert h.tg_hdl_ratio == pytest.approx(3.0)

    def test_homa_ir_none(self, app):
        with app.app_context():
            h = HormoneResult(tracking_id='TGMA-WT-F-0001',
                              fasting_glucose_mg_dl=None, insulin_uiu_ml=10)
            assert h.homa_ir is None


class TestUserModel:

    def test_password_hashing(self, app):
        with app.app_context():
            u = User(username='test', full_name='Test', role='pi')
            u.set_password('secret')
            assert u.check_password('secret')
            assert not u.check_password('wrong')

    def test_has_role(self, app):
        with app.app_context():
            u = User(username='test', full_name='Test', role='pi')
            assert u.has_role('pi', 'co_pi')
            assert not u.has_role('bioinformatician')
