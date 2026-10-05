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
        from analysis import sexpr
        report['rcg'] = {}
        for name in archive.namelist():
            if not name.endswith('.rcg'): continue
            lines = archive.read(name).decode('utf-8', errors='replace').splitlines()
            bad = []
            for number, line in enumerate(lines[1:], 2):
                if not line.strip(): continue
                try: sexpr(line)
                except Exception as exc:
                    bad.append({'line':number,'text':line[:2000],'error':str(exc)})
                    if len(bad)==5: break
            report['rcg'][name] = {'bad':bad,'tail':lines[-8:]}
gh.json('/releases/' + str(ident), 'PATCH', {'body': json.dumps(report, ensure_ascii=False)[:60000]})
print('Failure report retained in the private storage release.')
