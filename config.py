import os
from datetime import timedelta

basedir = os.path.abspath(os.path.dirname(__file__))


class BaseConfig:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-key-change-in-production')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', 50 * 1024 * 1024))
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', os.path.join(basedir, 'uploads'))
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)

    # TGMA study parameters
    TARGET_ENROLLMENT = 440
    TARGET_SEQUENCING = 160
    DISTRICT_TARGETS = {'WT': 200, 'ST': 100, 'DL': 100}
    LIFESTYLE_GROUPS = ['AT', 'AP', 'SDT', 'SP']
    LIFESTYLE_TARGET_EACH = 100
    SEQUENCING_BATCH_SIZE = 32

    # Budget in Lakhs INR
    BUDGET_SEQUENCING = float(os.environ.get('BUDGET_SEQUENCING', 30))
    BUDGET_HORMONES = float(os.environ.get('BUDGET_HORMONES', 11))
    BUDGET_SHIPMENT = float(os.environ.get('BUDGET_SHIPMENT', 1))

    # GPS bounds for Tripura
    GPS_LAT_MIN = 22.9
    GPS_LAT_MAX = 24.5
    GPS_LON_MIN = 91.1
    GPS_LON_MAX = 92.3


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        'postgresql://tgma_user:tgma_pass@localhost:5432/tgma_db'
    )


class ProductionConfig(BaseConfig):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'


class TestingConfig(BaseConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
    LOGIN_DISABLED = False


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig,
}
