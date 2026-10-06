"""Bundled team archives; identifiers never become user-controlled paths."""
import hashlib
import json
from pathlib import Path
ROOT = Path(__file__).parent / 'preset_teams'

def catalog():
    return json.loads((ROOT / 'catalog.json').read_text())

def resolve_teams(config, fields):
    known = {team['id']: team for team in catalog()}
    blobs = {}
    for side in ('left', 'right'):
        ident = config.get(side, {}).get('preset_id')
        if ident:
            if ident not in known:
                raise ValueError('Unknown preset team')
            team = known[ident]
            blob = archive_bytes(team)
            if hashlib.sha256(blob).hexdigest() != team['sha256']:
                raise ValueError('Preset archive checksum mismatch')
            config[side] = {key: team[key] for key in ('name', 'directory', 'command')}
            config[side]['preset_id'] = ident
        else:
            blob = fields.get(side + '_file')
            if not blob:
                raise ValueError('Choose a preset or upload a ZIP for both teams')
        blobs[side] = blob
    if sum(map(len, blobs.values())) > 32 * 1024**2:
        raise ValueError('Maximum 32 MB for both teams combined')
    return blobs

def archive_bytes(team):
    return b''.join((ROOT / name).read_bytes() for name in team.get('parts', [team['archive']]))
