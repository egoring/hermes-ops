#!/usr/bin/env python3
"""Run a project's README sh blocks in a clean copy, line by line, and log exit codes.

Usage: readme_repro.py SRC_ROOT OUT_DIR README_REL [SECTION_PREFIX ...]
  SRC_ROOT        project root to copy (read only)
  OUT_DIR         scratch dir (deleted and recreated)
  README_REL      README path relative to SRC_ROOT (e.g. 02_work/README.md)
  SECTION_PREFIX  run only ```sh blocks whose nearest heading starts with one of these
                  (default: all blocks). A block in a section whose heading starts with
                  'install' or '설치' that creates .venv is followed by putting .venv/bin on PATH.
Env: REPRO_EXCLUDE (comma list, default '.venv,node_modules,.next,__pycache__,*.pyc,_cc_logs,*.db')
     REPRO_STRIP_ENV (comma list of env vars to unset, default 'ANTHROPIC_API_KEY')
Writes OUT_DIR/out.txt; prints 'DONE ok/total'. Commands come only from the README.
"""
import os, re, subprocess, shutil, sys, time

src, out, readme_rel = sys.argv[1], sys.argv[2], sys.argv[3]
prefixes = sys.argv[4:]
shutil.rmtree(out, ignore_errors=True); os.makedirs(out)
proj = os.path.join(out, 'proj')
excl = os.environ.get('REPRO_EXCLUDE', '.venv,node_modules,.next,__pycache__,*.pyc,_cc_logs,*.db').split(',')
subprocess.run(['rsync', '-a'] + sum([['--exclude', e] for e in excl], []) + [src.rstrip('/') + '/', proj + '/'], check=True)
log = open(os.path.join(out, 'out.txt'), 'w', encoding='utf-8')
w = lambda s='': (log.write(s + '\n'), log.flush())
w(f'# README repro {time.strftime("%F %T")} copy={proj}')
lines = open(os.path.join(proj, readme_rel), encoding='utf-8').read().splitlines()
blocks, sec, i = [], '', 0
while i < len(lines):
    l = lines[i]
    if l.startswith('#'):
        sec = l.lstrip('#').strip()
    if l.strip() == '```sh':
        j, body = i + 1, []
        while lines[j].strip() != '```':
            body.append(lines[j]); j += 1
        blocks.append((i + 1, sec, body)); i = j
    i += 1
sel = [b for b in blocks if not prefixes or any(b[1].startswith(p) for p in prefixes)]
w('blocks: ' + ', '.join(f'{ln}:{s[:20]}' for ln, s, _ in blocks) + ' -> run ' + ', '.join(str(b[0]) for b in sel))
env = {k: v for k, v in os.environ.items() if k not in os.environ.get('REPRO_STRIP_ENV', 'ANTHROPIC_API_KEY').split(',') + ['VIRTUAL_ENV']}
res = []
for ln, sec, body in sel:
    sh = ['cd ' + repr(proj)]
    for k, c in enumerate(body):
        if c.strip():
            q = c.replace("'", "'\\''")
            sh += [f"echo '$ {q}'", c + ' 2>&1', f'echo "[exit $?] #{ln}:{k}"']
    r = subprocess.run(['bash', '-c', '\n'.join(sh)], env=env, capture_output=True, text=True)
    w(f'\n## block {ln} - {sec}'); w(r.stdout.rstrip())
    if r.stderr.strip():
        w('[stderr] ' + r.stderr.strip()[:2000])
    res += [int(m.group(1)) for m in re.finditer(r'\[exit (\d+)\] #', r.stdout)]
    venv = os.path.join(proj, os.path.dirname(readme_rel), '.venv', 'bin')
    if os.path.isdir(venv) and venv not in env['PATH']:
        env['PATH'] = venv + ':' + env['PATH']; env['VIRTUAL_ENV'] = os.path.dirname(venv)
        w(f'(venv activated for later blocks: {venv})')
ok = sum(1 for x in res if x == 0)
w(f'\n# end {time.strftime("%T")} commands {len(res)} exit0 {ok} nonzero {[x for x in res if x]}')
print(f'DONE {ok}/{len(res)}')
