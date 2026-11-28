#!/usr/bin/env python3
# evidence-gate warn 판정 보조 (11-28): would_block 마다 "없다"고 한 명령이 세션에 실제로 있었는지, E3 는 마지막 코드 쓰기 뒤 재실행이 있었는지 본다. 읽기 전용·LLM 0. 휴리스틱(스크립트 이름·핵심 토큰 일치)이라 리뷰어 판정을 대신하지 않는다.
# evidence-gate would_block 17건 전수 점검: '없다'고 한 명령이 실제 세션에 있었는지 (읽기 전용)
import json, re, sqlite3, os
from datetime import datetime
H=os.path.expanduser('~/.hermes/profiles/coder-bot')
rows=[json.loads(l) for l in open(H+'/logs/evidence_gate.jsonl') if l.strip()]
con=sqlite3.connect(f"file:{H}/state.db?mode=ro",uri=True)
def cmds(sid):
    out=[]
    for tc,ts in con.execute("select tool_calls,timestamp from messages where session_id=? and role='assistant' and tool_calls is not null order by timestamp,id",(sid,)):
        try: calls=json.loads(tc)
        except: continue
        for t in calls:
            f=t.get('function',{}); 
            try: a=json.loads(f.get('arguments','{}'))
            except: a={}
            if f.get('name')=='terminal': out.append(('run',ts,a.get('command','')))
            elif f.get('name') in ('write_file','patch'): out.append(('write',ts,a.get('path','')))
    return out
KEY=re.compile(r"[\w./-]+\.(?:py|sh|ipynb)|\w+ kernels \w+|git (?:commit|status)|shasum|presubmit_check|build_zip|pytest|py_compile|diff -r|cmp")
res=[]
for r in rows:
    if r['verdict']!='would_block': continue
    cs=cmds(r['session'])
    items=[]
    for m in r['missing']:
        kind=m[:2]; cmd=(re.search(r"`([^`]*)",m) or [None,''])[1]
        keys=[k for k in KEY.findall(cmd)][:2]
        # 핵심 토큰(스크립트 경로 끝부분) 이 실행 명령에 있었나
        hit=None
        for k in keys:
            kk=os.path.basename(k) if '/' in k else k
            runs=[c for c in cs if c[0]=='run' and kk in c[2]]
            if runs: hit=(kk, len(runs)); break
        items.append((kind, cmd[:70], keys[:1], hit))
    res.append((r['ts'][5:16], r['task'], r['tool'], len(cs), items))
for ts,task,tool,n,items in res:
    found=sum(1 for i in items if i[3]); print(f"\n{ts} {task} {tool} 도구호출 {n} — 누락 {len(items)}개 중 실행 흔적 {found}개")
    for k,c,key,hit in items: print(f"   {k} {'있음 '+str(hit) if hit else '없음':22s} | {c}")

print("\n\n=== E3 순서 점검 + E2 exit 불일치 점검 ===")
CODE=re.compile(r"\.(py|sh|ipynb|ts|js|json|yaml|yml|toml)$")
def runs_with_exit(sid):
    out={}; order=[]
    for role,tc,tcid,content,ts in con.execute("select role,tool_calls,tool_call_id,content,timestamp from messages where session_id=? order by timestamp,id",(sid,)):
        if role=='assistant' and tc:
            try: calls=json.loads(tc)
            except: continue
            for t in calls:
                f=t.get('function',{})
                try: a=json.loads(f.get('arguments','{}'))
                except: a={}
                order.append([t.get('id'),f.get('name'),a.get('command') or a.get('path') or '',ts,None])
        elif role=='tool' and tcid:
            for o in order:
                if o[0]==tcid:
                    m=re.search(r'"exit_code":\s*(-?\d+)',content or ''); o[4]=int(m.group(1)) if m else None
    return order
for r in rows:
    if r['verdict']!='would_block': continue
    od=runs_with_exit(r['session'])
    writes=[o for o in od if o[1] in ('write_file','patch') and CODE.search(o[2] or '')]
    last_w=max([o[3] for o in writes],default=0)
    for m in r['missing']:
        cmd=(re.search(r"`([^`]*)",m) or [None,''])[1]
        keys=KEY.findall(cmd)
        if not keys: continue
        kk=os.path.basename(keys[0]) if '/' in keys[0] else keys[0]
        runs=[o for o in od if o[1]=='terminal' and kk in (o[2] or '')]
        if m.startswith('E3'):
            after=[o for o in runs if o[3]>last_w]
            print(f"{r['task']} E3 {kk:32s} 마지막 코드 쓰기 뒤 실행 {len(after)}회 / 전체 {len(runs)}회 → {'오탐' if after else '정탐(쓰기 뒤 재실행 없음)'}")
        elif '다르다' in m:
            ex=[o[4] for o in runs]
            print(f"{r['task']} E2exit {kk:28s} 실제 exit들 {ex} | {m[m.find('적은'):][:30]}")

print("\n=== 정탐 후보 상세 ===")
for task in ('t_d166296b','t_3ade79a2'):
    r=[x for x in rows if x['task']==task and x['verdict']=='would_block'][0]
    od=runs_with_exit(r['session'])
    ws=[o for o in od if o[1] in ('write_file','patch') and CODE.search(o[2] or '')]
    lw=ws[-1]
    print(task, "마지막 코드 쓰기:", lw[1], lw[2].replace(os.path.expanduser('~'),'~')[-70:])
    later=[o for o in od if o[3]>lw[3] and o[1]=='terminal']
    print("   그 뒤 terminal", len(later), "회:", [ (o[2] or '')[:60].replace('\n',' ') for o in later][:4])
for task,key in (('t_bbe1422b','code_cell_mismatch_vs_V6'),('t_f187b58c','secs')):
    r=[x for x in rows if x['task']==task and x['verdict']=='would_block'][0]
    od=runs_with_exit(r['session'])
    hits=[o for o in od if o[1]=='terminal' and key in (o[2] or '')]
    print(task, key, "포함 실행", len(hits), [ (o[2] or '')[:90].replace('\n',' ') for o in hits][:2])
