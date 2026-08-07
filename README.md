# hybrid-orch-engine (폐기됨)

Hermes Agent에 상태 기반 오케스트레이션 + 작업 완료 알림 + 목표 추적을 붙이려던 프로젝트.
**Hermes v0.20.0 기준으로 전부 내장 기능에 포함되어 있어 코드를 전량 삭제했습니다.**

원본 코드는 git 히스토리에 남아 있습니다 (`git show 647b8fc`).

## 무엇이 무엇으로 대체되었나

| 삭제된 것 | 대체 |
|---|---|
| `scripts/core_engine.py` (매크로 스텝 루프) | Hermes 에이전트 루프 + `/goal` |
| `scripts/orchestrator_utils.py` (JSON 상태 저장) | `state.db` — SQLite, atomic write, 경합 처리 |
| `scripts/workers/fetcher.py` | 내장 `web_search` / 브라우저 자동화 도구 |
| `scripts/workers/analyzer.py` (LLM 호출이 mock이었음) | 에이전트 턴 그 자체 |
| `scripts/workers/summarizer.py` | 에이전트 턴 그 자체 |
| `state/project_status.json` | `SessionDB.state_meta` |
| `state/scenarios/audit_v1.json` | `/goal` 또는 kanban 카드 |
| `docs/orchestration_protocol.md` (상태 전이 규칙) | `/goal` judge 루프 |

## 대체 사용법

**목표 추적** — 세션이 끊겨도 유지됨. judge가 매 턴 완료 여부 판정, 기본 20턴 예산.

```
/goal <목표>            # 설정 + 즉시 첫 턴 시작
/goal draft <목표>      # 완료 조건을 구조화해서 작성
/goal show | pause | resume | clear
```

본문에 **명시적 완료 조건**을 쓸수록 judge 판정이 정확해집니다.

**카드 단위 목표 루프**

```bash
hermes kanban create "<제목>" \
  --body "Acceptance: <완료 조건>" \
  --goal --goal-max-turns 15
```

**예약 실행 + 배달**

```bash
hermes cron create "every 2h" "<지시>" --deliver telegram
hermes cron create "30m" "<지시>"                    # 일회성
hermes cron create "every 5m" --no-agent --script <경로> --deliver telegram
hermes cron list / remove <name>
```

**텔레그램 선제 발송** — 텔레그램 채팅에서 `/sethome`. 또는 `TELEGRAM_HOME_CHANNEL=<chat_id>`.

**백그라운드 작업 완료 통보**

- `delegate_task(background=True)` — 핸들 즉시 반환, 완료 시 결과를 새 메시지로 자동 전달
- `terminal(background=True, notify_on_complete=True)` — 세션 종료/재시작에도 살아남음

**이벤트 훅** — `~/.hermes/config.yaml`

```yaml
hooks:
  outbound:
    - name: tg-notify
      url: <webhook-url>
      events: [subagent_stop, on_session_end]
      timeout: 10
```

이벤트: `pre_tool_call`, `post_tool_call`, `pre_llm_call`, `post_llm_call`,
`on_session_start`, `on_session_end`, `subagent_start`, `subagent_stop`

## 검증 결과 (2026-08-07)

삭제가 안전한지 실제로 테스트함. 전부 통과 — 자체 엔진 불필요 확정.

| 테스트 | 내용 | 결과 |
|---|---|---|
| A1 | `terminal(background=True, notify_on_complete=True)` 정상 종료 | ✅ 자동 통보 도착 |
| A2 | 같은 방식 비정상 종료(`exit 1`) | ✅ 종료 코드 포함해서 통보 (성공만 알리는 게 아님) |
| B | `/goal`로 3단계 작업 + 명시적 Acceptance 조건 | ✅ 조건 충족 확인 후 자동 완료·클리어 |

**근본 원인**: 원래 "알림이 안 온다"고 느꼈던 원인은 Hermes가 아니라 `core_engine.py`의 버그였음.
`run_orchestration()`이 `self.state`를 메모리에 한 번만 로드하고 이후 갱신하지 않아 종료 조건이
never true가 되는 무한루프. `notify_on_complete=true`가 프로세스 **종료 시점**에 발화하는데
프로세스가 종료된 적이 없어서 알림도 없었음 (커밋 `5102326` 참고).

**B 테스트로 밝혀진 부수 사항**: judge는 지시문 전체가 아니라 **Acceptance 줄만** 판정 기준으로
삼음. "각각 다른 턴에" 같은 부가 지시는 강제되지 않았음 — Acceptance는 반드시 최종 상태 검증
가능한 조건으로만 쓸 것.

**하드웨어 관련 발견**: `llama-server --parallel 1` — 동시 요청 1개로 고정되어 있어 여러
서브에이전트/cron을 동시에 돌려도 물리적으로 직렬화됨. 병렬 처리가 필요하면 `--parallel` 상향 +
`-c` 재분배가 필요하나 12GB VRAM + 128K 컨텍스트 조합에선 여유가 크지 않음.

## 남는 갭

Hermes가 띄우지 않은 외부 프로세스는 추적 불가. 엔진이 아니라 한 줄로 해결:

```bash
<작업>; curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  -d chat_id="${TELEGRAM_HOME_CHANNEL}" -d text="done: $?"
```

## 환경

WSL2 / Hermes Agent v0.20.0 / gemma-4-12b-it-qat-q4_0 (llama-server, `--parallel 1`) / RTX 4070 12GB.

로컬 12B는 tool calling과 judge 판정 정확도가 프론티어 모델보다 낮습니다.
`/goal`이나 `delegate_task`가 불안정하면 엔진 문제가 아니라 모델 능력 문제일 수 있으므로,
`hermes model`로 해당 역할만 원격 API로 돌려서 원인을 분리할 것.
