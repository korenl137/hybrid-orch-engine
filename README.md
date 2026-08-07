# Hermes Agent 자동화 사용법 (이 환경 기준)

이 레포는 원래 Hermes Agent에 붙일 자체 오케스트레이션 엔진이었습니다. 실제로 테스트해보니
필요한 기능(작업 완료 알림, 목표 추적, 예약 실행)이 Hermes 내장 기능만으로 자연어 그대로
작동한다는 게 확인돼서 엔진 코드는 전량 삭제했습니다 (`git show 647b8fc`에 원본 남아있음).

지금부터는 **"이 환경에서 무슨 말을 하면 무슨 일이 일어나는지"를 실측한 사용설명서**입니다.
전부 아래 환경에서 직접 텔레그램으로 테스트하고 로그로 검증한 내용입니다.

**환경**: WSL2 / Hermes Agent v0.20.0 / gemma-4-12b-it-qat-q4_0 (llama-server, `--parallel 1`,
`-c 131072`) / RTX 4070 12GB / 텔레그램 게이트웨이.

---

## 1. 실행 중인 작업이 끝나면 알림 받기

도구 이름이나 파라미터를 몰라도 됩니다. 그냥 시키면 Hermes가 알아서
`background=True` + `notify_on_complete=True`를 선택합니다 (실측 확인됨).

> 터미널에서 `<명령어>` 좀 돌려줘. 끝나면 알려주고, 안 기다려도 돼.

- 응답이 즉시 옵니다(작업을 기다리지 않음).
- 작업이 끝나면 성공이든 실패든 **새 메시지로 자동 통보**됩니다. 실패 시 종료 코드까지 알려줍니다.
- 리서치/분석처럼 LLM이 필요한 작업은 `delegate_task`로 위임해도 같은 방식입니다.

**주의**: 셸 명령(`sleep`, 빌드, 스크립트 등)은 OS 프로세스라 여러 개를 동시에 시켜도 진짜
병렬로 돕니다. 반면 **리서치·분석처럼 모델 추론이 필요한 백그라운드 작업 여러 개를 동시에
맡기면 `--parallel 1` 때문에 사실상 한 슬롯을 두고 줄을 섭니다.** "동시에 끝난다"가 아니라
"총 소요시간이 대략 합산된다"고 예상할 것. 결과가 섞이는 일은 없습니다(귀속은 정확).

**Hermes가 띄우지 않은 외부 프로세스는 추적 대상이 아닙니다.** WSL에서 직접 `nohup`으로
뭔가 돌리셨다면 그건 Hermes가 알 방법이 없습니다. 그럴 땐 명령 끝에 직접 붙이세요:
```bash
<작업>; curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  -d chat_id="${TELEGRAM_HOME_CHANNEL}" -d text="done: $?"
```

---

## 2. 예약 실행 / 반복 작업 (cron)

"cron"이라는 단어조차 필요 없이 말로 시켜도 job 생성과 배달 목적지 지정까지는 정확히
동작합니다(실측 확인됨).

> 5분 뒤에 딱 한 번만 "○○" 라고 알려줘.
> 매일 아침 9시에 서버 상태 확인해서 알려줘.
> 2시간마다 뉴스 확인해서 요약해줘.

**다만 판단 없이 그냥 알려주기만 하면 되는 단순 리마인더는 자연어 대신 `--no-agent`로
만드는 걸 권장합니다.** 이유는 아래 "확인된 이슈" 참고 — 이 환경에서 12B 모델이 짧은
리마인더 프롬프트를 반복적으로 `[SILENT]`(알릴 필요 없음)로 오판해서 배달이 조용히
스킵되는 게 실측으로 확인됐습니다. "뉴스 확인해서 요약해줘"처럼 진짜 판단·생성이 필요한
job은 에이전트 모드가 맞고, "몇 분 뒤 한 번 알려줘"류는 스크립트로 우회하는 게 안전합니다:

```bash
printf '#!/bin/bash\necho "<메시지>"\n' > ~/.hermes/scripts/<이름>.sh
chmod +x ~/.hermes/scripts/<이름>.sh
hermes cron create "<시간>" --no-agent --script <이름>.sh --deliver telegram:<chat_id> --name <이름>
```

**콘솔 없이 텔레그램에서 그대로 시켜도 됩니다(실측 확인됨)** — Hermes가 스크립트 생성부터
`--no-agent` 등록까지 스스로 처리합니다:
```
1분 뒤에 "<메시지>"라고 딱 한 번 출력하는 스크립트를 ~/.hermes/scripts/ 에 만들고,
그걸로 no-agent cron job을 등록해줘.
```

**CLI로 직접 관리:**
```bash
hermes cron create "every 2h" "<지시>" --deliver telegram:<chat_id>
hermes cron create "30m" "<지시>"                              # 일회성, 에이전트 모드
hermes cron create "every 5m" --no-agent --script <경로> --deliver telegram   # LLM 없이 스크립트만
hermes cron list
hermes cron remove <name-or-id>
```
`--script`는 `~/.hermes/scripts/` 아래 경로만 받습니다. 대화창에서 그냥
"방금 만든 알림 취소해줘"라고 해도 됩니다. 일회성(`Repeat: 1/1`) job은 실행 후
`cron list`에서 자동으로 사라지는 게 정상입니다 — 목록에 없다고 실패한 건 아닙니다.

**주의**:
- 스케줄이 정각에 딱 맞지는 않습니다. "1분 뒤"가 실제로는 몇 초~몇십 초 늦게 옵니다.
  스케줄러 틱 간격 때문이라 정상 범위입니다.
- cron이 실행하는 턴도 결국 같은 `--parallel 1` 슬롯을 씁니다. 다른 대화/작업이 몰려 있으면
  cron도 그 뒤에서 기다립니다.
- 드물게 특정 프롬프트가 모델의 생성 폭주(끝없이 토큰을 뱉는 상태)를 유발할 수 있습니다.
  이 경우 최대 수 분~10분 정도 슬롯이 묶이지만, **자체 provider timeout이 있어서 결국은
  실패로 보고됩니다** (조용히 씹히지 않음, 실측 확인됨). 자세한 원인·해결은 7번 참고.
- 에이전트 모드 job이 `agent returned [SILENT] — skipping delivery`로 조용히 스킵될 수
  있습니다. "절대 침묵하지 마" 같은 명시적 지시로도 회피 안 됨(실측 3회 재현). 자세한 내용은
  8번 참고, 위 `--no-agent` 대안 사용할 것.

---

## 3. 장기 목표 추적 (`/goal`)

세션이 끊기거나 게이트웨이가 재시작돼도 살아남습니다(실측: 재시작 2회 후에도 진행 상태·조건
그대로 복원). 매 턴마다 보조 judge가 완료 여부를 판정합니다.

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
judge는 **Acceptance 줄만** 판정 기준으로 삼습니다. "각 턴마다 하나씩" 같은 과정에 대한
지시는 강제되지 않고, 모델이 한 번에 몰아서 처리해도 Acceptance만 충족되면 완료 처리됩니다
(실측 확인됨).

**함정 — `/goal resume`은 스스로 다음 턴을 진행하지 않습니다.** pause 상태에서 resume만
보내면 "다음 메시지를 보내거나 기다리라"는 응답만 오고 실제 진행은 없습니다(실측 확인됨).
장기 목표를 진짜 무인으로 돌리려면 pause 후 넛지 메시지가 주기적으로 필요합니다:
```
hermes cron create "10m" "진행 중인 목표 있으면 계속 진행해"
```

카드 단위로 격리해서 돌리고 싶으면 kanban의 goal 모드도 같은 엔진을 씁니다:
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

## 5. 게이트웨이 재시작이 필요할 때

**텔레그램에서 그냥 `/restart`.** 콘솔 없이 됩니다(실측 확인됨). WSL의
`hermes gateway restart`와 동일 동작으로 보이며, in-flight 턴을 기다렸다가 우아하게
재기동합니다.

**단, `/restart`(및 `hermes gateway restart`)는 게이트웨이 프로세스만 재시작합니다.
llama-server(모델 서버)는 건드리지 않습니다** — 재시작 전후로 llama-server PID가 동일함을
실측 확인. 둘은 완전히 별개 supervisor(게이트웨이 자체 vs systemd `llm@gemma4` 서비스)로
관리되는 구조이기 때문입니다.

**진행 중인 턴이 있으면 그게 끝날 때까지 기다립니다** — 폭주 중인 생성이 있으면 그 턴이
끝나야 재시작도 끝나므로 수 분~10분 이상 걸릴 수 있습니다(실측 확인됨, 단 7번 이슈 해결
후로는 폭주 자체가 재현 안 되고 있음). 오래 걸리면 재시작 명령만 취소(Ctrl+C 또는 텔레그램
메시지 무시)하고 기다리면, 대개 provider timeout이 알아서 정리합니다(2번 참고).

**llama-server 자체가 문제일 때(응답 없음, 슬롯이 계속 물려있음)는 `/restart`로 안
풀립니다** — 콘솔에서 직접 다뤄야 합니다:
```bash
pgrep -af llama-server
kill -9 <PID>
~/llm-stack/bin/llm-switch.sh use gemma4      # registry.yaml 기준으로 재기동
```

---

## 6. 확인된 이슈 — `/new` 후 텔레그램 "입력 중" 표시가 안 사라짐

`/new`(세션 리셋, LLM 호출 불필요한 로컬 명령) 응답 직후 타이핑 인디케이터가 무기한
지속됩니다. `is_processing=false`, 게이트웨이 프로세스 정상 단일, 로그 4분+ 무활동 상태에서도
재현됨 — `sendChatAction`을 반복 발사하는 태스크가 취소 안 되는 것으로 추정. **일반 대화 턴
종료 후에는 재현 안 됨** (session_reset 경로 한정으로 보임). 기능엔 영향 없음(알림·자동화
전부 정상 동작). `hermes gateway restart`로 즉시 해소되나 다음 `/new` 때 재발 가능.

이슈 등록 후보:
```
저장소: NousResearch/hermes-agent, 버전: v0.20.0 (2026.8.3)
재현: 텔레그램에서 /new 전송 → 응답 즉시 수신 → 입력 중 표시 무기한 지속
확인: /slots is_processing=false, 게이트웨이 단일 프로세스, 로그 4분+ 무활동
```

---

## 7. 확인·해결된 이슈 — 생성 폭주 (repeat-penalty 미설정)

짧은 응답이면 충분한 프롬프트(예: cron의 "1분 뒤 한 번만 알려줘")에 대해 모델이 멈추지 않고
계속 토큰을 생성하는 현상을 재현. `/slots`에서 `n_decoded`가 18,927까지 올라간 채
`has_next_token: true`로 계속 진행 중이었음. 약 10분 후 provider timeout으로 자동 실패
처리되고 실패 알림도 정상 도착했음(조용히 씹히지 않음) — 하지만 `--parallel 1`이라 그
10분간 다른 모든 작업이 막힘.

**원인 조사**: `--reasoning-format`(gemma에 DeepSeek 파서가 잘못 적용됐다는 초기 가설)은
기각. `llama-server --help` 확인 결과 기본값이 `auto`이고, 템플릿이 reasoning을 지원한다고
선언하면 `deepseek` 포맷을 자동 선택하는 게 정상 동작 — 실제로 명시적으로 설정된 값이
아니었음. `--repeat-penalty`도 마찬가지로 기본값 `1.00`(=비활성)이었을 뿐 이례적인 설정은
아니었음. 즉 **"잘못 설정됐다"가 아니라 "아무것도 설정 안 된 기본 상태에서, 반복 억제
장치가 없다 보니 특정 프롬프트가 우연히 모델을 못 빠져나오는 반복 루프로 몰아넣었다"**는
쪽으로 결론.

**적용한 수정** (`~/llm-stack/registry.yaml`, `models.gemma4.extra_flags`):
```
--jinja --flash-attn on -ngl 99 --parallel 1 --repeat-penalty 1.1
```
`~/llm-stack/bin/llm-switch.sh use gemma4`로 적용 (이 스크립트가 `registry.yaml`을 읽어
`registry/gemma4.env`를 재생성하고 systemd 서비스를 재시작함 — `gemma4.env`를 직접 고치면
다음 전환 때 덮어써지므로 반드시 `registry.yaml`을 고칠 것).

**검증**: 동일 조건(같은 "1분 뒤 알려줘" 프롬프트)으로 재현 시도 → `n_decoded=696`에서
`is_processing: false`로 정상 종료, 폭주 재현 안 됨. **해결 확인됨.**

---

## 8. 확인된 이슈 — 짧은 리마인더가 `[SILENT]`로 조용히 스킵됨

cron job의 시스템 프롬프트에는 "알릴 필요 없으면 `[SILENT]`를 반환해서 배달을 건너뛰라"는
지침이 있는 것으로 보임(왓치독 job에서 "이상 없으면 조용히"용 기능으로 추정). "1분 뒤 딱
한 번만 '테스트 완료'라고 알려줘" 같은 단순 일회성 리마인더에서 12B 모델이 이 지침을
과도하게 일반화해서 매번 `[SILENT]`를 반환 — **정상적으로 응답을 생성하고 턴도 정상
종료(`finish_reason=stop`)하지만 배달만 스킵됨.** `hermes cron list`엔 job이 실행 완료 후
정상적으로 사라지므로 겉으로는 아무 이상이 없어 보임.

로그 확인 방법:
```bash
grep "agent returned \[SILENT\]" ~/.hermes/logs/agent.log
```

**프롬프트에 "절대 침묵하지 마", "[SILENT]를 반환하지 마"를 명시해도 회피 안 됨 (3회
재현, 매번 동일하게 스킵).** 지시로 고칠 수 있는 문제가 아니므로, 대응은 2번 섹션의
`--no-agent` 우회가 유일하게 확인된 해법. `--no-agent` job은 LLM 판단 자체를 거치지 않아
이 오판이 구조적으로 불가능함 — 실측으로 정상 배달 확인.

**범위 확정**: `delegate_task(background=True)`로 동일하게 "sleep 30 실행하고 끝나면 딱
'완료'라고만 답해줘"처럼 짧은 응답을 요구했을 때는 `[SILENT]` 없이 정상 배달됨(실측
확인됨). 즉 **이 문제는 "짧은 응답 전반"이 아니라 cron 시스템 프롬프트의 워치독형 지침에
한정**됨 — cron 외 경로(delegate_task, terminal, 일반 대화)에서는 재현되지 않음.

**텔레그램만으로 `--no-agent` 우회도 가능함(실측 확인됨)** — 콘솔 없이 다음과 같이
시키면 Hermes가 스스로 스크립트 파일을 만들고 `--no-agent` cron으로 등록함:
```
1분 뒤에 "<메시지>"라고 딱 한 번 출력하는 스크립트를 ~/.hermes/scripts/ 에 만들고,
그걸로 no-agent cron job을 등록해줘.
```

---

## 9. 하드웨어 노트

- `llama-server --parallel 1` — 동시 추론 슬롯 1개. 셸 백그라운드 작업은 영향 없지만, LLM이
  필요한 모든 작업(delegate_task, cron 턴, goal 턴)은 이 슬롯을 공유해서 사실상 직렬화됨.
  진짜 동시 처리가 필요하면 `--parallel` 상향 + `-c` 재분배 필요하나, 12GB VRAM + 128K
  컨텍스트 조합에선 여유가 크지 않아 트레이드오프 있음.
- 로컬 12B는 tool calling·judge 판정 정확도가 프론티어 모델보다 낮음. `/goal`이나
  `delegate_task`가 이상하게 굴면 모델 능력 문제일 수 있으니 `hermes model`로 해당 역할만
  원격 API로 돌려서 원인을 분리할 것.
- `repeat_penalty` 미설정으로 인한 생성 폭주: 7번 참고, `1.1`로 해결 확인됨.
- `[SILENT]` 오판으로 인한 무음 스킵: 8번 참고, 모델 능력(작은 모델의 지시 우선순위 처리)
  한계로 추정 — `--no-agent`로 우회.

---

## 10. 어디에 무엇을 저장하는가

세 위치가 각자 다른 역할을 함. 헷갈리면 산출물이 `/tmp`나 엉뚱한 곳에 흩어짐(실측으로
확인됨 — 아래 참고).

| 위치 | 역할 |
|---|---|
| `~/.hermes/` | **Hermes 자신을 운영하는 데 필요한 것.** 설정(`config.yaml`, `.env`), 로그, 메모리, 세션, cron이 참조하는 스크립트(`scripts/`), 스킬(`skills/`), 훅(`hooks/`). "Hermes를 설정/개선한다"는 성격의 파일만. |
| `~/hermes-agent-playbook/` (이 레포) | **Hermes *자체*에 대한 기록.** 사용법, 발견한 버그, 설정 튜닝 히스토리 — 이 문서. git으로 버전 관리됨. |
| `~/workspace/projects/<주제-slug>/` | **Hermes와 *함께* 만든 결과물.** 시장조사, 레포 분석, 추론 기록, 코딩 산출물, 문서 정리, 실험 기록 등 — "Hermes로 만든 것." |
| `~/workspace/shared/` | 여러 프로젝트가 공유하는 자원. |
| `~/workspace/.venv` | Hermes가 Python 실행 시 기본으로 쓰는 uv 관리 가상환경. |

**주의 — 이 관례는 Hermes에게 자동으로 적용되지 않습니다.** 실측 결과, `/goal`이나 일반
요청으로 만든 산출물은 지시하지 않으면 `/tmp` 같은 임시 경로에 만들어졌습니다
(`workspace/projects`, `workspace/shared`는 애초에 만든 이후 한 번도 안 쓰였음). 매번
경로를 지정하기 번거로우면, Hermes의 memory에 이 규칙을 저장해두는 걸 권장:

```
앞으로 리서치·분석·코딩·문서 작업의 결과물은 항상 ~/workspace/projects/<주제-slug>/
밑에 저장해라. 여러 프로젝트가 공유할 자원은 ~/workspace/shared/에 둬라.
```

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
