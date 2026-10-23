"""Server-side identities, quotas and gateway-verified monthly subscriptions.

Deploy ARENA_ACCOUNT_DB on persistent storage. No Google passwords or payment
card credentials are collected. Google authorization codes are exchanged only
with Google's HTTPS endpoints; browser-supplied identity claims are not trusted.
"""
import base64
import calendar
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile
import account_store
from contextlib import contextmanager
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from pathlib import Path

PLANS = {'plus': {'name': 'پلاس', 'price': 30000, 'original_price': 50000, 'max_games': 100},
         'pro': {'name': 'پرو', 'price': 50000, 'original_price': 70000, 'max_games': 500}}
COOKIE = 'arena_session'
DAILY_GAMES = 30
QUOTA_WINDOW = 24 * 60 * 60


@contextmanager
def database():
    with account_store.LOCK:
        path = Path(os.environ.get('ARENA_ACCOUNT_DB', os.environ.get('DATA_DIR', './data') + '/accounts.sqlite3'))
        remote = account_store.initialize(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(path, timeout=30)
        db.row_factory = sqlite3.Row
        db.executescript('''
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS people (id TEXT PRIMARY KEY, email TEXT NOT NULL DEFAULT '',
                plan TEXT NOT NULL DEFAULT 'free', expires REAL NOT NULL DEFAULT 0,
                runs INTEGER NOT NULL DEFAULT 0, games INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, person TEXT NOT NULL, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS auth_destinations (state TEXT PRIMARY KEY, path TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS oauth (state TEXT PRIMARY KEY, session TEXT NOT NULL, verifier TEXT NOT NULL, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs (kind TEXT NOT NULL, id TEXT NOT NULL, person TEXT NOT NULL, PRIMARY KEY(kind,id));
            CREATE TABLE IF NOT EXISTS guest_usage (key TEXT PRIMARY KEY, runs INTEGER NOT NULL DEFAULT 0, games INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS reservation_buckets (id TEXT PRIMARY KEY, key TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS quota_events (id TEXT PRIMARY KEY, person TEXT NOT NULL,
                games INTEGER NOT NULL, created REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS quota_events_person_time ON quota_events(person,created);
            CREATE TABLE IF NOT EXISTS reservations (id TEXT PRIMARY KEY, person TEXT NOT NULL, games INTEGER NOT NULL, free INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS payments (id TEXT PRIMARY KEY, person TEXT NOT NULL, plan TEXT NOT NULL,
                amount INTEGER NOT NULL, reference TEXT NOT NULL UNIQUE, status TEXT NOT NULL DEFAULT 'pending',
                created REAL NOT NULL, approved REAL, approved_by TEXT);
            CREATE TABLE IF NOT EXISTS checkouts (id TEXT PRIMARY KEY, person TEXT NOT NULL,
                plan TEXT NOT NULL, amount INTEGER NOT NULL, authority TEXT UNIQUE, ref_id TEXT UNIQUE,
                status TEXT NOT NULL DEFAULT 'creating', created REAL NOT NULL, paid REAL);
            CREATE INDEX IF NOT EXISTS checkouts_person_time ON checkouts(person,created);
            CREATE TABLE IF NOT EXISTS attempts (key TEXT PRIMARY KEY, count INTEGER NOT NULL, until REAL NOT NULL);
        ''')
        db.execute('INSERT OR IGNORE INTO settings VALUES (?,?)', ('session_secret', secrets.token_hex(32)))
        db.commit()
        try:
            yield db
            if db.total_changes:
                account_store.save(remote, db.serialize())
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def cookie_value(h):
    try:
        jar = SimpleCookie(h.headers.get('Cookie', ''))
        return jar[COOKIE].value if COOKIE in jar else ''
    except Exception:
        return ''


def set_cookie(h, value, age=2592000):
    secure = '; Secure' if (os.environ.get('ARENA_PUBLIC_URL') or os.environ.get('RENDER_EXTERNAL_URL', '')).startswith('https://') else ''
    h.account_cookie = f'{COOKIE}={value}; Path=/; HttpOnly; SameSite=Lax; Max-Age={age}{secure}'


def new_session(h, db, person):
    token = secrets.token_urlsafe(32)
    db.execute('INSERT INTO sessions VALUES (?,?,?)', (digest(token), person, time.time() + 2592000))
    set_cookie(h, token)
    h.session_token = token
    return token


def peer_key(h, db):
    ip = h.client_address[0]
    if os.environ.get('ARENA_TRUST_PROXY') == '1':
        # Enable only behind a proxy that overwrites this header.
        ip = h.headers.get('X-Forwarded-For', ip).split(',')[0].strip()
    secret = os.environ.get('ARENA_SESSION_SECRET') or db.execute('SELECT value FROM settings WHERE key=?', ('session_secret',)).fetchone()[0]
    return hmac.new(secret.encode(), ip.encode(), hashlib.sha256).hexdigest()


def owner_credentials(h):
    user, password = os.environ.get('ARENA_USER'), os.environ.get('ARENA_PASSWORD')
    expected = 'Basic ' + base64.b64encode((str(user) + ':' + str(password)).encode()).decode()
    return bool(user and password and hmac.compare_digest(h.headers.get('Authorization', '').encode(), expected.encode()))


def identity(h):
    if hasattr(h, 'account'):
        return h.account
    with database() as db:
        if owner_credentials(h):
            person = 'owner'
            db.execute('INSERT OR IGNORE INTO people(id,email) VALUES (?,?)', (person, os.environ['ARENA_USER']))
        else:
            token = cookie_value(h)
            session = db.execute('SELECT person FROM sessions WHERE token=? AND expires>?', (digest(token), time.time())).fetchone() if token else None
            if session:
                person = session[0]
            else:
                # Each browser gets a distinct identity; address buckets limit quota only.
                person = 'guest:' + secrets.token_hex(24)
                db.execute('INSERT OR IGNORE INTO people(id) VALUES (?)', (person,))
                new_session(h, db, person)
        row = dict(db.execute('SELECT * FROM people WHERE id=?', (person,)).fetchone())
        if person.startswith('guest:'):
            row['bucket'] = peer_key(h, db)
            usage = db.execute('SELECT runs,games FROM guest_usage WHERE key=?', (row['bucket'],)).fetchone()
            if usage:
                row['runs'] = max(row['runs'], usage['runs'])
                row['games'] = max(row['games'], usage['games'])
    owner_sub = os.environ.get('ARENA_OWNER_GOOGLE_SUB', '')
    # Pin to Google's immutable sub where available; email fallback is Gmail only.
    email_owner = os.environ.get('ARENA_OWNER_EMAIL', '').strip().lower()
    row['owner'] = person == 'owner' or bool(owner_sub and person == 'google:' + owner_sub) or bool(
        not owner_sub and email_owner.endswith('@gmail.com') and row['email'].lower() == email_owner)
    row['tier'] = 'owner' if row['owner'] else row['plan'] if row['expires'] > time.time() else 'free'
    row['guest'] = person.startswith('guest:')
    h.account = row
    return row


def owns(account, kind, ident):
    if account['owner']:
        return True
    with database() as db:
        row = db.execute('SELECT person FROM jobs WHERE kind=? AND id=?', (kind, str(ident))).fetchone()
    return bool(row and row[0] == account['id'])


def bind(account, kind, ident):
    with database() as db:
        db.execute('INSERT OR IGNORE INTO jobs VALUES (?,?,?)', (kind, str(ident), account['id']))
        row = db.execute('SELECT person FROM jobs WHERE kind=? AND id=?', (kind, str(ident))).fetchone()
        if row[0] != account['id']:
            raise ValueError('This job already belongs to another account')


def authorize(h):
    account = identity(h)
    path = urllib.parse.urlparse(h.path).path
    if path.startswith(('/personal/', '/api/personal/', '/native/')) and not account['owner']:
        h.send(401 if account['guest'] else 403, {'error': 'اتصال Ubuntu شخصی و دسکتاپ مشترک فقط برای مالک سایت است.'})
        return False
    match = re.match(r'/api/(tests|builds)/([^/]+)', path)
    if match and not owns(account, match[1], match[2]):
        h.send(401 if account['guest'] else 404, {'error': 'Not found'})
        return False
    if account['tier'] not in ('pro', 'owner') and re.search(r'/(?:build-log/(?:left|right)|log)$', path):
        h.send(403, {'error': 'دانلود این فایل به اشتراک پرو نیاز دارد.'})
        return False
    return True


def reserve(h, config):
    account = identity(h)
    tier = account['tier']
    count = config['rounds'] * config['games_per_round']
    limit = PLANS.get(tier, {}).get('max_games', 500 if tier == 'owner' else 5 if account['guest'] else DAILY_GAMES)
    if count > limit:
        raise ValueError(f'سقف هر درخواست برای حساب شما {limit} بازی است.')
    if tier not in ('pro', 'owner') and (config.get('offline_logging') or config.get('debug_logging')):
        raise ValueError('خروجی آفلاین، CSV و دیباگ به اشتراک پرو نیاز دارد.')
    config['export_tier'] = tier  # Never trust the browser's requested tier.
    ticket = secrets.token_hex(16)
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        if tier == 'free' and not account['guest']:
            used = db.execute('SELECT COALESCE(SUM(games),0) FROM quota_events WHERE person=? AND created>?',
                              (account['id'], time.time()-QUOTA_WINDOW)).fetchone()[0]
            if used + count > DAILY_GAMES:
                raise ValueError('سهمیهٔ ۳۰ بازی در ۲۴ ساعت تکمیل شده است. کمی بعد دوباره امتحان کن.')
            db.execute('INSERT INTO quota_events VALUES (?,?,?,?)', (ticket, account['id'], count, time.time()))
        elif tier == 'free':
            updated = db.execute('UPDATE people SET runs=runs+1,games=games+? WHERE id=? AND runs<5 AND games+?<=5', (count, account['id'], count))
            db.execute('INSERT OR IGNORE INTO guest_usage(key) VALUES (?)', (account['bucket'],))
            bucket = db.execute('UPDATE guest_usage SET runs=runs+1,games=games+? WHERE key=? AND runs<5 AND games+?<=5', (count, account['bucket'], count))
            if bucket.rowcount != 1:
                raise ValueError('سهمیهٔ مهمان تمام شده؛ با گوگل وارد شو و روزانه ۳۰ بازی اجرا کن.')
            db.execute('INSERT INTO reservation_buckets VALUES (?,?)', (ticket, account['bucket']))
            if updated.rowcount != 1:
                raise ValueError('سهمیهٔ مهمان تمام شده؛ با گوگل وارد شو و روزانه ۳۰ بازی اجرا کن.')
        db.execute('INSERT INTO reservations VALUES (?,?,?,?)', (ticket, account['id'], count, int(tier == 'free')))
    return ticket


def quota_status(account):
    if account['tier'] != 'free':
        return {'remaining_games': None, 'remaining_runs': None, 'quota_limit': None, 'quota_reset_at': None, 'quota_window_seconds': None}
    if account['guest']:
        return {'remaining_games': max(0, 5-account['games']), 'remaining_runs': max(0, 5-account['runs']),
                'quota_limit': 5, 'quota_reset_at': None, 'quota_window_seconds': None}
    with database() as db:
        used = db.execute('SELECT COALESCE(SUM(games),0),MIN(created) FROM quota_events WHERE person=? AND created>?',
                          (account['id'], time.time()-QUOTA_WINDOW)).fetchone()
    return {'remaining_games': max(0, DAILY_GAMES-used[0]), 'remaining_runs': None,
            'quota_limit': DAILY_GAMES, 'quota_reset_at': used[1]+QUOTA_WINDOW if used[1] is not None else None,
            'quota_window_seconds': QUOTA_WINDOW}


def finish(ticket, success):
    if not ticket:
        return
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM reservations WHERE id=?', (ticket,)).fetchone()
        if row and not success and row['free']:
            db.execute('DELETE FROM quota_events WHERE id=?', (ticket,))
            db.execute('UPDATE people SET runs=MAX(0,runs-1),games=MAX(0,games-?) WHERE id=?', (row['games'], row['person']))
        bucket = db.execute('SELECT key FROM reservation_buckets WHERE id=?', (ticket,)).fetchone()
        if row and bucket and not success:
            db.execute('UPDATE guest_usage SET runs=MAX(0,runs-1),games=MAX(0,games-?) WHERE key=?', (row['games'], bucket[0]))
        db.execute('DELETE FROM reservation_buckets WHERE id=?', (ticket,))
        db.execute('DELETE FROM reservations WHERE id=?', (ticket,))


def accepted(ticket):
    # Quota was durably reserved before dispatch. Failure to prune this receipt
    # must not refund an already running job or prompt the client to submit twice.
    try:
        finish(ticket, True)
    except OSError:
        pass


def allowed_export(name, tier):
    return tier in ('pro', 'owner') or name.lower().endswith(('.rcg', '.rcl', '.json', '.json.gz'))


def send_archive(h, source, size):
    """Filter downloads again, including old jobs and expired subscriptions."""
    tier = identity(h)['tier']
    if tier in ('pro', 'owner'):
        h.send_response(200)
        h.send_header('Content-Type', 'application/zip')
        h.send_header('Content-Length', str(size))
        h.send_header('Content-Disposition', 'attachment; filename="rcss-logs.zip"')
        h.end_headers()
        import shutil
        shutil.copyfileobj(source, h.wfile)
        return
    import shutil
    with tempfile.TemporaryFile() as original, tempfile.TemporaryFile() as filtered:
        shutil.copyfileobj(source, original)
        original.seek(0)
        with zipfile.ZipFile(original) as incoming, zipfile.ZipFile(filtered, 'w', zipfile.ZIP_DEFLATED) as outgoing:
            for info in incoming.infolist():
                if not info.is_dir() and allowed_export(info.filename, tier):
                    with incoming.open(info) as src, outgoing.open(info.filename, 'w', force_zip64=True) as dst:
                        shutil.copyfileobj(src, dst)
        length = filtered.tell()
        filtered.seek(0)
        h.send_response(200)
        h.send_header('Content-Type', 'application/zip')
        h.send_header('Content-Length', str(length))
        h.send_header('Content-Disposition', 'attachment; filename="rcss-logs.zip"')
        h.end_headers()
        shutil.copyfileobj(filtered, h.wfile)


def json_body(h):
    length = int(h.headers.get('Content-Length', 0))
    if not 0 < length <= 8192:
        raise ValueError('Invalid request size')
    body = json.loads(h.rfile.read(length))
    if not isinstance(body, dict):
        raise ValueError('Expected JSON object')
    return body


def redirect(h, url):
    h.send_response(303)
    h.send_header('Location', url)
    h.send_header('Cache-Control', 'no-store')
    h.send_header('Referrer-Policy', 'no-referrer')
    h.send_header('Content-Length', '0')
    h.end_headers()


def google_settings():
    client = os.environ.get('GOOGLE_CLIENT_ID', '').strip()
    secret = os.environ.get('GOOGLE_CLIENT_SECRET', '').strip()
    public = (os.environ.get('ARENA_PUBLIC_URL') or os.environ.get('RENDER_EXTERNAL_URL', '')).strip().rstrip('/')
    parsed = urllib.parse.urlparse(public)
    if not client or not secret or not parsed.netloc or (parsed.scheme != 'https' and parsed.hostname not in ('localhost', '127.0.0.1')):
        raise ValueError('ورود گوگل هنوز تنظیم نشده؛ مدیر باید GOOGLE_CLIENT_ID، GOOGLE_CLIENT_SECRET و ARENA_PUBLIC_URL را تنظیم کند.')
    return client, secret, public + '/auth/google/callback'


def google_profile(code, verifier):
    client, secret, callback = google_settings()
    body = urllib.parse.urlencode({'code': code, 'client_id': client, 'client_secret': secret,
        'redirect_uri': callback, 'grant_type': 'authorization_code', 'code_verifier': verifier}).encode()
    with urllib.request.urlopen(urllib.request.Request('https://oauth2.googleapis.com/token', data=body), timeout=15) as response:
        tokens = json.load(response)
    request = urllib.request.Request('https://openidconnect.googleapis.com/v1/userinfo', headers={'Authorization': 'Bearer ' + tokens['access_token']})
    with urllib.request.urlopen(request, timeout=15) as response:
        profile = json.load(response)
    if not profile.get('sub') or profile.get('email_verified') is not True or not profile.get('email'):
        raise ValueError('Google email is not verified')
    return profile


def month_after(timestamp):
    value = datetime.fromtimestamp(timestamp, timezone.utc)
    month = value.month % 12 + 1
    year = value.year + int(value.month == 12)
    return value.replace(year=year, month=month, day=min(value.day, calendar.monthrange(year, month)[1])).timestamp()


def google_ready():
    try:
        google_settings()
        return True
    except ValueError:
        return False


def auth_destination(value):
    # Only app-owned purchase routes may survive OAuth; never an external URL.
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme or parsed.netloc or parsed.path != '/plans':
        return '/'
    plan = urllib.parse.parse_qs(parsed.query).get('plan', [''])[0]
    return '/plans' + ('?plan=' + plan if plan in PLANS else '')


def routes(h):
    path = urllib.parse.urlparse(h.path).path
    if path in ('/account-ui.js', '/auth-ui.js', '/plans-ui.js', '/theme.js', '/account-theme.css') and h.command == 'GET':
        h.send(200, (Path(__file__).parent / 'static' / path.lstrip('/')).read_bytes(), ('text/css' if path.endswith('.css') else 'application/javascript')+'; charset=utf-8')
        return True
    if path in ('/login', '/signin', '/signup') and h.command == 'GET':
        h.send(200, (Path(__file__).parent / 'static/login.html').read_bytes(), 'text/html; charset=utf-8')
        return True
    if path == '/plans' and h.command == 'GET':
        h.send(200, (Path(__file__).parent / 'static/plans.html').read_bytes(), 'text/html; charset=utf-8')
        return True
    import billing
    if billing.handle(h):
        return True
    if path not in ('/api/account', '/auth/google', '/auth/google/callback', '/api/auth/owner', '/api/auth/logout', '/api/payments', '/api/admin/payments') and not path.startswith('/api/admin/payments/'):
        return False
    try:
        account = identity(h)
        if h.command == 'POST':
            origin = h.headers.get('Origin')
            if not origin or urllib.parse.urlparse(origin).netloc != h.headers.get('Host'):
                h.send(403, {'error': 'Cross-origin request rejected'})
                return True
        if path == '/api/account' and h.command == 'GET':
            ready = google_ready()
            h.send(200, {'email': account['email'], 'guest': account['guest'], 'owner': account['owner'],
                'tier': account['tier'], 'expires': account['expires'], **quota_status(account), 'plans': PLANS, 'google_ready': ready, 'billing_ready': billing.configured()})
        elif path == '/auth/google' and h.command == 'GET':
            client, _, callback = google_settings()
            state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
            session = getattr(h, 'session_token', None) or cookie_value(h)
            if not session:
                with database() as db:
                    session = new_session(h, db, account['id'])
            with database() as db:
                db.execute('DELETE FROM oauth WHERE expires<?', (time.time(),))
                db.execute('INSERT INTO oauth VALUES (?,?,?,?)', (digest(state), digest(session), verifier, time.time()+600))
                destination = auth_destination(urllib.parse.parse_qs(urllib.parse.urlparse(h.path).query).get('next', ['/'])[0])
                db.execute('INSERT INTO auth_destinations VALUES (?,?)', (digest(state), destination))
            challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
            redirect(h, 'https://accounts.google.com/o/oauth2/v2/auth?' + urllib.parse.urlencode({
                'client_id': client, 'redirect_uri': callback, 'response_type': 'code', 'scope': 'openid email profile',
                'state': state, 'prompt': 'select_account', 'code_challenge': challenge, 'code_challenge_method': 'S256'}))
        elif path == '/auth/google/callback' and h.command == 'GET':
            query = urllib.parse.parse_qs(urllib.parse.urlparse(h.path).query)
            state = query.get('state', [''])[0]
            with database() as db:
                db.execute('BEGIN IMMEDIATE')
                saved = db.execute('SELECT * FROM oauth WHERE state=? AND session=? AND expires>?', (digest(state), digest(cookie_value(h)), time.time())).fetchone()
                if not saved:
                    raise ValueError('درخواست ورود منقضی یا نامعتبر است؛ دوباره وارد شو.')
                destination = db.execute('SELECT path FROM auth_destinations WHERE state=?', (digest(state),)).fetchone()
                destination = auth_destination(destination[0]) if destination else '/'
                db.execute('DELETE FROM auth_destinations WHERE state=?', (digest(state),))
                db.execute('DELETE FROM oauth WHERE state=?', (digest(state),))
            if 'error' in query:
                redirect(h, '/login?cancelled=1')
                return True
            profile = google_profile(query.get('code', [''])[0], saved['verifier'])
            person = 'google:' + profile['sub']
            with database() as db:
                db.execute('BEGIN IMMEDIATE')
                db.execute('INSERT INTO people(id,email) VALUES (?,?) ON CONFLICT(id) DO UPDATE SET email=excluded.email', (person, profile['email']))
                if account['guest']:
                    db.execute('UPDATE jobs SET person=? WHERE person=?', (person, account['id']))
                db.execute('DELETE FROM sessions WHERE token=?', (digest(cookie_value(h)),))
                new_session(h, db, person)
            redirect(h, destination if destination != '/' else '/?signed_in=1')
        elif path == '/api/auth/owner' and h.command == 'POST':
            data = json_body(h)
            with database() as db:
                db.execute('BEGIN IMMEDIATE')
                key = 'owner:' + peer_key(h, db)
                row = db.execute('SELECT * FROM attempts WHERE key=?', (key,)).fetchone()
                if row and row['until'] > time.time() and row['count'] >= 10:
                    h.send(429, {'error': 'تلاش‌های ورود زیاد است؛ ۱۵ دقیقه بعد دوباره امتحان کن.'})
                    return True
                count = row['count'] if row and row['until'] > time.time() else 0
                db.execute('INSERT OR REPLACE INTO attempts VALUES (?,?,?)', (key, count+1, time.time()+900))
            valid = bool(os.environ.get('ARENA_USER') and os.environ.get('ARENA_PASSWORD'))
            valid &= hmac.compare_digest(str(data.get('email', '')).encode(), os.environ.get('ARENA_USER', '').encode())
            valid &= hmac.compare_digest(str(data.get('password', '')).encode(), os.environ.get('ARENA_PASSWORD', '').encode())
            if not valid:
                h.send(401, {'error': 'ایمیل یا رمز مالک درست نیست.'})
                return True
            with database() as db:
                db.execute('DELETE FROM attempts WHERE key=?', (key,))
                db.execute('INSERT OR IGNORE INTO people(id,email) VALUES (?,?)', ('owner', os.environ['ARENA_USER']))
                db.execute('DELETE FROM sessions WHERE token=?', (digest(cookie_value(h)),))
                new_session(h, db, 'owner')
            h.send(200, {'ok': True})
        elif path == '/api/auth/logout' and h.command == 'POST':
            with database() as db:
                db.execute('DELETE FROM sessions WHERE token=?', (digest(cookie_value(h)),))
            set_cookie(h, '', 0)
            h.send(200, {'ok': True})
        elif path == '/api/payments' and h.command == 'GET':
            with database() as db:
                rows = db.execute('SELECT id,plan,amount,reference,status,created FROM payments WHERE person=? ORDER BY created DESC LIMIT 50', (account['id'],)).fetchall()
            h.send(200, [dict(r) for r in rows])
        elif path == '/api/payments' and h.command == 'POST' or path.startswith('/api/admin/payments'):
            h.send(410, {'error': 'پرداخت دستی حذف شده است؛ از صفحهٔ خرید پلن استفاده کن.'})
        else:
            h.send(405, {'error': 'Method not allowed'})
    except sqlite3.IntegrityError:
        h.send(409, {'error': 'این شمارهٔ پیگیری قبلاً ثبت شده است.'})
    except ValueError as exc:
        if path.startswith('/auth/google'):
            redirect(h, '/login?error=google_unavailable')
        else:
            h.send(400, {'error': str(exc)})
    except (OSError, KeyError):
        if path.startswith('/auth/google'):
            redirect(h, '/login?error=google_failed')
        else:
            h.send(502, {'error': 'ارتباط برقرار نشد؛ دوباره امتحان کن.'})
    return True
