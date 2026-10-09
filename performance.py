"""Full-log performance export using the same tested classifier as the monitor."""
import json
from pathlib import Path
import subprocess
from replay import parse_replay


def analyze_performance(path):
    with Path(path).open(encoding='utf-8-sig') as stream:
        replay=parse_replay(stream)
    classifier=Path(__file__).resolve().parent/'scripts'/'analyze_performance.cjs'
    result=subprocess.run(['node',str(classifier)],input=json.dumps(replay,allow_nan=False),
                          text=True,capture_output=True,timeout=60,check=True)
    data=json.loads(result.stdout)
    if data.get('schema_version')!=1 or data.get('source')!='full_rcg':
        raise ValueError('Invalid performance analysis output')
    return data
