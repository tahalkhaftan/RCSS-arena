"""Durable account snapshots in the existing private GitHub storage repository.

One web instance only. Upload a new snapshot before pruning old copies so a
failed upload never deletes the last durable account database. Read failures
fail closed, rather than creating fresh quotas or discarding subscriptions.
"""
import os
import re
import threading
import time
from pathlib import Path
from github_api import storage_client

LOCK = threading.RLock()
READY = {}
MARKER = 'arena-account-store-v1'
NAME = re.compile(r'accounts-[0-9]+\.sqlite3')


def initialize(path):
    if os.environ.get('ARENA_ACCOUNTS_STORE', 'sqlite') != 'github':
        return None
    key = (str(path.resolve()), os.environ.get('STORAGE_REPOSITORY'))
    if key in READY:
        return READY[key]
    gh = storage_client()
    gh.require_private()
    release = None
    page = 1
    while True:
        rows = gh.json(f'/releases?per_page=100&page={page}')
        release = next((r for r in rows if r.get('name') == MARKER), None)
        if release or len(rows) < 100:
            break
        page += 1
    if not release:
        # A pre-existing local database must be deliberately migrated by the
        # operator; never silently overwrite it with an empty remote store.
        release = gh.json('/releases', 'POST', {'name': MARKER, 'tag_name': MARKER, 'draft': True})
    assets = [a for a in gh.assets(release['id']).values() if NAME.fullmatch(a['name'])]
    if assets:
        latest = max(assets, key=lambda a: int(a['id']))
        if latest.get('size', 0) > 64*1024**2:
            raise ValueError('Account snapshot exceeds 64 MiB')
        data = gh.read_asset(latest)
        if not data.startswith(b'SQLite format 3\0'):
            raise ValueError('Invalid account database snapshot')
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix('.restoring')
        temp.write_bytes(data)
        temp.chmod(0o600)
        temp.replace(path)
        for suffix in ('-journal', '-wal', '-shm'):
            Path(str(path)+suffix).unlink(missing_ok=True)
    elif path.exists():
        # First opt-in migrates the existing local database, before serving it.
        save((gh, release['id']), path.read_bytes())
    READY[key] = (gh, release['id'])
    return READY[key]


def save(remote, content):
    if not remote:
        return
    gh, ident = remote
    if len(content) > 64*1024**2:
        raise ValueError('Account database exceeds 64 MiB')
    gh.put(ident, f'accounts-{time.time_ns()}.sqlite3', content, 'application/vnd.sqlite3')
    try:
        assets = sorted((a for a in gh.assets(ident).values() if NAME.fullmatch(a['name'])), key=lambda a: int(a['id']), reverse=True)
        for old in assets[2:]:
            gh.json('/releases/assets/'+str(old['id']), 'DELETE')
    except OSError:
        pass  # A retained older snapshot does not invalidate the new one.
