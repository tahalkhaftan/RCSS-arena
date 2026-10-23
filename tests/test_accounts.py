"""Account security and subscription behavior without Google or bank traffic."""
import base64
import io
import json
import os
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from http.cookiejar import CookieJar
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import accounts
from app import Handler


def fixture(person='google:test', tier='free', owner=False):
    with accounts.database() as db:
        db.execute('INSERT OR IGNORE INTO people(id,email) VALUES (?,?)', (person, 'test@gmail.com'))
    return SimpleNamespace(account={'id': person, 'tier': tier, 'owner': owner, 'guest': False})


class Accounts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'ARENA_ACCOUNT_DB': str(Path(self.temp.name)/'accounts.sqlite3'),
            'ARENA_USER': 'owner@example.com', 'ARENA_PASSWORD': 'owner-secret',
            'ARENA_OWNER_EMAIL': '', 'ARENA_OWNER_GOOGLE_SUB': '', 'ARENA_PUBLIC_URL': '',
            'GOOGLE_CLIENT_ID': '', 'GOOGLE_CLIENT_SECRET': ''})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def config(self, games=1, **kw):
        return {'rounds': 1, 'games_per_round': games, **kw}

    def test_signed_in_quota_is_30_games_per_rolling_24_hours(self):
        h = fixture()
        now = 1900000000
        with patch('accounts.time.time', return_value=now):
            accounts.finish(accounts.reserve(h, self.config(20)), True)
        with patch('accounts.time.time', return_value=now+3600):
            accounts.finish(accounts.reserve(fixture(), self.config(10)), True)
            self.assertEqual(accounts.quota_status(h.account)['remaining_games'], 0)
            with self.assertRaises(ValueError):
                accounts.reserve(h, self.config())
        with patch('accounts.time.time', return_value=now+86400):
            self.assertEqual(accounts.quota_status(h.account)['remaining_games'], 20)
            accounts.finish(accounts.reserve(h, self.config(20)), True)
            with self.assertRaises(ValueError):
                accounts.reserve(h, self.config())
        with patch('accounts.time.time', return_value=now+90000):
            self.assertEqual(accounts.quota_status(h.account)['remaining_games'], 10)

    def test_rejected_submission_refund_is_idempotent(self):
        h = fixture()
        ticket = accounts.reserve(h, self.config(30))
        accounts.finish(ticket, False)
        accounts.finish(ticket, False)
        self.assertEqual(accounts.quota_status(h.account)['remaining_games'], 30)
        accounts.finish(accounts.reserve(h, self.config(30)), True)
        with self.assertRaises(ValueError):
            accounts.reserve(h, self.config())

    def test_multiple_rounds_count_every_game(self):
        h = fixture()
        accounts.finish(accounts.reserve(h, {'rounds': 5, 'games_per_round': 6}), True)
        self.assertEqual(accounts.quota_status(h.account)['remaining_games'], 0)
        with self.assertRaises(ValueError):
            accounts.reserve(fixture('google:other'), self.config(31))

    def test_simultaneous_requests_cannot_overspend_daily_quota(self):
        h = fixture()
        def submit(_):
            try:
                accounts.finish(accounts.reserve(h, self.config()), True)
                return True
            except ValueError:
                return False
        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(sum(pool.map(submit, range(42))), 30)

    def test_plus_batch_cap_unlimited_runs_and_no_tier_forgery(self):
        h = fixture(tier='plus')
        for _ in range(7):
            config = self.config(100, export_tier='pro')
            accounts.finish(accounts.reserve(h, config), True)
            self.assertEqual(config['export_tier'], 'plus')
        with self.assertRaises(ValueError):
            accounts.reserve(h, self.config(101))
        with self.assertRaises(ValueError):
            accounts.reserve(h, self.config(offline_logging=True))
        for tier in ('pro', 'owner'):
            accounts.finish(accounts.reserve(fixture(tier=tier), self.config(500, debug_logging=True)), True)

    def test_month_renewal_handles_short_month(self):
        from datetime import datetime, timezone
        start = datetime(2026, 1, 31, 10, tzinfo=timezone.utc).timestamp()
        self.assertEqual(datetime.fromtimestamp(accounts.month_after(start), timezone.utc).isoformat(), '2026-02-28T10:00:00+00:00')

    def test_job_ownership_and_legacy_jobs_are_private(self):
        a = fixture().account
        b = fixture('google:other').account
        accounts.bind(a, 'tests', '7')
        self.assertTrue(accounts.owns(a, 'tests', '7'))
        self.assertFalse(accounts.owns(b, 'tests', '7'))
        self.assertFalse(accounts.owns(a, 'tests', 'old'))
        self.assertTrue(accounts.owns(fixture('owner', 'owner', True).account, 'tests', 'old'))

    def test_download_filters_old_archives_by_current_entitlement(self):
        source = io.BytesIO()
        with zipfile.ZipFile(source, 'w') as z:
            for name in ('match.rcg', 'match.rcl', 'results.json', 'replay.json.gz', 'dataset.csv', 'debug.log'):
                z.writestr(name, b'fixture')
        source.seek(0)
        h = fixture(tier='plus')
        h.wfile = io.BytesIO()
        h.send_response = lambda _: None
        h.send_header = lambda *args: None
        h.end_headers = lambda: None
        accounts.send_archive(h, source, len(source.getvalue()))
        with zipfile.ZipFile(h.wfile) as z:
            self.assertEqual(set(z.namelist()), {'match.rcg', 'match.rcl', 'results.json', 'replay.json.gz'})


class AccountHTTP(unittest.TestCase):
    config = Accounts.config
    def setUp(self):
        Accounts.setUp(self)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = 'http://127.0.0.1:' + str(self.server.server_port)
        self.jar = CookieJar()
        self.client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        Accounts.tearDown(self)

    def request(self, path, body=None, owner=False, origin=True):
        headers = {'Origin': self.base} if origin else {}
        if owner:
            headers['Authorization'] = 'Basic ' + base64.b64encode(b'owner@example.com:owner-secret').decode()
        if body is not None:
            headers['Content-Type'] = 'application/json'
        with self.client.open(urllib.request.Request(self.base+path, data=json.dumps(body).encode() if body is not None else None, headers=headers), timeout=5) as response:
            return response.read()

    def login_user(self, person='google:test'):
        fixture(person)
        token = 'fixture-session'
        with accounts.database() as db:
            db.execute('INSERT OR REPLACE INTO sessions VALUES (?,?,?)', (accounts.digest(token), person, time.time()+3600))
        from http.cookiejar import Cookie
        self.jar.set_cookie(Cookie(0, accounts.COOKIE, token, None, False, '127.0.0.1', False, False, '/', True, False, None, False, None, None, {}))

    def test_public_login_owner_bypass_and_session_logout(self):
        self.assertIn('ورود'.encode(), self.request('/login'))
        guest = json.loads(self.request('/api/account'))
        self.assertTrue(guest['guest'])
        self.assertEqual(guest['remaining_games'], 5)
        self.request('/api/auth/owner', {'email': 'owner@example.com', 'password': 'owner-secret'})
        owner = json.loads(self.request('/api/account'))
        self.assertTrue(owner['owner'])
        self.assertEqual(owner['tier'], 'owner')
        self.request('/api/auth/logout', {})
        self.assertTrue(json.loads(self.request('/api/account'))['guest'])

    def test_guest_cookies_do_not_share_job_identity_but_share_quota_bucket(self):
        self.request('/api/account')
        token = next(iter(self.jar)).value
        with accounts.database() as db:
            person = db.execute('SELECT person FROM sessions WHERE token=?', (accounts.digest(token),)).fetchone()[0]
        h = SimpleNamespace(headers={'Cookie': accounts.COOKIE+'='+token}, client_address=('127.0.0.1', 1))
        account = accounts.identity(h)
        accounts.finish(accounts.reserve(h, self.config(5)), True)
        self.jar.clear()
        self.assertEqual(json.loads(self.request('/api/account'))['remaining_games'], 0)
        token2 = next(iter(self.jar)).value
        with accounts.database() as db:
            person2 = db.execute('SELECT person FROM sessions WHERE token=?', (accounts.digest(token2),)).fetchone()[0]
        self.assertNotEqual(person, person2)
        accounts.bind(account, 'tests', 'secret')
        self.assertFalse(accounts.owns({'id': person2, 'owner': False}, 'tests', 'secret'))

    def test_subscription_requires_owner_confirmation_and_cannot_be_approved_twice(self):
        self.login_user()
        payment = json.loads(self.request('/api/payments', {'plan': 'plus', 'reference': '123456789'}))
        self.assertEqual(json.loads(self.request('/api/account'))['tier'], 'free')
        approve = '/api/admin/payments/'+payment['id']+'/approve'
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request(approve, {})
        self.assertEqual(error.exception.code, 403)
        self.request(approve, {}, owner=True)
        self.assertEqual(json.loads(self.request('/api/account'))['tier'], 'plus')
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request(approve, {}, owner=True)
        self.assertEqual(error.exception.code, 400)
        with accounts.database() as db:
            db.execute('UPDATE people SET expires=? WHERE id=?', (time.time()-1, 'google:test'))
        self.assertEqual(json.loads(self.request('/api/account'))['tier'], 'free')

    def test_signin_signup_pages_and_daily_api_quota(self):
        for path in ('/login', '/signin', '/signup'):
            page = self.request(path)
            self.assertIn(b'/auth-ui.js', page)
            self.assertIn('۳۰ بازی'.encode(), page)
        self.assertIn(b"location.assign('/auth/google')", self.request('/auth-ui.js'))
        self.login_user()
        account = json.loads(self.request('/api/account'))
        self.assertEqual(account['remaining_games'], 30)
        self.assertEqual(account['quota_window_seconds'], 86400)
        accounts.finish(accounts.reserve(fixture(), self.config(12)), True)
        self.assertEqual(json.loads(self.request('/api/account'))['remaining_games'], 18)
        self.request('/api/auth/logout', {})
        self.login_user()
        self.assertEqual(json.loads(self.request('/api/account'))['remaining_games'], 18)

    def test_payment_and_owner_login_reject_cross_origin_or_missing_origin(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request('/api/auth/owner', {'email': 'owner@example.com', 'password': 'owner-secret'}, origin=False)
        self.assertEqual(error.exception.code, 403)

    def test_google_callback_requires_session_bound_single_use_state(self):
        self.request('/api/account')
        token = next(iter(self.jar)).value
        with accounts.database() as db:
            db.execute('INSERT INTO oauth VALUES (?,?,?,?)', (accounts.digest('fixture-state'), accounts.digest(token), 'verifier', time.time()+600))
        with patch('accounts.google_profile', return_value={'sub': 'google-id', 'email': 'verified@gmail.com', 'email_verified': True}) as profile:
            with self.assertRaises(urllib.error.HTTPError):
                self.request('/auth/google/callback?state=wrong&code=test')
            self.assertFalse(profile.called)
            self.request('/auth/google/callback?state=fixture-state&code=test')
            profile.assert_called_once_with('test', 'verifier')
            self.assertEqual(json.loads(self.request('/api/account'))['email'], 'verified@gmail.com')
            with self.assertRaises(urllib.error.HTTPError):
                self.request('/auth/google/callback?state=fixture-state&code=test')


if __name__ == '__main__':
    unittest.main()
