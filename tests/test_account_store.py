import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import accounts
import account_store


class Storage:
    def __init__(self):
        self.items = {}
        self.data = {}
        self.fail = False
        self.sequence = 0
    def require_private(self):
        pass
    def json(self, path, method='GET', body=None):
        if method == 'GET':
            return [{'id': 1, 'name': account_store.MARKER}]
        if method == 'DELETE':
            ident = int(path.rsplit('/', 1)[1])
            self.items = {k: v for k, v in self.items.items() if v['id'] != ident}
    def assets(self, ident):
        return dict(self.items)
    def read_asset(self, asset):
        return self.data[asset['id']]
    def put(self, ident, name, data, ctype):
        if self.fail:
            raise OSError('Fixture upload failed')
        self.sequence += 1
        self.items[name] = {'name': name, 'id': self.sequence, 'size': len(data)}
        self.data[self.sequence] = data


class AccountStore(unittest.TestCase):
    def test_restart_restores_paid_accounts_and_failed_upload_does_not_acknowledge_changes(self):
        gh = Storage()
        with tempfile.TemporaryDirectory() as folder, patch('account_store.storage_client', return_value=gh), patch.dict(os.environ, {'ARENA_ACCOUNTS_STORE': 'github', 'STORAGE_REPOSITORY': 'fixture/private', 'ARENA_ACCOUNT_DB': str(Path(folder)/'accounts.sqlite3')}):
            path = Path(os.environ['ARENA_ACCOUNT_DB'])
            try:
                with accounts.database() as db:
                    db.execute("INSERT INTO people(id,plan,expires,games) VALUES ('paid','pro',9999999999,5)")
                    db.execute("INSERT INTO people(id) VALUES ('google:free')")
                    db.execute("INSERT INTO quota_events VALUES ('daily','google:free',7,?)", (time.time(),))
                self.assertTrue(gh.items)
                gh.fail = True
                with self.assertRaises(OSError):
                    with accounts.database() as db:
                        db.execute("UPDATE people SET plan='free' WHERE id='paid'")
                gh.fail = False
                with sqlite3.connect(path) as db:
                    self.assertEqual(db.execute("SELECT plan FROM people WHERE id='paid'").fetchone()[0], 'pro')
                path.unlink()
                account_store.READY.clear()
                with accounts.database() as db:
                    row = db.execute("SELECT plan,games FROM people WHERE id='paid'").fetchone()
                    self.assertEqual(tuple(row), ('pro', 5))
                self.assertEqual(accounts.quota_status({'id': 'google:free', 'tier': 'free', 'guest': False})['remaining_games'], 23)
            finally:
                account_store.READY.clear()

    def test_keep_previous_snapshot_until_new_upload_succeeds(self):
        gh = Storage()
        for _ in range(4):
            account_store.save((gh, 1), b'SQLite fixture')
        self.assertEqual(len(gh.items), 2)
        before = dict(gh.items)
        gh.fail = True
        with self.assertRaises(OSError):
            account_store.save((gh, 1), b'next snapshot')
        self.assertEqual(gh.items, before)


if __name__ == '__main__':
    unittest.main()
