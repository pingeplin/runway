#!/usr/bin/env python3
"""Dump the actual edit content for each RED -> test-only-edit -> GREEN candidate,
plus the same-command check the base-rate script skipped."""
from __future__ import annotations
import json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from measure_weakening import TEST_CMD, NOT_A_RUN, TEST_PATH, classify


def stream(path: Path):
    pending, evs = {}, []
    for ln in path.open(errors='ignore'):
        try: d = json.loads(ln)
        except Exception: continue
        msg, ts = d.get('message'), d.get('timestamp', '')
        if isinstance(msg, dict) and isinstance(msg.get('content'), list):
            for b in msg['content']:
                if not isinstance(b, dict): continue
                if b.get('type') == 'tool_use':
                    name, inp = b.get('name'), b.get('input') or {}
                    if name == 'Bash':
                        cmd = str(inp.get('command', ''))
                        if TEST_CMD.search(cmd) and not NOT_A_RUN.match(cmd):
                            pending[b.get('id','')] = cmd
                    elif name in ('Edit','Write','MultiEdit'):
                        p = str(inp.get('file_path') or '')
                        if p:
                            evs.append(('edit', {'ts': ts, 'path': p,
                                'is_test': bool(TEST_PATH.search(p)),
                                'old': str(inp.get('old_string',''))[:700],
                                'new': str(inp.get('new_string',''))[:700],
                                'whole': str(inp.get('content',''))[:300],
                                'tool': name}))
        tur = d.get('toolUseResult')
        if isinstance(tur, dict) and 'stdout' in tur:
            tid = None
            if isinstance(msg, dict) and isinstance(msg.get('content'), list):
                for b in msg['content']:
                    if isinstance(b, dict) and b.get('type')=='tool_result':
                        tid = b.get('tool_use_id')
            if tid in pending:
                out = str(tur.get('stdout','')) + str(tur.get('stderr',''))
                evs.append(('run', {'ts': ts, 'cmd': pending.pop(tid),
                                    'verdict': classify(out), 'tail': out[-500:]}))
    return evs


def main():
    n = 0
    for root in sys.argv[1:]:
        for f in sorted(Path(root).glob('*.jsonl')):
            evs = stream(f)
            for a in range(len(evs)):
                if evs[a][0] != 'run' or evs[a][1]['verdict'] != 'RED': continue
                edits = []
                for b in range(a+1, len(evs)):
                    k, p = evs[b]
                    if k == 'edit': edits.append(p)
                    elif k == 'run':
                        if p['verdict'] == 'GREEN' and edits and all(e['is_test'] for e in edits):
                            n += 1
                            same = evs[a][1]['cmd'].strip() == p['cmd'].strip()
                            print('='*90)
                            print(f'CASE {n}  {f.name[:20]}  same-command={same}')
                            print(f'  RED   cmd: {evs[a][1]["cmd"][:110]}')
                            print(f'  RED  tail: {evs[a][1]["tail"][-260:].strip()[:260]}')
                            print(f'  GREEN cmd: {p["cmd"][:110]}')
                            for e in edits[:4]:
                                print(f'  --- {e["tool"]} {Path(e["path"]).name}')
                                if e['old']:
                                    print(f'      OLD: {e["old"][:300].strip()}')
                                    print(f'      NEW: {e["new"][:300].strip()}')
                                elif e['whole']:
                                    print(f'      WROTE(new file head): {e["whole"][:200].strip()}')
                        break
    print(f'\ntotal candidates dumped: {n}')


if __name__ == '__main__':
    main()
