## 진행 방식
1. 스펙을 재해석하지 말고 그대로 구현한다. 스펙이 모순되거나 실행할 수 없으면 `kanban_block`을 쓴다. 이 카드에서 block은 최대 1번이다. 기다려야 하면 `kanban_schedule(reason="SCHEDULED_UNTIL=<ISO8601> | <무엇을 기다리는지>")`를 쓴다.
2. 체크리스트 항목을 하나 끝낼 때마다 `kanban_heartbeat` note에 `진행 k/N: <끝낸 항목>`을 남긴다.
3. 끝나면 `hermes kanban --board <board> request-review <id> --reviewer reviewer-bot --summary "변경 파일 / 검증 / 기준별 수치"`를 호출한다.
   - **`--reviewer reviewer-bot`은 필수다.**
   - 반려되면 고친 뒤 같은 플래그로 다시 request-review한다(최대 3회).
4. 런을 끝내기 전에 complete / request_review / block / schedule 중 하나를 반드시 호출한다.
5. 금지: Hermes 파일·DB 쓰기, gateway 재시작, push(별도 카드에서만).
   - 테스트용 파일은 `$TMPDIR`나 pytest tmp_path에만 둔다(`~/.hermes` 아래 금지).
   - 배포가 있으면 이전 태그와 롤백 명령을 기록한다.
   - 커밋은 1개만 하고, 커밋 후 `git status --porcelain`이 0줄이어야 한다.

<!-- 리뷰 없는 helper-bot 카드는 3번 대신 "kanban_complete로 끝냄, 사전 확인이 하나라도 실패하면 kanban_block"으로 바꾼다. -->
