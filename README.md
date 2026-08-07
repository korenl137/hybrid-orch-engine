# Hermes Agent 자동화 사용법 (이 환경 기준)

이 레포는 원래 Hermes Agent에 붙일 자체 오케스트레이션 엔진이었습니다. 실제로 테스트해보니
필요한 기능(작업 완료 알림, 목표 추적, 예약 실행)이 Hermes 내장 기능만으로 자연어 그대로
작동한다는 게 확인돼서 엔진 코드는 전량 삭제했습니다 (`git show 647b8fc`에 원본 남아있음).

지금부터는 **"이 환경에서 무슨 말을 하면 무슨 일이 일어나는지"를 실측한 사용설명서**입니다.
전부 아래 환경에서 직접 텔레그램으로 테스트하고 로그로 검증했습니다. 굵게 표시 안 된 서술은
공식 동작, `(실측)` 표시는 이 환경에서 직접 재현·확인한 것입니다.

**환경**: WSL2 / Hermes Agent v0.20.0 / gemma-4-12b-it-qat-q4_0 (llama-server, `--parallel 1`,
`-c 131072`, `--repeat-penalty 1.1`) / RTX 4070 12GB / 텔레그램 게이트웨이.

**빠른 참조** — 하고 싶은 일 → 어디를 볼지:

| 하고 싶은 일 | 섹션 |
|---|---|
| 백그라운드 작업 끝나면 알림 받기 | 1 |
| 예약/반복 알림 (cron) | 2 |
| 며칠 걸리는 목표를 맡겨두기 | 3 |
| Hermes가 먼저 말 걸게 하기 | 4 |
| 게이트웨이/모델이 멈췄을 때 | 5 |
| 결과물을 어디에 저장할지 | 6 |

---

## 1. 백그라운드 작업 완료 알림

도구 이름이나 파라미터를 몰라도 됩니다. 그냥 시키면 됩니다.

> 터미널에서 `<명령어>` 좀 돌려줘. 끝나면 알려주고, 안 기다려도 돼.

Hermes가 알아서 `background=True` + `notify_on_complete=True`를 선택하고, 응답은 즉시 오며,
작업이 끝나면 **성공이든 실패든** 새 메시지로 자동 통보됩니다(실패 시 종료 코드 포함).
리서치처럼 LLM이 필요한 작업은 `delegate_task`로 위임해도 동일합니다. `(실측)`

**동시 실행 시 주의**: 셸 명령은 OS 프로세스라 여러 개를 동시에 시켜도 진짜 병렬로 돕니다.
반면 **모델 추론이 필요한 작업(리서치·분석·delegate_task)은 `--parallel 1` 때문에 한 슬롯을
두고 줄을 섭니다** — "동시에 끝난다"가 아니라 "총 소요시간이 대략 합산된다"고 예상할 것.
결과가 섞이는 일은 없습니다(귀속은 정확). `(실측)`

**Hermes가 띄우지 않은 외부 프로세스는 추적 대상이 아닙니다.** WSL에서 직접 `nohup`으로
뭔가 돌리셨다면 Hermes는 알 방법이 없습니다. 명령 끝에 직접 붙이세요:
```bash
<작업>; curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  -d chat_id="${TELEGRAM_HOME_CHANNEL}" -d text="done: $?"
```

---

## 2. 예약 실행 / 반복 작업 (cron)

"cron"이라는 단어 없이 말로 시켜도 job 생성과 배달 목적지 지정까지 정확히 동작합니다.

> 5분 뒤에 딱 한 번만 "○○" 라고 알려줘.
> 매일 아침 9시에 서버 상태 확인해서 알려줘.
> 2시간마다 뉴스 확인해서 요약해줘.

`(실측)` — Hermes가 자체 `cronjob` 도구로 job을 만들고, 만든 대화방(`origin`)으로 정확히
배달합니다.

**단순 일회성 리마인더는 자연어로 시켜도 `--no-agent`(LLM 판단 없이 스크립트 출력만 배달)로
유도하세요.** 판단·생성이 필요 없는 리마인더에 에이전트 모드를 쓰면 [SILENT] 오판으로 무음
스킵될 수 있습니다(8번 참고). 텔레그램에서 그대로 시키면 됩니다:
```
1분 뒤에 "<메시지>"라고 딱 한 번 출력하는 스크립트를 ~/.hermes/scripts/ 에 만들고,
그걸로 no-agent cron job을 등록해줘.
```
`(실측)` Hermes가 스크립트 생성부터 등록까지 콘솔 없이 전부 처리합니다.

**CLI로 직접 관리:**
```bash
hermes cron create "every 2h" "<지시>" --deliver telegram:<chat_id>   # 에이전트 모드
hermes cron create "30m" "<지시>"                                     # 일회성, 에이전트 모드
hermes cron create "every 5m" --no-agent --script <이름> --deliver telegram  # LLM 없이 스크립트만
hermes cron list
hermes cron remove <name-or-id>
```
`--script`는 `~/.hermes/scripts/` 아래 경로만 받습니다. 대화창에서 "방금 만든 알림
취소해줘"라고 해도 됩니다. 일회성(`Repeat: 1/1`) job은 실행 후 `cron list`에서 자동으로
사라지는 게 정상입니다 — 목록에 없다고 실패한 게 아닙니다. `(실측)`

**주의**: 스케줄이 정각에 딱 맞지는 않습니다("1분 뒤"가 몇 초~몇십 초 늦게 옴 — 스케줄러 틱
간격 때문에 정상). cron 턴도 `--parallel 1` 슬롯을 공유하므로 다른 작업이 몰려 있으면
지연됩니다.

---

## 3. 장기 목표 추적 (`/goal`)

세션이 끊기거나 게이트웨이가 재시작돼도 살아남습니다. 매 턴마다 보조 judge가 완료 여부를
판정합니다.

```
/goal <목표>              # 설정 + 즉시 첫 턴 시작
/goal draft <목표>        # 완료 조건을 Hermes가 구조화해서 작성
/goal show                # 현재 상태·진행 턴 수 확인
/goal pause / resume      # 일시정지 / 재개
/goal clear                # 목표 제거
```

**Acceptance(완료 조건)는 반드시 최종 상태로 검증 가능한 문장으로 쓸 것:**
```
/goal <목표>
Acceptance: <완료 여부를 결과물만 보고 판단할 수 있는 조건>
```
judge는 **Acceptance 줄만** 판정 기준으로 삼습니다. "각 턴마다 하나씩" 같은 과정 지시는
강제되지 않고, 모델이 한 번에 몰아서 처리해도 Acceptance만 충족되면 완료 처리됩니다. `(실측)`

**함정 — `/goal resume`은 스스로 다음 턴을 진행하지 않습니다.** pause 상태에서 resume만
보내면 상태만 해제되고 실제 진행은 없습니다. 무인으로 돌리려면 pause 후 넛지가 주기적으로
필요합니다: `(실측)`
```
hermes cron create "10m" "진행 중인 목표 있으면 계속 진행해"
```

카드 단위로 격리하려면 kanban의 goal 모드도 같은 엔진을 씁니다:
```bash
hermes kanban create "<제목>" --body "Acceptance: <완료 조건>" --goal --goal-max-turns 15
```

---

## 4. 텔레그램에서 먼저 말 걸게 하기 (선제 발송)

cron·목표 완료 결과가 어디로 갈지는 "home channel"이 결정합니다.

- 텔레그램 채팅방에서 `/sethome` 한 번이면 그 방이 기본 목적지가 됩니다.
- 수동 설정: `~/.hermes/.env`의 `TELEGRAM_HOME_CHANNEL=<chat_id>` (그룹은 음수 ID, 개인 DM은
  본인 user ID와 동일).

---

## 5. 게이트웨이/모델이 멈췄을 때

**게이트웨이만 문제면 텔레그램에서 `/restart`.** 콘솔 불필요, in-flight 턴을 기다렸다가
우아하게 재기동합니다. `(실측)`

**`/restart`는 게이트웨이 프로세스만 재시작하고 llama-server(모델 서버)는 건드리지
않습니다** — 재시작 전후 llama-server PID 동일함을 확인. 둘은 완전히 별개 supervisor(게이트웨이
자체 vs systemd `llm@gemma4` 서비스)로 관리됩니다. `(실측)`

**llama-server 자체가 멈췄을 때(응답 없음, 슬롯이 계속 물려있음)는 `/restart`로 안 풀리고
콘솔이 필요합니다:**
```bash
pgrep -af llama-server
kill -9 <PID>
~/llm-stack/bin/llm-switch.sh use gemma4      # registry.yaml 기준으로 재기동
```
진행 중인 턴이 있으면 재시작이 그 턴이 끝날 때까지 기다립니다 — 폭주 중인 생성이 있으면
수 분~10분 걸릴 수 있습니다(7번 이슈 해결 후로는 재현 안 되고 있음). 오래 걸리면 재시작
명령만 취소하고 기다리면 대개 provider timeout이 정리합니다.

---

## 6. 어디에 무엇을 저장하는가

세 위치가 각자 다른 역할을 합니다. 헷갈리면 산출물이 `/tmp` 같은 임시 경로에 흩어집니다
`(실측)` — 지시 없이 `/goal`로 만든 파일들이 실제로 `/tmp`에 생겼고, 아래 `workspace/`는
만든 이후 한 번도 안 쓰였습니다.

| 위치 | 역할 |
|---|---|
| `~/.hermes/` | **Hermes 자신을 운영하는 데 필요한 것.** 설정(`config.yaml`, `.env`), 로그, 메모리, 세션, cron이 참조하는 스크립트(`scripts/`), 스킬(`skills/`), 훅(`hooks/`). |
| `~/hermes-agent-playbook/` (이 레포) | **Hermes *자체*에 대한 기록.** 사용법, 발견한 버그, 설정 튜닝 히스토리 — 이 문서. |
| `~/workspace/projects/<주제-slug>/` | **Hermes와 *함께* 만든 결과물.** 리서치, 분석, 코딩, 문서, 실험 기록 등. |
| `~/workspace/shared/` | 여러 프로젝트가 공유하는 자원. |
| `~/workspace/.venv` | Hermes가 Python 실행 시 기본으로 쓰는 uv 관리 가상환경. |

이 관례는 Hermes에게 자동 적용되지 않으므로 memory에 저장해뒀습니다(9번 참고).

---

## 7. 알려진 이슈

| # | 증상 | 상태 |
|---|---|---|
| 7.1 | 생성 폭주 (짧은 응답이면 되는데 수천 토큰씩 안 멈춤) | ✅ 해결됨 |
| 7.2 | 짧은 일회성 리마인더가 `[SILENT]`로 무음 스킵 | ⚠️ 우회됨 (2번 참고) |
| 7.3 | `/new` 후 텔레그램 "입력 중" 표시가 안 사라짐 | 재현됨, 기능 영향 없음 |

### 7.1 생성 폭주 — 해결됨

cron의 "1분 뒤 한 번만 알려줘"처럼 짧은 응답이면 충분한 프롬프트에서 모델이 멈추지 않고
계속 토큰을 생성. `/slots`에서 `n_decoded`가 18,927까지 올라간 채 진행 중이었음. 약 10분 후
provider timeout으로 자동 실패 처리되고 실패 알림도 정상 도착(조용히 씹히지 않음) — 하지만
`--parallel 1`이라 그 10분간 다른 모든 작업이 막힘.

**원인**: `--reasoning-format`이 gemma에 안 맞는 DeepSeek 파서를 강제한다는 초기 가설은
기각 — `llama-server --help` 확인 결과 기본값 `auto`가 reasoning 지원 템플릿에서 `deepseek`을
자동 선택하는 정상 동작이었음. 진짜 원인은 `--repeat-penalty`가 기본값 `1.00`(비활성)이었던
것 — 이례적 설정이 아니라 "아무것도 설정 안 한 상태"였고, 반복 억제가 없다 보니 특정
프롬프트가 우연히 모델을 못 빠져나오는 반복 루프로 몰아넣었음.

**수정** (`~/llm-stack/registry.yaml`, `models.gemma4.extra_flags`):
```
--jinja --flash-attn on -ngl 99 --parallel 1 --repeat-penalty 1.1
```
`~/llm-stack/bin/llm-switch.sh use gemma4`로 적용. **`registry/gemma4.env`를 직접 고치지
말 것** — 이 스크립트가 `registry.yaml`을 읽어 매번 재생성함.

**검증**: 동일 프롬프트로 재현 시도 → `n_decoded=696`에서 정상 종료, 폭주 재현 안 됨. `(실측)`

### 7.2 `[SILENT]` 오판 — 우회됨, cron 한정

cron job 시스템 프롬프트에 "알릴 필요 없으면 `[SILENT]`를 반환해 배달을 건너뛰라"는 지침이
있는 것으로 보임(왓치독용 기능으로 추정). 단순 일회성 리마인더에서 12B 모델이 이 지침을
과도하게 일반화해서 매번 `[SILENT]`를 반환 — 응답 생성과 턴 종료는 정상(`finish_reason=stop`)
이지만 배달만 스킵됨. `cron list`엔 실행 완료 후 정상적으로 사라지므로 겉보기엔 이상 없어
보임.

로그 확인: `grep "agent returned \[SILENT\]" ~/.hermes/logs/agent.log`

**"절대 침묵하지 마" 같은 명시적 지시로도 회피 안 됨(3회 재현, 매번 동일).** 지시로 고칠 수
있는 문제가 아님.

**범위**: `delegate_task(background=True)`로 동일하게 짧은 응답을 요구했을 때는 `[SILENT]`
없이 정상 배달됨 — **cron 시스템 프롬프트에 한정된 문제**이고 delegate_task·terminal·일반
대화는 영향 없음. `(실측)`

**해법**: 2번 섹션의 `--no-agent` 우회가 유일하게 확인된 대응. LLM 판단 자체를 거치지 않아
구조적으로 오판이 불가능함.

### 7.3 `/new` 타이핑 인디케이터 — 재현됨, 무해

`/new`(세션 리셋, LLM 호출 불필요) 응답 직후 텔레그램 타이핑 표시가 무기한 지속.
`is_processing=false`, 게이트웨이 단일 프로세스, 로그 4분+ 무활동 상태에서도 재현 —
`sendChatAction` 반복 태스크가 취소 안 되는 것으로 추정. 일반 대화 턴 종료 후에는 재현 안
됨(session_reset 경로 한정). 기능엔 영향 없음. `/restart`로 즉시 해소되나 다음 `/new` 때
재발 가능.

이슈 등록 후보:
```
저장소: NousResearch/hermes-agent, 버전: v0.20.0 (2026.8.3)
재현: 텔레그램에서 /new 전송 → 응답 즉시 수신 → 입력 중 표시 무기한 지속
확인: /slots is_processing=false, 게이트웨이 단일 프로세스, 로그 4분+ 무활동
```

---

## 8. 하드웨어 노트

- `llama-server --parallel 1` — 동시 추론 슬롯 1개. LLM이 필요한 모든 작업(delegate_task,
  cron 턴, goal 턴)이 이 슬롯을 공유해 사실상 직렬화됨. 진짜 동시 처리가 필요하면 `--parallel`
  상향 + `-c` 재분배 필요하나, 12GB VRAM + 128K 컨텍스트 조합에선 여유가 크지 않음.
- 로컬 12B는 tool calling·judge 판정 정확도가 프론티어 모델보다 낮음. `/goal`이나
  `delegate_task`가 이상하게 굴면 모델 능력 문제일 수 있으니 `hermes model`로 해당 역할만
  원격 API로 돌려서 원인을 분리할 것.

---

## 9. Hermes에게 이 지식을 알리기

이 문서를 Hermes가 자동으로 읽지는 않습니다. Hermes 자신의 *행동*을 바꿔야 하는 내용(6·7.2)은
memory/skill로 넘겨야 하고, 순수 인프라 troubleshooting(5·7.1·8)은 사람만 보면 되므로
이 문서에만 남겨둡니다. 상세 판단 기준과 실제로 등록한 내용은 별도로 정리 예정.

---

## 부록 — 무엇이 무엇으로 대체됐는가 (삭제된 엔진 기준)

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

**애초에 "알림이 안 온다"고 느꼈던 근본 원인**은 Hermes가 아니라 `core_engine.py`의 버그였음.
`run_orchestration()`이 `self.state`를 메모리에 한 번만 로드하고 이후 갱신하지 않아 종료
조건이 never true가 되는 무한루프였고, `notify_on_complete=true`는 프로세스 **종료 시점**에
발화하는데 그 프로세스가 종료된 적이 없어서 알림도 없었음 (커밋 `5102326` 참고).

## 부록 — 이벤트 훅 (필요시)

지금까지 테스트한 범위에선 내장 알림만으로 충분해서 안 씀. 더 세밀한 제어가 필요해지면
`~/.hermes/config.yaml`:
```yaml
hooks:
  outbound:
    - name: tg-notify
      url: <webhook-url>
      events: [subagent_stop, on_session_end]
      timeout: 10
```
이벤트 종류: `pre_tool_call`, `post_tool_call`, `pre_llm_call`, `post_llm_call`,
`on_session_start`, `on_session_end`, `subagent_start`, `subagent_stop`
