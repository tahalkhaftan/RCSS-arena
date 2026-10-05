"""Keep failure diagnostics in the existing private release, never public logs."""
import io
import json
import os
import zipfile
from github_api import storage_client

gh = storage_client()
gh.require_private()
ident = int(os.environ['RELEASE_ID'])
assets = gh.assets(ident)
report = {'results': json.loads(gh.read_asset(assets['results.json']))}
if 'logs.zip' in assets:
    with zipfile.ZipFile(io.BytesIO(gh.read_asset(assets['logs.zip']))) as archive:
        report['logs'] = {name: archive.read(name).decode('utf-8', errors='replace')[-11000:]
                          for name in archive.namelist() if name.endswith(('server.log', 'left.log', 'right.log'))}
gh.json('/releases/' + str(ident), 'PATCH', {'body': json.dumps(report, ensure_ascii=False)[:60000]})
print('Failure report retained in the private storage release.')
