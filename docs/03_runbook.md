# 점검 절차 (runbook)

> 명령은 복사해서 그대로 쓴다. **게이트웨이 재시작·launchd 변경은 사용자 승인 후.**

## R1. 정기 점검 (주 1회, 5분)

```bash
# 1) 게이트웨이와 봇 연결
launchctl list | grep ai.hermes.gateway
grep -E "discord connected|ERROR" ~/.hermes/logs/gateway.log | tail -5
# 2) 래퍼 복귀 여부 (0이어야 함, 06_이슈 #9)
grep -c osascript ~/Library/LaunchAgents/ai.hermes.gateway.plist
# 3) 파이프라인 지표 → 04_운영지표.md 기록표에 한 줄 추가
python3 ~/hermes-ops/scripts/kanban_metrics.py --days 7
# 4) 오래 막힌 태스크 (지표 출력의 '열린 태스크' 표)
# 5) 디스크
df -h ~ | tail -1
```

## R2. 모델 교체

| 순서 | 명령 / 확인 |
|---|---|
| 1 | 모델 ID 확인: Hermes 소스 `grep -rho "claude-[a-z]*-[0-9-]*" ~/.hermes/hermes-agent --include=*.py \| sort -u`. 없으면 CLI 호출로 확인: `hermes -p <봇> chat -Q -m <모델> --max-turns 1 -q "모델 이름만"` 후 `profiles/<봇>/logs/agent.log`에서 `model=<모델>`과 정상 `finish_reason` |
| 2 | 백업: `cp profiles/<봇>/config.yaml{,.bak_$(date +%Y%m%d_%H%M)_<사유>}` |
| 3 | `hermes kanban --board <보드> list \| grep running` → 없을 때 진행 |
| 4 | `hermes -p <봇> config set model.default <모델>` |
| 5 | (승인) `hermes gateway restart` → 30초 뒤 `discord connected` 3개 확인 |
| 6 | 행동 테스트 해당 봇 항목 (`01_운영구조.md` §7.2) |
| 7 | `01_운영구조.md` §1·§3, `변경이력.md` 갱신, 커밋 |

되돌리기: 백업 파일을 `config.yaml`로 복사 → 5번.

## R3. Hermes 업데이트 (전·후)

### 업데이트 전

| 순서 | 확인 |
|---|---|
| 1 | `hermes update --check`, `hermes update --plan` (재시작 대상 서비스와 방식 확인) |
| 2 | 전체 백업 `hermes backup -o <파일>`. 코드(`hermes-agent/`)와 `installs/`는 빠진다 → 데이터 전용 백업이다 |
| 3 | kanban·state DB는 따로 복사: `sqlite3 <db> ".backup <대상>"` 후 복사본에 `PRAGMA integrity_check` → `ok` |
| 4 | 로컬 수정 확인: 설치 트리에서 `git status`. 업스트림에 같은 수정이 있는지 보고 `--keep-stash` 사용 |
| 5 | 실행 중 워커 0 확인. (a) DB의 running 카드 (b) `kanban_worker_client`·`agent.managed_worker` 프로세스 (c) 에이전트 모드 cron(`no_agent: false`)의 다음 실행 시각. 셋 다 봐야 한다. 비상 정지는 `hermes pause` / `hermes resume`(v0.23.0) |

실행: 터미널에서 `hermes update --yes --backup --keep-stash`를 권장한다. Discord `/update`는 백업 여부가 `updates.pre_update_backup` 설정을 따른다.

### 업데이트 후

`hermes update` / `gateway start` / `gateway install` 은 plist를 다시 만든다.

먼저 살아 있는지 확인한다.

| 확인 | 기대 |
|---|---|
| `hermes --version` | 새 버전 |
| `ls -l ~/.hermes/gateway.sock` | 소켓이 있다 |
| `lsof -t ~/.hermes/gateway.sock` | `~/.hermes/state/gateway.lifecycle.json`의 pid와 같다. 이 환경에서 `pgrep -f "gateway run …"`은 0줄이었으므로 pid는 소켓으로 찾는다 |
| `launchctl list \| grep ai.hermes` | 서비스가 올라와 있다 |
| 대시보드 | 응답한다 |

소켓이 없으면 워커 0을 확인한 뒤 `hermes gateway restart`를 1회만 한다.

그다음 기존 절차:

| 순서 | 확인 |
|---|---|
| 1 | `grep -c osascript ~/Library/LaunchAgents/ai.hermes.gateway.plist` → 1 이상이면 래퍼가 돌아온 것 |
| 2 | (승인) 래퍼 재제거: 백업 `ai.hermes.gateway.plist.bak_osascript_20260925_2232` 와 새 plist를 diff 해서 `ProgramArguments`만 옮긴다(새 plist의 다른 변경은 유지). `launchctl bootout gui/$(id -u)/ai.hermes.gateway && launchctl bootstrap gui/$(id -u) <plist>` |
| 3 | 봇 3개 connected, CPU 확인 `ps -o pid,%cpu,command -ax \| grep -i "hermes.*gateway" \| grep -v grep` |
| 4 | 모델 ID가 새 카탈로그에 있는지 (`R2` 1번 명령) |
| 5 | 행동 테스트 T3·T5·T6 |
| 6 | kanban 도구·CLI 옵션 변화: `hermes kanban create --help` 를 이전과 비교 |

### webapp (v0.23.0)

기본값은 `webapp.enabled: false`다. 쓰려면 `hermes config set webapp.enabled true` 후 `hermes gateway restart`. 그다음 `hermes webapp`이 일회용(60초) 로그인 링크를 연다. 주소를 직접 열면 로그인 안내만 보이는 것이 정상이다.

### 되돌리기

릴리스 업데이트는 태그 커밋으로 detached HEAD 이동을 하고 `main` 브랜치는 그대로 둔다.

1. 서비스 정지: `hermes gateway stop`(= launchd bootout). 대시보드는 `launchctl bootout`
2. `git switch main`
3. `hermes pm install` → `hermes pm doctor`
4. 서비스 시작

DB 복원은 해당 파일을 연 프로세스가 0일 때만 한다(`lsof <파일>`로 먼저 확인).

## R4. 규칙(SOUL·AGENTS) 수정

| 순서 | 내용 |
|---|---|
| 1 | 백업 `*.bak_<날짜>` |
| 2 | 규칙을 옮길 땐 받는 쪽 먼저 추가 → 보내는 쪽 삭제 |
| 3 | 층 확인 (`01_운영구조.md` §4 표): SOUL에 프로젝트 전용 내용을 넣지 않는다 |
| 4 | 실행 중 worker는 옛 규칙으로 끝난다 → 급하면 끝난 뒤 수정 |
| 5 | 새 세션에서 T3 (+ 바뀐 부분 관련 테스트) |
| 6 | `변경이력.md`, 커밋 (프로젝트 AGENTS는 프로젝트 저장소에) |

## R5. 태스크 이상 대응

| 증상 | 확인 | 조치 |
|---|---|---|
| `crashed` | `boards/<보드>/logs/<태스크>.log` 끝부분, 같은 시각 `gateway.log` | 디스패처가 자동 재시도(`failure_limit: 2`). 같은 태스크 2회 이상이면 원인 기록(`06_이슈.md` #11) |
| `reclaimed` + `stale_lock` | 이벤트 payload의 `last_heartbeat_at` vs `now` | 긴 작업이 heartbeat 없이 15분 초과. 태스크에 `--max-runtime` 지정 또는 작업을 쪼갠다 |
| 같은 block 반복 (`block_loop_detected`) | block 사유 | 승인 요청이면 규칙 위반 → 결정용 요약으로 바꾸라고 코멘트 |
| 오래된 blocked | `kanban_metrics.py` 열린 태스크 표 | 재개(`unblock`) / 보관(`archive`) 사용자 결정 |
| 알림 경고 `has no parent_chat_id anchor` 반복 | `hermes kanban --board <보드> notify-list` | 끝난 태스크 구독 해제 (R6) |

## R6. 끝난 태스크 알림 구독 정리 (월 1회 또는 경고가 보일 때)

```bash
B=<보드>   # 예: webapp
hermes kanban --board $B notify-list --json > /tmp/subs_$B.json   # 백업 겸 목록
python3 - "$B" <<'EOF'
import json, os, sqlite3, subprocess, sys
b = sys.argv[1]
subs = json.load(open(f"/tmp/subs_{b}.json"))
st = dict(sqlite3.connect(os.path.expanduser(f"~/.hermes/kanban/boards/{b}/kanban.db")).execute("select id,status from tasks"))
for s in subs:
    if st.get(s["task_id"]) not in ("done", "archived"):
        continue  # 열린 태스크 구독은 유지
    cmd = ["hermes", "kanban", "--board", b, "notify-unsubscribe", s["task_id"],
           "--platform", s["platform"], "--chat-id", s["chat_id"]]
    if s.get("thread_id"):
        cmd += ["--thread-id", s["thread_id"]]
    print(s["task_id"], subprocess.run(cmd, capture_output=True).returncode)
EOF
```

## R7. 되돌리기 위치

| 대상 | 백업 |
|---|---|
| 봇 설정 | `profiles/<봇>/config.yaml.bak_*` |
| SOUL | `profiles/<봇>/SOUL.md.bak_*` |
| plist | `~/Library/LaunchAgents/ai.hermes.gateway.plist.bak_osascript_20260925_2232` |
| 폴더 이전 전체 | `~/.hermes/backups/20260928_mig/` |
| 알림 구독 | `~/.hermes/backups/<날짜>_ops/<보드>_notify_subs.json` |
| 문서·AGENTS | 각 git 저장소 이력 |

## R8. 자동화 (no_agent cron, 토큰 0)

| 작업 | 주기 | 스크립트 (`~/.hermes/scripts/`) | 알림 |
|---|---|---|---|
| kanban 이상 감시 | 30분 | `kanban_watch.py` | 새 crashed/잠금 만료 회수/gave_up/protocol_violation/block 루프, blocked 24시간+ (태스크당 1회). 크래시·회수는 `~/.hermes/kanban/incidents/`에 증거(payload + 워커 로그 200줄 + gateway ±3분) 저장 |
| 일일 백업 | 매일 04:30 | `daily_backup.sh` | 성공 시 조용. 실패·디스크 여유 10GB 미만일 때만 멘션. `~/.hermes-backups/`에 최근 7개 (1개 약 200MB, 10초) |
| 주간 지표 | 월 09:10 | `weekly_metrics.py` | 핵심 수치 + 지난주 대비. 원본 표는 `reports/weekly/<주차>.md` (로컬 전용) |
| effort 변경·적용 + 최종점검 | 5분 | `effort_watch.py` | 📋 fable-bot 최종점검 배정, 🧠 실행 시작, 🎚 태스크 effort 지정(`reasoning_effort_set`), ⚙️ 프로필 기본 effort 변경(멘션), ✅ 봇 세션이 기본과 다른 effort로 실제 시작됨. 말로 요청한 최종점검이 xhigh로 돌았는지 확인용 |
| 리소스 감시 / 사용량 보고 | 09·21시 / 09시 | `resource_alert.py` / `usage_report.py` | 기존 |
| 대기 카드 깨우기 | 15분 | `kanban_wake.py` (default 프로필) | `SCHEDULED_UNTIL`이 지난 scheduled 카드를 다시 배정. 12회 넘으면 알림만 (`01_운영구조.md` §5.7) |

에이전트 cron (토큰 사용):

| 작업 | 주기 | 프로필 | 내용 |
|---|---|---|---|
| 규칙 파일 진단 | 월 09:00 | coder-bot (Sonnet) | `claude-md-improver` 스킬로 AGENTS.md·SOUL.md 11개를 점수화해 Discord로 보고. **읽기 전용** — 수정은 사용자 지시 후. Discord 전송 cron은 Discord 토큰이 있는 봇 프로필에 둔다(default에 두면 `blocked_config`) |

전송은 공용 `_notify.py`(helper-bot 계정, 알림 채널). 복원: `hermes import ~/.hermes-backups/<zip>`.
테스트: `kanban_watch.py --dry-run --since-id <과거 id>` / `weekly_metrics.py --dry-run` / `effort_watch.py --dry-run --since <epoch>`.

참고: `hermes config set agent.reasoning_effort <v>`는 "not a recognized config key" 경고를 내지만 게이트웨이가 실제로 읽는 키다(`hermes_constants.resolve_reasoning_config`). 경고를 없애려면 `--force`.

## R9. 봇 장애 1차 진단 (응답 없음 / 오프라인)

| 증상 | 먼저 볼 것 | 판단 |
|---|---|---|
| 봇이 답 대신 짧은 안내 문구만 보냄, 또는 전부 응답 없음 | `hermes -p <bot> auth list` + 한 줄 테스트 `hermes -p <bot> chat -Q --max-turns 1 -q "1만 답해"` | `No Anthropic credentials found` / 로그 `terminally invalid (invalid_grant)` → **인증 만료**. 사용자가 Claude Code 재로그인(`claude /login`), 안 되면 `hermes -p <bot> auth add anthropic`. 게이트웨이 재시작 불필요 (#16) |
| Discord에서 봇이 오프라인 | `~/.hermes/gateway_state.json`의 `platforms.<bot>:discord.error_code` | `discord_connect_error` + `No route to host` → **맥 네트워크** (#18). 회복되면 최대 5분 안에 자동 재연결 |
| | | `discord_websocket_health_stale` (`socket_closed`, `latency_exceeded`) → **게이트웨이 지연** (#17). 직전 `Can't keep up` 경고와 그 시각의 cron·도구 실행을 확인 |
| 한 봇만 계속 재연결 실패 | 토큰 유효성: Discord `GET /users/@me` (값은 출력하지 말 것), `session_start_limit.remaining` | 토큰·한도 정상이면 다음 재시도(5분)를 기다린다. `hermes -p <bot> gateway restart`는 multiplex 구조에서 재연결을 하지 않고 standalone 안내만 출력한다 (10-10 확인) |
| 계속 실패 | — | `hermes gateway restart` (봇 4개 동시 재연결, 사용자 승인 필요) |

봇 `.env`의 `DISCORD_BOT_TOKEN`은 **한 줄만** 둔다. 여러 줄이면 마지막 줄이 쓰이고, 앞줄에 다른 봇 토큰이 섞여 있으면 스크립트가 엉뚱한 봇으로 보낼 수 있다(10-01 정리).

## R10. 스킬 공유·추천 점검 (`01_운영구조.md` §3.1)

```bash
# 1) 봇이 공유 스킬을 읽는지 (external 줄 수, kanban 전용 2개는 평소 빠질 수 있음)
for p in coder-bot reviewer-bot helper-bot fable-bot; do echo "$p $(COLUMNS=250 hermes -p $p skills list | grep -c external)"; done
# 2) 훅 등록·동의 (✓ allowlisted 여야 함)
hermes -p <프로필> hooks doctor
# 3) 추천이 실제로 도는지 (플랫폼·프로필·후보가 한 줄씩)
tail -20 ~/.hermes/logs/skill_recommend.log
# 4) 특정 질문의 점수 확인
python3 ~/.hermes/hooks/skill_recommend.py --explain "질문" --profile <프로필>
```

- 새 프로필에 훅을 붙일 때: `config.yaml`에 `hooks.pre_llm_call` 추가 → allowlist 등록(무인 게이트웨이는 동의 프롬프트를 띄우지 않고 훅을 건너뛴다). `hermes --accept-hooks ... hooks test`는 동의를 **기록하지 않는다** — `agent.shell_hooks._record_approval(event, command)`를 그 프로필 `HERMES_HOME`으로 호출해 기록했다.
- 훅 명령 문자열을 바꾸면 allowlist 키도 바뀌어 다시 등록해야 한다.
- 끄기: 프로필 `config.yaml`의 `hooks:` 블록 삭제 또는 `hermes -p <프로필> hooks revoke "<command>"`.
- 추천이 엉뚱하면 `--explain`으로 걸린 단어를 보고 훅의 `STOP`/`GENERIC` 목록이나 hermes-hub `skill-search.ts` 동의어를 고친다. 고친 뒤 `python3 ~/.hermes/hooks/skill_recommend_eval.py`로 회귀 통과 + 실제 턴 재생 결과를 확인한다(손으로 고른 질문만 보면 실제 디스코드에서 효과가 없을 수 있다 — 11-11~16 실측: 사람 질문 84건 중 💡 0건).
- 효과 측정: 주입 문맥은 `messages`에 저장되지 않는다. "후보 스킬을 그 턴에 `skill_view` 했는가"로 본다.
- 스킬을 자꾸 건너뛸 때: (1) 그 봇 목록에 스킬이 있는지(`skills list`, 공유 누락이 흔하다) (2) SOUL `## 스킬 먼저 로드` 표에 그 작업 유형이 있는지 (3) 대화형으로 같은 질문을 보내 `📚 Skill …`이 뜨는지. 새 SOUL 규칙은 새 스레드부터 확실히 적용된다(긴 스레드는 압축 전까지 기존 프롬프트 유지).
- `Skill security warning … outside the trusted skills directory` (공유 스킬 로드 시 errors.log WARNING): 링크가 default `~/.hermes/skills/`로 풀려서 나는 경고다. 로드는 정상.
- 1회성 실행(`hermes chat -q -Q`)은 스킬 프롬프트가 "아는 일엔 로드하지 말라"로 바뀐다. 자동 로드 테스트는 대화형 모드로 한다.

- 모델이 실제로 스킬을 불러오는지 재기: `python3 ~/.hermes/hooks/skill_trigger_eval.py --profiles reviewer-bot,coder-bot --runs 3 --workers 5` (120회 ≈ 40분, 봇 인증을 같이 쓰니 동시 실행 5 이하). 결과 `~/.hermes/logs/skill_trigger_eval/`.
- 디스코드에서 확인: 채널에 **새 메시지**(기존 스레드 말고)로 봇을 멘션해 보낸다 → 세션 `messages.tool_calls`에 `skill_view`, 답변 첫 줄 `🧩`. 기존 스레드는 압축 때까지 옛 SOUL로 동작한다.

### 스킬이 10만 자 한도에 붙었을 때 (분할)

봇의 `skill_manage` patch가 `content is N characters (limit: 100,000)`로 실패하고, 봇이 내용을 깎아 맞추기 시작한다. 1주 점검(`fix_watch`)이 9만 자 넘는 파일을 알린다.

```bash
B=~/.hermes/backups/$(date +%Y%m%d)_skill_split; mkdir -p $B
COPYFILE_DISABLE=1 tar -C <스킬 상위 폴더> -czf $B/<스킬>.tgz <스킬>      # ._ 파일 없이 백업
# SKILL.md: 항상 지킬 규칙 맨 앞 + 단계 개요 + References(파일마다 "언제 읽는지"). 세부는 references/로 원문 그대로 이동
python3 ~/.hermes/scripts/skill_split_check.py <스킬> --profile <프로필> --backup $B   # PASS까지 반복
```

검사 조건: 원본의 모든 내용 줄 보존(제목 수준·글머리표만 변경 허용), frontmatter 동일, SKILL.md ≤24k, 모든 참조 파일이 SKILL.md에 연결. 참조 파일도 한도가 같으니 큰 파일은 `## ` 단위로 옆 파일로 나눈다(원래 이름을 첫 조각으로 유지해 기존 링크가 살게). 봇이 작업 중일 수 있으니 쓰기 직전 mtime을 다시 확인한다.

### 큐레이터가 기본 내장 스킬을 보관할 때

30일 안 쓴 스킬은 기본 내장이라도 `.archive/`로 옮겨진다(11-07 55개, 11-14 7개). `curator pin`은 내장 스킬을 거부하므로 **restore 후 lock**:

```bash
hermes curator restore <이름> && hermes curator lock <이름>   # lock된 스킬은 자동 전이에서 빠진다
ls ~/.hermes/skills/.archive/                                 # 며칠 뒤 다시 확인
```

lock하면 에이전트가 그 스킬을 고치지 못한다(읽기·자동 로드는 됨). 같은 이름 카테고리 폴더와 겹치면 restore가 실패한다 → 원래 경로로 직접 `mv`.

## R11. 설계 카드·리뷰 양식 (09 §4.4·§4.5)

설계 카드 양식 (reviewer가 coder 카드를 만들 때):

````
## 한 줄 요약
## 범위
- 바꿀 파일: <경로> — <목적> — <공개 함수·시그니처>
- 범위 밖(건드리지 않음): <목록>
## 데이터 흐름·경계 사례
## 합격 기준 (숫자)
| # | 기준 | 임계값 | 확인 명령 |
## 합격 명령
```bash
# 줄 끝 숫자 = 기대 종료 코드(exit code). 출력값이 아니다(R11 ②)
<명령 1>            # expect: 0
<명령 2>            # expect: 0
```
## 위험·가정
## 진행 규칙 (coder-bot)
1) 스펙대로 구현하고 재해석하지 않는다 2) 합격 명령을 마지막 수정 뒤에 이 세션에서 실행한다
3) request-review(reviewer=reviewer-bot, metadata.verification=[{cmd, exit_code, result}])
4) 반려되면 🔴만 고치고 다시 2)부터 한다
````

리뷰 양식:

```
[round N/<상한>] 판정: 승인 | 수정 요청
합격 명령 재실행: | 명령 | coder exit | reviewer exit | 일치 |
기준별: | # | 측정값 | 충족 |
🔴 (스펙·합격 기준 위반, 버그, AGENTS.md 규칙 위반만)
🟡/🟢 (반송 사유 아님)
제외: 스타일·이름·취향 — 적지 않는다
```

- ① 리뷰 반려 상한은 **2회**(U3, 11-20 결정). 봇 SOUL의 "[round N/3]" 문구는 사용자가 SOUL을 고칠 때 함께 바뀐다(그 전까지 SOUL은 3).
- ② `## 합격 명령` 블록 줄 끝의 `# expect: N`은 **그 명령의 기대 종료 코드(exit code)**다(없으면 0). 출력값이나 출력 줄 수가 아니다. 개수를 확인하려면 비교를 명령 안에 넣는다: 일치 0줄 확인은 `! grep -q '<패턴>' <파일>   # expect: 0`, 정확한 개수는 `test "$(grep -c '<패턴>' <파일>)" -eq 3   # expect: 0`. `grep -c`·`wc -l`처럼 숫자를 출력하는 명령 끝에 `# expect: <숫자>`만 붙이지 않는다(11 통합 검증 T6: `grep -Ec … # expect: 0`을 '출력 0'으로 읽어 카드가 막혔다). 줄은 반드시 `# expect: N`으로 끝난다(evidence-gate는 줄 끝만 읽는다). 설명은 블록 안의 `#` 주석 줄에 쓴다(evidence-gate는 `#`로 시작하는 줄을 명령으로 세지 않는다).
- ③ coder는 `metadata.verification=[{cmd, exit_code, result}]`를 마지막 수정 뒤 이 세션에서 실행한 그대로 적는다(evidence-gate가 활성화되면 기계로 대조, D24).
- ④ reviewer가 만드는 coder 카드부터 이 양식이 의무다(U5).
- ⑤ 프로필 `.env`(시험 프로필 포함)는 **사람이 쓴다.** 워커가 write_file 가드를 스크립트로 돌아가 `.env`를 쓰는 방식은 금지한다. 필요하면 카드에 내용을 적고 kanban_block으로 사람에게 넘긴다(11-21 통합 검증 K1에서 itest `.env`를 스크립트로 덮어쓴 건은 사후 승인).

## R12. 평가 운영 (09 §5·§6.3)

> 코드·테스트·실행 파일은 `~/.hermes/evals/`에 만들어져 있고 **cron 등록은 0건, 활성화 전**이다(사용자 결정 11-21: 전체 구현 → 통합 검증 → 한 번에 활성화). 이 절의 등록 명령은 활성화 때 사용자가(또는 승인받은 reviewer가) 쓴다. 평가 LLM은 평가 전용 키만 쓴다(D25·D26).

### 12.1 구성요소

| 구성 | 파일 | 하는 일 | 주기(KST) | cron 이름 (실행 파일) | 인터프리터 | LLM |
|---|---|---|---|---|---|---|
| A + 주간 보고 | `~/hermes-ops/scripts/kanban_metrics.py`, `eval_compare.py`, `~/.hermes/evals/bin/eval_weekly_report.py` | 6절 보고서를 `reports/<주>.md`에 쓰고 요약을 `quiet_hours.emit()`으로 알린다 | 월 09:40 | `eval-weekly-report` (`eval_weekly_report.sh`) | `/opt/anaconda3/bin/python3` | 0 |
| B0 스냅샷 | `eval_snap.py` | 리뷰 요청 때의 문서 상태를 `snap/`에 저장 | 2분마다 | `eval-snap` (`eval_snap.sh`) | `/opt/anaconda3/bin/python3` | 0 |
| B(i) 코드 검사 | `eval_kchecks.py` | K1~K8을 `b/k_checks.jsonl`에 창별로 쌓음(같은 창은 교체, 35일 보관) | 매일 04:30 | `eval-kchecks` (`eval_kchecks.sh`) | `/opt/anaconda3/bin/python3` | 0 |
| B(ii) 판정 제출 | `eval_judge.py --submit` (J1 → J2), `eval_llm.py`, `eval_guard.py` | 지난 주 표본·반려를 Message Batches로 제출 | 매일 03:00 | `eval-judge-submit` (`eval_judge_submit.sh`) | `~/.hermes/hermes-agent/venv/bin/python`(SDK) | 평가 키 |
| B(ii) 판정 수거 | `eval_judge.py --collect` | 끝난 배치를 `b/j1/<주>.jsonl`·`b/j2/<주>.jsonl`과 장부에 씀 | 매시 정각 | `eval-judge-collect` (`eval_judge_collect.sh`) | `~/.hermes/hermes-agent/venv/bin/python`(SDK) | 평가 키 |
| C 스킬 효과 + J3 | `eval_c_run.py`, `eval_c_report.py` | 고정 문제 ON/OFF 시행 → `c/results/<run>/` | 수동(cron 없음) | — | `~/.hermes/hermes-agent/venv/bin/python` | 평가 키 |
| 트리거 회귀 | `skill_trigger_eval.py` | 합성 질문에서 스킬 로드 확인 → `trigger/<시각>.jsonl` | 수동 | — | 같음 | 평가 키 |
| 판정기 보정 | `eval_calib.py` | 라벨 CSV 추출·합의율·κ·합격 판정 | 수동 | — | `/opt/anaconda3/bin/python3` | 0 |
| 키 점검 | `check_key.py` | 평가 키 형식·모델 조회·최소 호출 1회 | 수동 | — | `~/.hermes/hermes-agent/venv/bin/python` | 평가 키(약 $0.0001) |
| 야간 실패 알림 보류·방출 | `eval_cron_quiet.py` | 4개 작업 래퍼가 23~09시에 실패하면 알림 대신 `quiet_hold/eval-cron-fail.jsonl`에 보류하고(30건 상한), 09:05에 한 번에 낸다 | 매일 09:05 | `eval-alert-flush` (`eval_alert_flush.sh`) | `/opt/anaconda3/bin/python3` | 0 |

실행 파일은 `~/.hermes/evals/cron/*.sh` 6개(권한 755)다. `eval_snap.sh`·`eval_kchecks.sh`·`eval_judge_submit.sh`·`eval_judge_collect.sh`는 첫 줄에서 `eval_cron_quiet.py run`으로 자기를 다시 실행한다: 23~09시에 0이 아닌 종료면 실패 내용을 보류하고 종료 코드 0으로 끝나며(stdout `QUIET_HELD …`), 그 밖 시간에는 종료 코드를 그대로 낸다. `eval_judge_submit.sh`·`eval_judge_collect.sh`는 J1 다음 J2를 부르고, 429·overloaded(종료 코드 3)면 J2를 건너뛰고 그 코드로 끝난다.

### 12.2 활성화 순서 (사람이 한다)

1. 실행 파일을 reviewer 프로필 `scripts/`로 복사한다. 작업은 그 프로필의 `scripts/` 안 파일만 실행하기 때문이다(`~/.hermes/hermes-agent/cron/scheduler_script.py:323-366`). `.sh`는 bash로 돈다(같은 파일 `:408`).
```bash
for n in snap kchecks judge_submit judge_collect weekly_report alert_flush; do cp ~/.hermes/evals/cron/eval_$n.sh ~/.hermes/profiles/reviewer-bot/scripts/; done
ls -l ~/.hermes/profiles/reviewer-bot/scripts/eval_*.sh   # 6개, -rwxr-xr-x
```
2. cron을 등록한다. 저장소는 프로필마다 따로다(`~/.hermes/profiles/reviewer-bot/cron/jobs.json`, `cron/jobs.py:85-95`). `--no-agent`이면 스크립트 stdout이 그대로 알림이 되고 stdout이 비면 조용하다(`hermes_cli/subcommands/cron.py:58-66`, `cron/scheduler.py:1504-1553`). `<알림 대상>`은 기존 `no_agent` 작업과 같은 값을 쓴다(`hermes -p reviewer-bot cron list`로 `deliver` 확인).
   - **알림이 가는 작업은 주간 보고와 `eval-alert-flush`(야간 실패 보류분 방출) 둘뿐이다.** `eval-snap`·`eval-kchecks`·`eval-judge-submit`·`eval-judge-collect`는 정상 실행에도 요약을 stdout에 쓰고(매시 수거 요약, 2분마다 스냅샷 줄 등), `touch STOP` 중에는 판정 래퍼 둘이 `STOP`을 stdout에 쓴다. 이대로 `--deliver "$D"`로 걸면 23~09시를 포함해 밤낮없이 Discord로 간다. 그래서 이 4개는 `--deliver local --failure-deliver "$D"`로 건다: 성공 실행의 stdout은 알림 대신 `~/.hermes/profiles/reviewer-bot/cron/output/<job_id>/<시각>.md`에만 남고(`cron/scheduler.py:3067-3073`, `cron/jobs.py:3353-3364`; 작업마다 기본 최근 50개만 보관, `cron/jobs.py:3323-3328`), 실패(0이 아닌 종료)만 `$D`로 간다(`cron/scheduler_delivery.py:863-882`, `hermes_cli/subcommands/cron.py:44-53`).
   - 주간 보고는 `--deliver "$D"`다. 알림은 보고서가 `quiet_hours.emit()`으로 내므로 23~09시에는 보류된다.
   - 실패 알림도 23~09시에는 가지 않는다: 4개 작업 래퍼가 그 시간의 실패를 `quiet_hours.emit()`으로 보류하고 종료 코드 0으로 끝난다(cron 실패 알림은 `quiet_hours`를 거치지 않기 때문, `cron/scheduler.py:1535-1542`). 보류분은 `eval-alert-flush`(매일 09:05, `--deliver "$D"`)가 한 번에 낸다. 보류는 30건까지이고 넘은 건수는 방출 때 한 줄로 적힌다. `quiet_hours.py`를 읽지 못하면 래퍼는 종료 코드를 그대로 낸다(알림을 잃지 않는 쪽).
```bash
D="<알림 대상>"
hermes -p reviewer-bot cron create "every 2m"   --name eval-snap          --script eval_snap.sh          --no-agent --deliver local --failure-deliver "$D" --timezone Asia/Seoul
hermes -p reviewer-bot cron create "30 4 * * *" --name eval-kchecks       --script eval_kchecks.sh       --no-agent --deliver local --failure-deliver "$D" --timezone Asia/Seoul
hermes -p reviewer-bot cron create "0 3 * * *"  --name eval-judge-submit  --script eval_judge_submit.sh  --no-agent --deliver local --failure-deliver "$D" --timezone Asia/Seoul   # 보정 통과 뒤에만
hermes -p reviewer-bot cron create "0 * * * *"  --name eval-judge-collect --script eval_judge_collect.sh --no-agent --deliver local --failure-deliver "$D" --timezone Asia/Seoul
hermes -p reviewer-bot cron create "40 9 * * 1" --name eval-weekly-report --script eval_weekly_report.sh --no-agent --deliver "$D" --timezone Asia/Seoul
hermes -p reviewer-bot cron create "5 9 * * *"  --name eval-alert-flush   --script eval_alert_flush.sh   --no-agent --deliver "$D" --timezone Asia/Seoul
```
3. 확인한다. 등록 직후 `next_run_at`이 채워지고(`cron/jobs.py:1914-1921`), 첫 실행 뒤 `last_run_at`·`last_status`가 적힌다(`cron/jobs.py:2398-2404`). 마지막 실행·다음 실행은 주간 보고 사용량 절의 "평가 cron" 표에도 나온다.
```bash
hermes -p reviewer-bot cron list | grep -c 'Name: *eval-'   # 활성화 날 5(eval-judge-submit 제외), 보정 통과 뒤 6. 기존 작업 9개는 그대로
hermes -p reviewer-bot cron runs <eval-snap의 job_id> --limit 3   # 3분 안에 첫 실행 기록 (job_id는 list에서 복사)
```
4. `next_run_at`이 비거나 첫 실행 기록이 생기지 않을 때만 R3 5번(워커 0 확인)을 한 뒤 사용자가 `hermes gateway restart`를 한다. cron ticker는 60초마다 돌고(`cron/jobs.py:105`) 매 tick이 `jobs.json`을 다시 읽으므로(`cron/jobs.py:1377, 2868`) 정상이면 재시작이 필요 없다.

일정 문법 근거: `"every 2m"`은 2분 interval, 5칸 식(`"30 4 * * *"`)은 cron, 요일·시각 문구(`"every monday 9:40am"`)도 같은 cron으로 풀린다(`cron/jobs.py:787-852`, 소스 함수를 직접 불러 확인). 정각 매시는 `"0 * * * *"`다. 6개를 한 번에 등록하지 않아도 된다: `eval-snap`과 `eval-kchecks`는 C6 승인 직후, `eval-judge-submit`은 보정 통과 뒤, `eval-weekly-report`는 C10 승인 뒤가 09 §7의 순서다.

### 12.3 멈춤

- LLM 구성요소만 즉시 0으로: `touch ~/.hermes/evals/STOP`. J1·J2 제출·수거, C 묶음, J3가 클라이언트·subprocess·장부 0으로 끝난다. A·B0·B(i)·주간 보고는 계속 돈다. 풀기: `rm ~/.hermes/evals/STOP`. STOP 중 `eval-judge-submit`·`eval-judge-collect` 래퍼는 종료 코드 0으로 끝나며 stdout에 `STOP`을 쓰지만, 두 작업은 `--deliver local`이라 Discord로 가지 않는다(12.2).
- cron 전체: `hermes -p reviewer-bot cron pause <job_id>` / `resume <job_id>` (`<job_id>`는 `cron list`).
- 429·overloaded: 그 실행이 종료 코드 3으로 멈추고 남은 일은 다음 주기에 다시 돈다. 0이 아닌 종료는 cron이 오류 알림으로 `$D`에 보낸다(`cron/scheduler.py:1505`). 23~09시의 실패는 보류됐다가 09:05 `eval-alert-flush`가 낸다(12.2). 주간 보고 사용량 절의 "그 주 halt" 횟수와 맞추어 본다.

### 12.4 비용

- 콘솔 월 상한 **$200**(사용자가 콘솔에서 설정), 내부 안전선 **$180**(상한 × `soft_stop_ratio` 0.9, `~/.hermes/evals/evals.yaml`). 월 누적 + 예상 비용이 안전선을 넘으면 새 제출을 다음 순서로 줄인다: C 남은 시행 → J1 표본 100 → 50 → 0 → J2. A·B0·B(i)·보고는 사용량이 0이라 멈추지 않는다.
- 장부 `~/.hermes/evals/ledger.jsonl`은 SDK 응답의 실제 usage를 적는다. Sonnet 5.5 단가는 가정값이라 줄마다 `cost_basis: assumed`로 남고, 주간 보고가 그 금액 비율을 적는다. 단가표에 없는 모델은 `unknown_price`(비용 0)로 적히고 보고서가 줄 수를 따로 적는다.
- 월 $ 누적과 $200 대비 %는 주간 보고 `## 사용량·상한`에서 본다. 달 경계는 KST다.

### 12.5 평가 키

- 키는 `~/.hermes/evals/.env`의 `HERMES_EVAL_ANTHROPIC_API_KEY`에만 둔다(권한 600). 봇용 `~/.hermes/.env`와 섞지 않고, 이 파일을 열어 값을 보거나 채팅에 적지 않는다.
- 점검: `~/.hermes/hermes-agent/venv/bin/python ~/.hermes/evals/bin/check_key.py` (형식, 봇 키와 다른 키인지, 모델 3종 조회, 최소 호출 1회).

### 12.6 보정 (판정기 J1·J2)

- 주기: 첫 보정은 B0 스냅샷을 켠 지 2주 뒤, 이후 8주마다와 판정 모델·루브릭을 바꿀 때. 매월 무작위 10건을 사용자가 다시 판정해 합의율이 기준 아래로 떨어지면 즉시 다시 한다.
- 합격 기준과 사람 몫은 09 §5.5(회당 약 45분). 순서는 `eval_calib.py` 하위 명령 기준이다.
```bash
python3 ~/.hermes/evals/bin/eval_calib.py extract --kind j1 --until <KST 시각> --seed <N> --out <labels.csv>   # j2도 같다
#  → reviewer가 prelabel_reviewer 열을 채운다
python3 ~/.hermes/evals/bin/eval_calib.py plan --kind j1 --labels <labels.csv> --models claude-opus-5-5,claude-sonnet-5-5 --repeats 2 --dry-run   # 개수·예상 비용만
#  → 판정 실행(reviewer, 사용자 승인 뒤)이 judge 열을 채운다. J1은 opus·sonnet 둘 다 돌린다
python3 ~/.hermes/evals/bin/eval_calib.py review-list --labels <labels.csv> --seed <N> --out <review.csv>      # 판정기와 어긋난 것 전부 + 무작위 20건
#  → 사용자가 label_user 열을 채운다
python3 ~/.hermes/evals/bin/eval_calib.py metrics --kind j1 --labels <labels.csv> --model <모델> --json        # 합격 판정
```
- `review-list`는 judge 열이 채워진 뒤에 부른다. 비어 있으면 전부 어긋난 것으로 세어 전체가 사용자에게 간다(`eval_calib.py` `user_review_list`).
- J1 모델은 두 모델의 `metrics` 결과를 `choose_j1_model`(`eval_calib.py:506`: 합격한 쪽 중 합의율이 높은 쪽, 차이 0.005 미만이면 sonnet)로 정해 `evals.yaml`의 `j1_model`에 적는다.
- **상태 파일은 사람이 쓴다**(도구가 쓰지 않는다): `metrics`가 합격이면 `~/.hermes/evals/b/calib/j1_status.json`을 `{"pass": true, "model": "<모델>", "checked_at": "<KST 시각>"}`로 만든다(J2는 `j2_status.json`). 주간 보고는 `pass`가 JSON `true`일 때만 "보정 통과"로 읽고, 그 밖(파일 없음·`false`·문자열)은 절 첫 줄에 `미보정 — 판정·결정에 쓰지 않는다`를 붙인다.

### 12.7 변경 기록부 (`~/.hermes/evals/changes.yaml`)

- 쓰는 사람: 설정을 바꾼 사람(사용자 또는 바꾼 작업을 한 봇). 쓰는 때: **바꾼 날 같은 날**. 시간 비교의 창을 이 기록으로 자르므로 빠지면 앞뒤 창에 다른 변경이 섞인다.
- 항목 칸: `at`(ISO 8601, `+09:00` 필수, 시각 오름차순), `profile`(`coder-bot`·`reviewer-bot`·`helper-bot`·`fable-bot`·`all`), `kind`(`effort`·`model`·`soul`·`skill`·`plugin`·`guard`·`rule`·`hermes`), `note`, `ref`(결정 번호 또는 카드).
- 쓴 뒤 검사: `python3 ~/hermes-ops/scripts/eval_compare.py --validate-changes ~/.hermes/evals/changes.yaml` (오류 0이어야 한다).
- 주간 보고 A 절은 뒤 창(변경 + 14일)이 그 주에 끝나는 변경마다 층화 비교(Δ·90% CI·판정)를 싣는다. 단순 Δ는 참고로만 적힌다.

### 12.8 C 스킬 효과 실행

- 대상: 봇 × 스킬 중 실사용 로드율(K5, 지난 4주)이 **10% 이상이고 맞는 세션이 20개 이상**인 쌍만(09 §5.7.2). 나머지는 "판정 불가(로드율)".
- 순서: 그 봇의 **A/A(ON vs ON) 48시행을 먼저** 한 번 돌려 잡음 폭을 잰다(모델·SOUL·effort가 바뀔 때마다 다시). 그다음 ON/OFF 48시행(문제 8 × 3회 × 2).
```bash
~/.hermes/hermes-agent/venv/bin/python ~/.hermes/evals/bin/eval_c_run.py --bot <봇> --skill <스킬> --arms on,on --reps 3 --dry-run   # 계획만(쓰기 0)
~/.hermes/hermes-agent/venv/bin/python ~/.hermes/evals/bin/eval_c_run.py --bot <봇> --skill <스킬> --arms on,on --reps 3            # A/A
~/.hermes/hermes-agent/venv/bin/python ~/.hermes/evals/bin/eval_c_run.py --bot <봇> --skill <스킬> --arms on,off --reps 3           # ON/OFF
# 두 묶음이 끝난 뒤: 보고서 파일을 만든다(각 묶음이 끝에 `결과 <경로>/trials.jsonl`을 찍는다). stdlib만 쓰므로 인터프리터는 이것이다.
R=~/.hermes/evals/c/results
/opt/anaconda3/bin/python3 ~/.hermes/evals/bin/eval_c_report.py --trials $R/<ON/OFF run_id>/trials.jsonl --aa $R/<A/A run_id>/trials.jsonl \
  --load-rate <K5 로드율> --n-sessions <K5 대상 세션 수> --json > $R/<ON/OFF run_id>/report.json
```
- `eval_c_run.py`는 `trials.jsonl`·`summary.json`·`rerun.jsonl`만 쓰고 `report.json`을 만들지 않는다. `eval_c_report.py`는 결과를 stdout으로만 내므로 위 마지막 줄의 `> report.json`이 그 파일을 만든다. 주간 보고 C 절은 `c/results/*/report.json`만 읽으므로 이 단계를 하지 않으면 C 절이 `데이터 없음(미활성)`으로 남는다. 봇 이름은 같은 폴더의 `summary.json`에서, 스킬 이름은 `trials.jsonl`에서 읽는다.
- `--load-rate`·`--n-sessions`는 `eval_kchecks.py`의 K5(실사용 로드율·맞는 세션 수, 주간 보고 B(i) 절 K5 표의 `로드율`과 `로드/대상`의 대상 수)다. 이 단계가 실패하면(종료 코드 2) 빈 `report.json`이 남으니 지우고 다시 한다(C 절에는 `읽지 못함`으로 나온다).
- 병렬 1. 실행 중인 kanban 워커가 있으면 기다린다(대기 규칙은 `eval_guard.py`, C에만 적용). `STOP` 파일이면 시작하지 않는다.
- 묶음을 돌리는 동안에는 `pytest`를 돌리지 않는다. 시작 전 `ls -A /tmp/evals/c "$TMPDIR/evals/c" "$(getconf DARWIN_USER_TEMP_DIR)evals/c"`가 모두 비어 있고 `launchctl list | grep -c 'com\.nousresearch\.hermes\.runtime\.'`가 0인지 본다(실행기도 같은 위치와 런타임 라벨을 보고, 남은 것이 있으면 종료 코드 4로 시작하지 않는다). 실행기는 시행마다 그 시행 홈의 런타임 게이트웨이를 멈추고(`gateway.pid` 확인 → SIGTERM, 20초 뒤 SIGKILL), 그 홈을 가리키는 런타임 라벨을 `launchctl remove`로 지운 뒤 시행 폴더를 지운다(최대 5회). 하나라도 실패하면 종료 코드 4로 멈춘다. `hermes gateway stop`은 쓰지 않는다(시행 홈만 멈춘다는 보장이 없다, `hermes_cli/gateway.py:5320-5367`).
- 결과는 `~/.hermes/evals/c/results/<run_id>/`(`trials.jsonl`, `summary.json`, `rerun.jsonl`)에 남고, `report.json`은 위 `eval_c_report.py --json` 단계가 ON/OFF 폴더에 만든다. 시행마다 `state.db`와 작업 폴더가 쌓이므로 용량을 한 번 잰 뒤 이 절에 적는다. 판정표(09 §5.7.6): 유지 = Δ ≥ max(0.10, 2 × 잡음 폭)이고 CI 하한 > 0 / 해로움 = CI 상한 < 0 / 효과 없음 = Δ ≤ 0.02이고 CI 상한 < 0.10 → 보관 후보 / 그 밖 = 보류(문제 4개를 더하거나 반복 5회로 한 번 더). 조치는 모두 사용자가 정한다.
- `skill_trigger_eval.py`(새 판)는 `~/.hermes/evals/bin/`에 있고 결과를 `~/.hermes/evals/trigger/<시각>.jsonl`에 쓴다. 원본은 `~/.hermes/hooks/`에 그대로 두고 고치지 않는다.

### 12.9 E (축소 벤치) 승인 절차

E는 기본 운영에 넣지 않는다. 쓰는 때: 모델·provider 교체, 에이전트 루프를 바꾼 Hermes 업데이트, A가 같은 프로젝트에서 연속 두 번 "악화"인데 B로 원인을 못 찾음, SOUL을 30% 넘게 고침. 절차: ① reviewer가 조건·가설·arm·예산·시간대를 적은 카드 초안을 올린다 → ② 사용자가 **"E 실행 승인"**이라고 명시한다 → ③ coder 카드로 벤치를 만든다 → ④ 실시간 시험이 없는 기간에 실행한다. 한 번에 coder 런 20회(약 $13 추정), 같은 월 $200 상한 안이다. 승인 없이는 만들지도 돌리지도 않는다.

### 12.9b 가드·플러그인 로그 위치 (11-25 실측)

봇 여러 개를 게이트웨이 프로세스 하나가 돌리면(multiplex) Discord·데스크톱 턴의 env `HERMES_HOME`은 기본 홈이다. 그래서 `HERMES_HOME`으로 경로를 정하는 플러그인 로그는 두 곳에 나뉜다.

| 경로 | 로그 위치 |
|---|---|
| kanban 워커(프로필별 하위 프로세스) | `~/.hermes/profiles/<봇>/logs/<이름>.jsonl` |
| 게이트웨이 턴(Discord·데스크톱) | `~/.hermes/logs/<이름>.jsonl` |

warn 판정·주간 집계는 두 곳을 합쳐 센다. 같은 이유로 `<HERMES_HOME>/state.db`를 여는 보조 조회는 게이트웨이 턴에서 기본 DB를 연다 — enforce 전에 프로필을 인식하는 경로로 고친다. role-guard의 terminal 행은 쓰기 패턴(`sed -i`·`tee `·`cat >`·`git apply`·`git commit`)이 있을 때만 남는다(읽기 명령은 0행이 정상).

### 12.10 데이터 위치·보관 (`~/.hermes/evals/`)

| 위치 | 내용 | 보관 |
|---|---|---|
| `snap/` | B0 스냅샷(런별 폴더) | 90일, 합계 2GB 초과 시 오래된 것부터 지움 |
| `b/` | `k_checks.jsonl`(창별로 쌓임, 35일 보관), `j1/<주>.jsonl`, `j2/<주>.jsonl`, `calib/`, 배치 상태 파일 | 지우지 않는다 |
| `reports/` | 주간 보고 `<주>.md` | 지우지 않는다 |
| `ledger.jsonl` | 평가 LLM 호출 장부(월 누적의 원본) | 지우지 않는다 |
| `c/` | `problems/`, `keys/`(작업 폴더 밖 정답), `results/<run_id>/` | 결과는 시행 폴더 누적 용량을 보고 정한다 |
| `trigger/` | 스킬 트리거 회귀 결과 | 지우지 않는다 |
| `changes.yaml`, `evals.yaml`, `prices.yaml` | 변경 기록부, 평가 설정(상한·모델), 단가표 | 사람이 고친다 |
