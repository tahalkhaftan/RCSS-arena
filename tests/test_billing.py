"""No real bank requests: verify stored prices, ownership and atomic activation."""
import json
import os
import time
import unittest
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import accounts
import billing
import test_accounts as fixture_tools

AUTHORITY = 'A'+'1'*35
MERCHANT = '00000000-0000-0000-0000-000000000000'

class Billing(unittest.TestCase):
    def setUp(self):
        fixture_tools.Accounts.setUp(self)
        self.gateway_env = patch.dict(os.environ, {'ARENA_PUBLIC_URL': 'https://arena.example', 'ZARINPAL_MERCHANT_ID': MERCHANT})
        self.gateway_env.start()
        self.account = fixture_tools.fixture().account
    def tearDown(self):
        self.gateway_env.stop()
        fixture_tools.Accounts.tearDown(self)
    def checkout(self, plan='plus'):
        with patch('billing.gateway', return_value={'code':100,'authority':AUTHORITY}) as gateway:
            result = billing.create_checkout(self.account, plan)
        return result, gateway.call_args.args[1]
    def person(self):
        with accounts.database() as db:
            return dict(db.execute('SELECT * FROM people WHERE id=?', (self.account['id'],)).fetchone())
    def test_stored_price_is_converted_to_rials_and_order_is_bound_to_authority(self):
        result, payload = self.checkout()
        self.assertEqual(payload['amount'], 300000)
        self.assertEqual(payload['currency'], 'IRR')
        self.assertIn(result['id'], payload['callback_url'])
        with patch('billing.gateway', return_value={'code':100,'ref_id':123}) as gateway:
            billing.verify_checkout(result['id'], AUTHORITY, 'OK')
        self.assertEqual(gateway.call_args.args[1], {'amount':300000,'authority':AUTHORITY})
        self.assertEqual(self.person()['plan'], 'plus')
        self.assertGreater(self.person()['expires'], time.time()+27*86400)
    def test_browser_success_parameter_and_fake_receipt_do_not_activate(self):
        result, _ = self.checkout()
        with patch('billing.gateway', return_value={'code':-21}) as gateway:
            with self.assertRaises(ValueError):
                billing.verify_checkout(result['id'], AUTHORITY, 'OK')
        self.assertEqual(self.person()['plan'], 'free')
        with patch('billing.gateway') as gateway:
            with self.assertRaises(ValueError):
                billing.verify_checkout(result['id'], 'B'+'2'*35, 'OK')
            gateway.assert_not_called()
    def test_cancelled_payment_never_verifies_or_activates(self):
        result, _ = self.checkout()
        with patch('billing.gateway') as gateway:
            billing.verify_checkout(result['id'], AUTHORITY, 'NOK')
            gateway.assert_not_called()
        self.assertEqual(self.person()['plan'], 'free')
    def test_concurrent_callbacks_and_replays_extend_only_once(self):
        result, _ = self.checkout()
        with patch('billing.gateway', return_value={'code':101,'ref_id':123}):
            with ThreadPoolExecutor(max_workers=6) as pool:
                list(pool.map(lambda _:billing.verify_checkout(result['id'], AUTHORITY, 'OK'), range(8)))
        expiry = self.person()['expires']
        self.assertLess(expiry, time.time()+32*86400)
        with patch('billing.gateway') as gateway:
            billing.verify_checkout(result['id'], AUTHORITY, 'OK')
            gateway.assert_not_called()
        self.assertEqual(self.person()['expires'], expiry)
    def test_gateway_verified_retry_recovers_after_persistence_failure(self):
        result, _ = self.checkout()
        with patch('billing.gateway', return_value={'code':100,'ref_id':123}), patch('account_store.save', side_effect=OSError('fixture outage')):
            with self.assertRaises(OSError):
                billing.verify_checkout(result['id'], AUTHORITY, 'OK')
        self.assertEqual(self.person()['plan'], 'free')
        with patch('billing.gateway', return_value={'code':101,'ref_id':123}):
            billing.verify_checkout(result['id'], AUTHORITY, 'OK')
        self.assertEqual(self.person()['plan'], 'plus')
    def test_upgrade_preserves_existing_days_and_active_pro_cannot_downgrade(self):
        expiry = time.time()+10*86400
        with accounts.database() as db:
            db.execute("UPDATE people SET plan='plus',expires=? WHERE id=?", (expiry,self.account['id']))
        result, _ = self.checkout('pro')
        with patch('billing.gateway', return_value={'code':100,'ref_id':123}):
            billing.verify_checkout(result['id'], AUTHORITY, 'OK')
        self.assertEqual(self.person()['plan'], 'pro')
        self.assertGreater(self.person()['expires'], expiry+27*86400)
        with self.assertRaises(ValueError):
            billing.create_checkout(self.account, 'plus')
    def test_repeated_checkout_reuses_pending_authority(self):
        result, _ = self.checkout()
        with patch('billing.gateway') as gateway:
            self.assertEqual(billing.create_checkout(self.account,'plus'), result)
            gateway.assert_not_called()
    def test_unconfigured_gateway_never_creates_or_activates_order(self):
        with patch.dict(os.environ, {'ZARINPAL_MERCHANT_ID':''}), patch('billing.gateway') as gateway:
            self.assertFalse(billing.configured())
            with self.assertRaises(ValueError):
                billing.create_checkout(self.account, 'plus')
            gateway.assert_not_called()
    def test_google_return_destination_has_no_open_redirect(self):
        for unsafe in ('https://evil.example/plans', '//evil.example/plans', '/plans/../outside', '/other'):
            self.assertEqual(accounts.auth_destination(unsafe), '/')
        self.assertEqual(accounts.auth_destination('/plans?plan=pro'), '/plans?plan=pro')
        self.assertEqual(accounts.auth_destination('/plans?plan=evil&next=https://evil.example'), '/plans')

class BillingHTTP(unittest.TestCase):
    request = fixture_tools.AccountHTTP.request
    login_user = fixture_tools.AccountHTTP.login_user
    def setUp(self):
        fixture_tools.AccountHTTP.setUp(self)
        self.gateway_env = patch.dict(os.environ, {'ZARINPAL_MERCHANT_ID':MERCHANT,'ARENA_PUBLIC_URL':'https://arena.example'})
        self.gateway_env.start()
    def tearDown(self):
        self.gateway_env.stop()
        fixture_tools.AccountHTTP.tearDown(self)
    def test_checkout_ignores_browser_price_and_plan_activates_without_owner(self):
        self.login_user()
        with patch('billing.gateway', return_value={'code':100,'authority':AUTHORITY}) as gateway:
            order = json.loads(self.request('/api/billing/checkout', {'plan':'plus','amount':1,'verified':True}))
        self.assertEqual(gateway.call_args.args[1]['amount'], 300000)
        self.assertEqual(json.loads(self.request('/api/account'))['tier'],'free')
        with patch('billing.gateway', return_value={'code':100,'ref_id':123}):
            self.request('/billing/callback?order='+order['id']+'&Authority='+AUTHORITY+'&Status=OK')
        self.assertEqual(json.loads(self.request('/api/account'))['tier'],'plus')
        self.assertEqual(json.loads(self.request('/api/billing/orders/'+order['id']))['status'],'paid')
        self.login_user('google:other')
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request('/api/billing/orders/'+order['id'])
        self.assertEqual(error.exception.code,404)
    def test_public_readiness_and_plans_do_not_expose_card_or_credentials(self):
        account=json.loads(self.request('/api/account'))
        self.assertNotIn('card',account)
        self.assertNotIn('merchant_id',account)
        self.assertNotIn('client_secret',account)
        self.assertIn('خرید'.encode(),self.request('/plans'))
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request('/api/setup')
        self.assertEqual(error.exception.code,403)
