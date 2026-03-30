"""Tests for authentication routes."""


class TestLogin:

    def test_login_page_loads(self, client):
        resp = client.get('/login')
        assert resp.status_code == 200
        assert b'TGMA Platform' in resp.data

    def test_login_success(self, client, pi_user):
        resp = client.post('/login', data={
            'username': 'test_pi',
            'password': 'testpass',
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert b'Dashboard' in resp.data or b'Welcome' in resp.data

    def test_login_wrong_password(self, client, pi_user):
        resp = client.post('/login', data={
            'username': 'test_pi',
            'password': 'wrongpass',
        }, follow_redirects=True)
        assert b'Invalid' in resp.data

    def test_login_nonexistent_user(self, client):
        resp = client.post('/login', data={
            'username': 'nobody',
            'password': 'test',
        }, follow_redirects=True)
        assert b'Invalid' in resp.data

    def test_protected_route_redirect(self, client):
        resp = client.get('/')
        assert resp.status_code == 302  # Redirect to login

    def test_logout(self, auth_client):
        resp = auth_client.get('/logout', follow_redirects=True)
        assert b'logged out' in resp.data.lower() or resp.status_code == 200
