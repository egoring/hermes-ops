# hermes-ops

[Hermes Agent](https://github.com/NousResearch/hermes-agent) 하나로 Discord 봇 4개(설계·리뷰 / 구현 / 보조 / 최종점검)를 역할별 모델로 돌리고, kanban 보드로 "설계 → 구현 → 리뷰" 왕복을 자동화한 개인 운영 기록이다. 프로젝트와 무관한 운영 구조만 여기 둔다.

> Personal ops notes (Korean) for running four role-split Hermes Agent Discord bots — Opus for design/review, Sonnet for implementation, Haiku for light work, Fable for independent final checks — sharing one multiplexed gateway, with a kanban design→implement→review loop. Includes the SOUL.md role prompts, the custom skills the bots accumulated, a kanban metrics script, and upstream bug reports found along the way.

**그대로 쓰는 템플릿이 아니다.** 설정값·수치는 2026-09 기준 한 사람의 환경(macOS, Hermes v0.21.4)에서 확인한 것이다. 가져다 쓸 땐 `docs/01_운영구조.md`의 구조와 `docs/05_결정기록.md`의 이유를 보고 자기 환경에서 다시 확인할 것.

| 먼저 볼 것 | |
|---|---|
| 구조 한눈에 | `docs/01_운영구조.md` §1~§2 (mermaid 그림) |
| 왜 이렇게 했나 | `docs/05_결정기록.md` |
| 실제로 무슨 문제가 있었나 | `docs/06_이슈.md`, `docs/04_운영지표.md` §3 |
| 봇 역할 프롬프트 | `souls/` |
| 최종점검 (fable-bot) | `docs/07_최종점검.md` |

| 문서 | 내용 | 언제 보나 |
|---|---|---|
| `docs/01_운영구조.md` | 봇·런타임·설정·규칙 층·파이프라인·검증 | 구조를 이해/변경할 때 |
| `docs/02_프로젝트_연결.md` | 새 프로젝트 붙이기, cwd 선택지, AGENTS 템플릿 | 프로젝트 추가·전환 |
| `docs/03_runbook.md` | 정기 점검, 모델 교체, 업데이트 후, 규칙 수정, 태스크 이상, 되돌리기 | 작업할 때 체크리스트 |
| `docs/04_운영지표.md` | 지표 정의, 기준선, 기록표 | 주간 점검 |
| `docs/05_결정기록.md` | 왜 이 구조인가 (D1~) | 구조를 바꾸고 싶을 때 |
| `docs/06_이슈.md` | 미해결 이슈 | 점검·장애 |
| `docs/07_최종점검.md` | 최종점검을 fable-bot(Fable 5.1)이 맡는 구조, 흐름, 보고서 형식, 검증 | 제출·배포 전 |
| `projects/example.md` | 프로젝트 연결 정보 양식. 실제 `projects/<이름>.md`는 **로컬 전용** (`.gitignore`) | 프로젝트 추가 |
| `issue_drafts/` | Hermes upstream 제보 원문 (#127651, #127652 제출됨) | 제보할 때 |
| `scripts/kanban_set_effort.py` | 태스크 하나의 추론 강도 지정/해제 (CLI에 없는 기능) | 특정 태스크 추론 강도 조정 (최종점검은 fable-bot으로 이전) |
| `scripts/kanban_metrics.py` | 보드 지표 (읽기 전용) | `python3 scripts/kanban_metrics.py --days 7` |
| `skills/` | 운영용 자작 스킬 스냅샷 (원본은 `~/.hermes`) | 백업·다른 PC 이전 |
| `souls/` | 봇 4개 SOUL.md 스냅샷 (개인 ID는 자리표시자로 치환) | 역할 규칙 원문 확인 |
| `scripts/sync_skills.py` | 스킬·SOUL 복사 + ID 치환 + 공개 보류 처리 + 저장소 전체 개인정보 검사 | 스킬이 바뀐 뒤 커밋 전 |

## 스킬·SOUL 동기화

원본은 항상 `~/.hermes` 쪽이다(Hermes가 스킬을 계속 고친다). 저장소는 스냅샷이다.

```bash
python3 scripts/sync_skills.py   # 복사 + 검사. exit 1이면 커밋하지 않는다
git add -A && git commit -m "skills sync" && git push
```

| 저장소 경로 | 원본 | 용도 |
|---|---|---|
| `skills/default/hermes-multi-profile-bot-fleet` | `~/.hermes/skills/devops/…` | 봇 fleet 운영 전반 (게이트웨이, 리뷰 루프, 알림) |
| `skills/reviewer-bot/kanban-*` (4개) | `profiles/reviewer-bot/skills/…` | 태스크 위임·검증 분석·오케스트레이션 |
| `skills/coder-bot/shared-thread-scope-discipline` | `profiles/coder-bot/skills/…` | 공유 스레드에서 남의 일 안 가져가기 |

SOUL은 복사할 때 `<@USER_ID>`, `<ID>`, `<USER_NAME>`으로 바뀐다 (원본은 그대로). 추가 치환어·금지어·공개용 문구 치환은 git에서 제외된 `scripts/redact_local.txt`, `scripts/pii_local.txt`, `scripts/public_subs_local.txt`에 둔다. **저장소의 SOUL을 원본에 다시 복사하지 말 것** (알림이 깨진다).

특정 프로젝트 전용 스킬과 Hermes 기본·허브 스킬은 넣지 않는다. 진행 중인 프로젝트 사례가 많은 파일은 `WITHHOLD`로 안내문만 올라간다(프로젝트 종료 후 해제). 다른 PC로 옮길 땐 각 폴더를 원본 경로에 복사한다.

규칙 파일 자체(SOUL.md, AGENTS.md)는 각 위치에 있고, 이 문서들은 그것을 요약·설명한다. 충돌하면 규칙 파일이 맞다.

날짜별 변경 기록(`docs/변경이력.md`)은 백업 경로가 들어 있어 로컬에만 둔다.

## License

MIT — `LICENSE`.
