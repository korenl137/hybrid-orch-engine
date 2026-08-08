# Hermes Snapshot (헤르메스 스냅샷)

이 문서는 현재 운영 중인 **Hermes Agent 시스템의 정체성, 핵심 운영 원칙 및 기술적 환경**을 정의하는 매뉴얼입니다.

**참고 방식**: 이 문서는 Hermes에게 자동으로 로드되지 않습니다. 지금은 필요할 때 사람이 직접 참조를 지시하며, 추후 이 스냅샷을 최신 상태로 갱신해주는 스킬을 만들 예정입니다(자세한 내용은 `README.md` 9~10번 섹션 참고).

## 1. Identity & Philosophy (시스템 정체성)

### Designer-Executor Model
*   **Hermes:** 고도의 추론, 코드 설계, 아키텍처 분석, 데이터 처리 및 워크플로우 기획 담당.
*   **User:** Yun Ji (korenl137@skku.edu) - 로컬 환경에서의 최종 실행 승인, 물리적 하드웨어 제어, GPU 기반의 실질적 연산 수행 담당.

### Stateful Orchestration
*   모든 복잡한 프로젝트는 `project_status.json`과 같은 공유 상태 파일을 통해 현재 단계를 추적하고 컨텍스트를 유지합니다.
*   사용자는 진행 상황을 시각적으로 확인할 수 있도록 매 단계마다 명확한 상태 업데이트를 제공받습니다.

### Hybrid Execution Model
*   **Macro-Sequential:** 거시적인 프로젝트의 논리적 단계는 순차적으로(Step-by-step) 진행됩니다.
*   **Micro-Parallel:** 각 단계 내의 독립적인 하위 작업(예: 여러 타겟에 대한 개별 리서치 등)은 최대 성능을 위해 병렬로 실행될 수 있습니다.

## 2. Operational Constraints (운영 제약 사항)

### LLM Inference Limits
*   **Serial Processing:** 현재 시스템은 `--parallel 1` 설정으로 인해 모든 LLM 추론이 사실상 직렬(Sequential)로 처리됩니다.
*   **Expectation Management:** 작업 계획 시 예상 소요 시간을 안내할 때 이 제약 사항을 반드시 고려하여 현실적인 타임라인을 제시합니다.

### Notification & Reminder Policy
*   **Efficient Alerts:** 단순 알림이나 반복 리마인더 요청 시, LLM 토큰을 낭비하는 에이전트 모드를 사용하지 않습니다.
*   **No-Agent Cron:** `~/.hermes/scripts/`에 `echo` 또는 간단한 Python 스크립트를 생성하고, `--no-agent` 옵션을 사용하여 크론잡으로 등록합니다.

### Workspace & Resource Rules
*   **Output Path:** 모든 프로젝트의 연구, 분석, 코드, 문서 산출물은 반드시 `~/workspace/projects/<subject-slug>/` 경로 하위에 저장합니다.
*   **Shared Resources:** 여러 프로젝트에서 공통으로 사용하는 자원은 `~/workspace/shared/` 폴더에 통합 관리합니다.

## 3. System Environment (기술 환경)

> **마지막 실측 확인: 2026-08-08** (SFF에 원격 SSH로 직접 접속해 확인한 값. 이전 버전은
> 미검증 상태로 부정확한 값이 섞여 있었음 — 아래는 실측으로 교체한 것. 같은 날 안에
> Gemma4-12B → 26B-A4B 전환도 실행·검증됨, 상세 근거·벤치마크는 `README.md` 부록 "모델
> 전환 기록" 참고)

### Infrastructure
*   **OS:** Windows Subsystem for Linux (WSL), 호스트명 `Korenl-SFF`
*   **CPU/RAM:** 물리 RAM 32GB, WSL 할당 23GiB (`.wslconfig`: `memory=24GB, processors=12, swap=12GB`)
*   **GPU:** NVIDIA RTX 4070 SUPER, VRAM 12,282 MiB (driver 610.57.01, CUDA UMD 13.3) —
    "CUDA 12.6 활성화 완료"는 이전 버전의 미검증 서술이었음, 실측 드라이버 기준으로 정정
*   **VRAM 실사용량**: Gemma4-12B 단독 구동 시 여유 약 1.9~3GB, **Gemma4-26B-A4B
    (`--n-cpu-moe 12`, 비전 포함) 구동 시 여유 약 1.8GB** — 둘 다 build-guide.md 3-4의
    추정치보다 빠듯함. 추가 여유가 필요하면 `--n-cpu-moe`를 5 단위로 올릴 것(tg 속도 소폭 하락).

### Development Stack
*   **Language:** Python 3.11
*   **Package Manager:** `uv`
*   **Models:** **Gemma4-26B-A4B (QAT UD-Q4_K_XL, MoE) — 현재 메인, 2026-08-08 전환.**
    Gemma4-12B(Dense)는 대안/비교용으로 유지.
*   **모델 서버**: `llama-server`, systemd 템플릿 유닛 — 현재 `llm@gemma4-26b-a4b.service`
    활성(root 단위, 재시작 시 `sudo` 필요) — `~/llm-stack/bin/llm-switch.sh use <키>`로 전환,
    `~/llm-stack/registry.yaml`이 단일 소스. 키 이름은 `gemma4-26b-a4b` / `gemma4-12b`로
    **무게 기준 명명**(이전엔 `gemma4-12b-legacy`로 "legacy" 딱지를 붙였으나, 12B도
    프롬프트 처리 속도·VRAM 여유에서 실사용 가치가 있어 정정함 — 벤치마크는 README 참고)
*   **포트**: **8000** (2026-08-08 기준. 이전엔 8001로 드리프트돼 있었고, README의 "포트 8000
    통일 방침"과 불일치했던 것을 `registry.yaml` + `~/.hermes/config.yaml` 양쪽 수정으로 정정함)
*   **게이트웨이**: `hermes-gateway.service`는 **사용자 단위 systemd**(`~/.config/systemd/user/`,
    sudo 불필요) — `hermes gateway restart`로 재시작. 단, 재시작 시 진행 중이던 서브에이전트
    턴은 "우아하게 대기"한다는 메시지와 달리 즉시 끊길 수 있음(2026-08-08 실측, 컨텍스트
    압축 중 스폰된 감사 서브에이전트 3개가 재시작과 동시에 중단됨) — 트래픽 없는 시간대에
    재시작할 것.
*   **비전(mmproj) CUDA 크래시 리스크**: `ggml-org/llama.cpp` #21402 이슈는 RTX 4070 SUPER에서
    재현 안 됨(2026-08-08 실측, 이미지 처리 정상) — 비전 켜고 운영 가능.
*   **Data Tools:** Polars, etc.

## 4. Active Skill Inventory (활성화된 스킬셋)

| Skill Name | Category | Description |
| :--- | :--- | :--- |
| **simple_reminder** | Productivity | 단순 알림 요청 시 `no-agent` 크론작업으로 효율적으로 처리 |
| **workspace_org** | Productivity | 프로젝트별 산출물 경로 준수 및 공유 자원 관리 절차 수행 |

*이 문서는 시스템의 핵심 운영 정책을 담고 있으며, 새로운 규칙이나 환경 변화가 발생할 때마다 업데이트됩니다.*
