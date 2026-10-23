"""Zarinpal checkout: activate only after server-to-server verification.

Prices are stored in tomans; gateway request and verify both use stored IRR.
Callbacks may be replayed, arrive without a browser session, or be retried after
an interrupted snapshot upload. The paid transition and entitlement are atomic.
"""
import json
import os
import re
import secrets
import sqlite3
import time
import urllib.parse
import urllib.request
import accounts

API = 'https://payment.zarinpal.com/pg/v4/payment/'
START = 'https://payment.zarinpal.com/pg/StartPay/'


def public_url():
    value = (os.environ.get('ARENA_PUBLIC_URL') or os.environ.get('RENDER_EXTERNAL_URL', '')).strip().rstrip('/')
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme != 'https' or not parsed.netloc or parsed.path or parsed.query or parsed.fragment or parsed.username:
        raise ValueError('Configure the HTTPS ARENA_PUBLIC_URL origin')
    return value


def configured():
    try:
        public_url()
        return bool(re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', os.environ.get('ZARINPAL_MERCHANT_ID', '').strip()))
    except ValueError:
        return False


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def gateway(method, payload):
    if not configured():
        raise ValueError('درگاه پرداخت هنوز فعال نشده است.')
    payload = dict(payload, merchant_id=os.environ['ZARINPAL_MERCHANT_ID'].strip())
    request = urllib.request.Request(API+method+'.json', data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json', 'Accept': 'application/json'}, method='POST')
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=20) as response:
        result = json.loads(response.read(65536))
    data = result.get('data')
    if not isinstance(data, dict):
        raise ValueError('درگاه پاسخ معتبر نداد؛ دوباره امتحان کن.')
    return data


def create_checkout(account, plan):
    if account['guest']:
        raise PermissionError('برای خرید، با گوگل وارد شو.')
    if account['owner']:
        raise ValueError('حساب مالک دسترسی کامل دارد و به خرید نیاز ندارد.')
    if plan not in accounts.PLANS:
        raise ValueError('پلن معتبر انتخاب کن.')
    if not configured():
        raise ValueError('خرید آنلاین به‌زودی فعال می‌شود.')
    ident = secrets.token_hex(16)
    now = time.time()
    with accounts.database() as db:
        db.execute('BEGIN IMMEDIATE')
        current = db.execute('SELECT plan,expires FROM people WHERE id=?', (account['id'],)).fetchone()
        if current['plan'] == 'pro' and current['expires'] > now and plan == 'plus':
            raise ValueError('اشتراک پرو فعال داری؛ می‌توانی پرو را تمدید کنی.')
        pending = db.execute("SELECT * FROM checkouts WHERE person=? AND status IN ('creating','pending') AND created>? ORDER BY created DESC LIMIT 1", (account['id'], now-1800)).fetchone()
        if pending:
            if pending['plan'] == plan and pending['authority']:
                return {'id': pending['id'], 'url': START+pending['authority']}
            raise ValueError('یک پرداخت باز داری؛ آن را کامل کن یا ۳۰ دقیقه بعد دوباره تلاش کن.')
        db.execute('INSERT INTO checkouts(id,person,plan,amount,created) VALUES (?,?,?,?,?)',
            (ident, account['id'], plan, accounts.PLANS[plan]['price'], now))
    try:
        data = gateway('request', {'amount': accounts.PLANS[plan]['price']*10, 'currency': 'IRR',
            'description': 'RCSS Arena '+plan+' monthly',
            'callback_url': public_url()+'/billing/callback?order='+ident,
            'metadata': {'order_id': ident}})
        authority = data.get('authority', '')
        if data.get('code') != 100 or not re.fullmatch(r'[A-Za-z0-9]{16,128}', str(authority)):
            raise ValueError('ساخت پرداخت انجام نشد؛ دوباره امتحان کن.')
        with accounts.database() as db:
            db.execute("UPDATE checkouts SET authority=?,status='pending' WHERE id=?", (authority, ident))
    except Exception:
        with accounts.database() as db:
            db.execute("UPDATE checkouts SET status='failed' WHERE id=? AND status='creating'", (ident,))
        raise
    return {'id': ident, 'url': START+authority}


def verify_checkout(ident, authority, status):
    if not re.fullmatch(r'[0-9a-f]{32}', ident) or not re.fullmatch(r'[A-Za-z0-9]{16,128}', authority):
        raise ValueError('بازگشت پرداخت نامعتبر است.')
    with accounts.database() as db:
        row = db.execute('SELECT * FROM checkouts WHERE id=? AND authority=?', (ident, authority)).fetchone()
    if not row:
        raise ValueError('پرداخت پیدا نشد.')
    if row['status'] == 'paid':
        return
    if status != 'OK':
        with accounts.database() as db:
            db.execute("UPDATE checkouts SET status='cancelled' WHERE id=? AND status!='paid'", (ident,))
        return
    # Never trust Status=OK, browser amount, plan, ref_id or a submitted receipt.
    result = gateway('verify', {'amount': row['amount']*10, 'authority': row['authority']})
    ref = str(result.get('ref_id', ''))
    if result.get('code') not in (100, 101) or not ref.isdigit() or int(ref) <= 0:
        with accounts.database() as db:
            db.execute("UPDATE checkouts SET status='failed' WHERE id=? AND status!='paid'", (ident,))
        raise ValueError('پرداخت تأیید نشد؛ در صورت کسر وجه، وضعیت را دوباره بررسی کن.')
    with accounts.database() as db:
        db.execute('BEGIN IMMEDIATE')
        latest = db.execute('SELECT status FROM checkouts WHERE id=?', (ident,)).fetchone()
        if latest['status'] == 'paid':
            return
        person = db.execute('SELECT plan,expires FROM people WHERE id=?', (row['person'],)).fetchone()
        # Preserve existing days when renewing/upgrading. A late older Plus
        # callback never downgrades an already active Pro subscription.
        plan = 'pro' if person['plan'] == 'pro' and person['expires'] > time.time() else row['plan']
        expires = accounts.month_after(max(time.time(), person['expires']))
        db.execute('UPDATE people SET plan=?,expires=? WHERE id=?', (plan, expires, row['person']))
        db.execute("UPDATE checkouts SET status='paid',ref_id=?,paid=? WHERE id=?", (ref, time.time(), ident))


def handle(h):
    path = urllib.parse.urlparse(h.path).path
    order_route = re.fullmatch(r'/api/billing/orders/([0-9a-f]{32})', path)
    if path not in ('/api/billing/checkout', '/billing/callback', '/api/setup') and not order_route:
        return False
    try:
        if path == '/billing/callback' and h.command == 'GET':
            args = urllib.parse.parse_qs(urllib.parse.urlparse(h.path).query)
            ident = args.get('order', [''])[0]
            verify_checkout(ident, args.get('Authority', [''])[0], args.get('Status', [''])[0])
            accounts.redirect(h, '/plans?order='+ident)
            return True
        account = accounts.identity(h)
        if path == '/api/setup' and h.command == 'GET':
            if not account['owner']:
                h.send(403, {'error': 'Owner access required'})
            else:
                try:
                    base = public_url()
                except ValueError:
                    base = ''
                h.send(200, {'google_ready': accounts.google_ready(), 'billing_ready': configured(),
                    'google_callback': base+'/auth/google/callback' if base else '',
                    'missing': [name for name in ('GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET', 'ZARINPAL_MERCHANT_ID') if not os.environ.get(name, '').strip()]})
        elif order_route and h.command == 'GET':
            with accounts.database() as db:
                row = db.execute('SELECT id,person,plan,amount,status,ref_id FROM checkouts WHERE id=?', (order_route[1],)).fetchone()
            if not row or row['person'] != account['id']:
                h.send(404, {'error': 'Not found'})
            else:
                h.send(200, {k: row[k] for k in ('id', 'plan', 'amount', 'status', 'ref_id')})
        elif path == '/api/billing/checkout' and h.command == 'POST':
            origin = h.headers.get('Origin')
            if not origin or urllib.parse.urlparse(origin).netloc != h.headers.get('Host'):
                h.send(403, {'error': 'Cross-origin request rejected'})
                return True
            if account['guest']:
                h.send(401, {'error': 'برای خرید، با گوگل وارد شو.'})
                return True
            if not configured():
                h.send(503, {'error': 'خرید آنلاین به‌زودی فعال می‌شود.'})
                return True
            data = accounts.json_body(h)
            h.send(201, create_checkout(account, data.get('plan')))
        else:
            h.send(405, {'error': 'Method not allowed'})
    except (ValueError, PermissionError, sqlite3.IntegrityError):
        if path == '/billing/callback':
            accounts.redirect(h, '/plans?payment=unverified')
        else:
            h.send(400, {'error': 'خرید انجام نشد؛ وضعیت پلن یا پرداخت قبلی را بررسی کن.'})
    except (OSError, KeyError):
        if path == '/billing/callback':
            accounts.redirect(h, '/plans?payment=retry')
        else:
            h.send(502, {'error': 'ارتباط با درگاه برقرار نشد؛ دوباره امتحان کن.'})
    return True
