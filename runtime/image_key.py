"""A runtime changes only when its Docker recipe, server or library pins change."""
import hashlib
from pathlib import Path


def image_key(root):
    root=Path(root);digest=hashlib.sha256()
    paths=[root/'runtime'/'Dockerfile',root/'runtime'/'build_runtime.py',root/'runtime'/'image_key.py',root/'team_build.py']
    paths+=sorted(p for p in (root/'vendor'/'rcssserver-19.0.0').rglob('*') if p.is_file())
    for path in paths:
        digest.update(str(path.relative_to(root)).encode());digest.update(b'\0');digest.update(path.read_bytes());digest.update(b'\0')
    return digest.hexdigest()

if __name__=='__main__':print(image_key(Path(__file__).resolve().parents[1]))
