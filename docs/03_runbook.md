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

## R3. Hermes 업데이트 후

`hermes update` / `gateway start` / `gateway install` 은 plist를 다시 만든다.

| 순서 | 확인 |
|---|---|
| 1 | `grep -c osascript ~/Library/LaunchAgents/ai.hermes.gateway.plist` → 1 이상이면 래퍼가 돌아온 것 |
| 2 | (승인) 래퍼 재제거: 백업 `ai.hermes.gateway.plist.bak_osascript_20260925_2232` 와 새 plist를 diff 해서 `ProgramArguments`만 옮긴다(새 plist의 다른 변경은 유지). `launchctl bootout gui/$(id -u)/ai.hermes.gateway && launchctl bootstrap gui/$(id -u) <plist>` |
| 3 | 봇 3개 connected, CPU 확인 `ps -o pid,%cpu,command -ax \| grep -i "hermes.*gateway" \| grep -v grep` |
| 4 | 모델 ID가 새 카탈로그에 있는지 (`R2` 1번 명령) |
| 5 | 행동 테스트 T3·T5·T6 |
| 6 | kanban 도구·CLI 옵션 변화: `hermes kanban create --help` 를 이전과 비교 |

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
| 리소스 감시 / 사용량 보고 | 09·21시 / 09시 | `resource_alert.py` / `usage_report.py` | 기존 |

전송은 공용 `_notify.py`(helper-bot 계정, 알림 채널). 복원: `hermes import ~/.hermes-backups/<zip>`.
테스트: `kanban_watch.py --dry-run --since-id <과거 id>` / `weekly_metrics.py --dry-run`.
