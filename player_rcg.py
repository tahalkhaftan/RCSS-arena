"""Optional ULG5 player tracks; the original server RCG is always retained."""
import json
from contextlib import ExitStack
from analysis import sexpr


def selection(value):
    if value is None:
        return {'enabled': False, 'left': [], 'right': []}
    if not isinstance(value, dict) or type(value.get('enabled')) is not bool:
        raise ValueError('player_rcg.enabled must be boolean')
    result = {'enabled': value['enabled']}
    for side in ('left', 'right'):
        numbers = value.get(side, [])
        if not isinstance(numbers, list) or any(type(n) is not int or not 1 <= n <= 11 for n in numbers):
            raise ValueError('Player numbers must be integers from 1 to 11')
        result[side] = sorted(set(numbers)) if result['enabled'] else []
    if result['enabled'] and not any(result[s] for s in ('left', 'right')):
        raise ValueError('حداقل یک بازیکن از تیم چپ یا راست انتخاب کن.')
    return result


def record(value):
    if isinstance(value, list):
        return '(' + ' '.join(record(v) for v in value) + ')'
    return json.dumps(value, ensure_ascii=False) if not value or any(c.isspace() or c in '()"' for c in value) else value


def export_players(source, config):
    chosen = selection(config.get('player_rcg'))
    targets = [(side, 'l' if side == 'left' else 'r', n) for side in ('left', 'right') for n in chosen[side]]
    if not targets:
        return []
    folder = source.parent / 'player-rcg'
    folder.mkdir(exist_ok=True)
    paths = []
    try:
        with ExitStack() as stack:
            outputs = []
            for side, code, n in targets:
                path = folder / f'{side}-player-{n:02d}.rcg'
                paths.append(path)
                outputs.append((code, str(n), stack.enter_context(path.open('w', encoding='utf-8'))))
            with source.open(encoding='utf-8') as stream:
                for line in stream:
                    if not line.startswith('(show '):
                        for _, _, out in outputs:
                            out.write(line)
                        continue
                    frame = sexpr(line)
                    for code, n, out in outputs:
                        keep = [frame[0], frame[1]]
                        for item in frame[2:]:
                            ident = item[0] if isinstance(item, list) and item else None
                            if isinstance(ident, list) and ident and ident[0] in ('l', 'r'):
                                if ident != [code, n]:
                                    continue
                            keep.append(item)
                        out.write(record(keep) + '\n')
        return [str(p.relative_to(source.parent)) for p in paths]
    except Exception:
        for path in paths:
            path.unlink(missing_ok=True)
        raise
