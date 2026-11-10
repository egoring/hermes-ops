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
- 추천이 엉뚱하면 `--explain`으로 걸린 단어를 보고 훅의 `STOP`/`GENERIC` 목록이나 hermes-hub `skill-search.ts` 동의어를 고친다.
