"""Pytest configuration and fixtures for TGMA platform tests."""

import pytest
from app import create_app
from app.extensions import db as _db
from app.models import User


@pytest.fixture(scope='session')
def app():
    """Create application for testing."""
    app = create_app('testing')
    with app.app_context():
        yield app


@pytest.fixture(scope='session')
def database(app):
    """Create database tables for the test session."""
    with app.app_context():
        _db.create_all()
        yield _db
        _db.drop_all()


@pytest.fixture(autouse=True)
def session(database, app):
    """Create a clean database session for each test."""
    with app.app_context():
        yield database.session
        database.session.rollback()


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture
def pi_user(database, app):
    """Create a PI user for authenticated tests."""
    with app.app_context():
        user = User.query.filter_by(username='test_pi').first()
        if not user:
            user = User(username='test_pi', full_name='Test PI', role='pi')
            user.set_password('testpass')
            database.session.add(user)
            database.session.commit()
        yield user


@pytest.fixture
def auth_client(client, pi_user):
    """Authenticated test client (logged in as PI)."""
    client.post('/login', data={
        'username': 'test_pi',
        'password': 'testpass',
    }, follow_redirects=True)
    return client
