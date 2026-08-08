# MoE 모델 도입 검토 보고서 (하드웨어 실측 기반)

**작성**: Claude Code (단독 분석) / **작성일**: 2026-08-08
**대상**: `hermes-agent-playbook` 레포의 Qwen3.6 도입 논의
**입력 문서**: `build-guide.md` (v15 구축 가이드), `local_llm_analysis_report.md` (Hermes 협업 분석)

> 이 문서는 위 두 문서에 대한 **독립 검토**입니다. 결론이 다른 부분은 근거와 함께 명시했습니다.

---

## 0. 요약 (먼저 읽을 것)

> **업데이트 (사용자 확인)**: Qwen3.6은 **연구실 SFF(12GB VRAM, WSL 24GB 가변 할당)에서만**
> 돌릴 예정이며, 이 로컬 데스크탑(16GB)은 이번 건에 쓰지 않기로 확정됐습니다. 따라서 원래
> 8장에 있던 "두 기계 분리 배치" 제안은 **적용 대상이 아닙니다** — 참고용으로만 남겨두고,
> 이 문서의 결론은 전부 **SFF 12GB 단일 기계** 기준으로 다시 정리했습니다.

> **최종 결정 (2026-08-08)**: **B안 — Gemma4-12B → Gemma4-26B-A4B(MoE) 단일모델 교체**로
> 확정. Qwen3.6-35B-A3B는 폐기가 아니라 **조건부 보류**(코딩 요구가 실제 SWE-bench급으로
> 커지고 RAM을 28GB+로 올릴 수 있을 때 재검토). 최종 검증 결과와 `build-guide.md` v16
> 반영 내용은 **14장**에 정리했습니다.

1. **1장의 하드웨어 실측은 "이 로컬 데스크탑" 기준이며, 실제 배포 대상인 SFF가 아닙니다.**
   레포 문서(`README.md`, `build-guide.md`, `hermes_snapshot.md`)가 기술하는 RTX 4070 SUPER
   12GB / WSL Ubuntu 24.04 환경은 **SFF 쪽 얘기**이고, 사용자 확인상 그 전제는 맞습니다.
   이 로컬 데스크탑(RTX 4080 16GB, WSL 미설치)은 이번 도입과 무관합니다.
2. **Qwen3.6-35B-A3B의 "110 tok/s @ 4070 SUPER" 수치는 SFF에서 재현 불가합니다.**
   해당 사례는 다른 포크(ik_llama.cpp) + 다른 양자화(IQ4_XS) + **48GB RAM** 조합입니다.
   SFF는 WSL에 24GB만 할당돼 있어 오프로딩 여력이 근본적으로 부족합니다.
3. **진짜 병목은 VRAM이 아니라 SFF의 WSL RAM 할당(24GB)입니다.** 4장 참고.

---

## 1. 하드웨어 실측 — 이 문서 작성 중 확인한 것 (참고용)

> 아래는 이 대화가 실행된 **로컬 데스크탑** 실측입니다. Qwen3.6은 여기서 안 돌리기로
> 확정됐으니 참고로만 남겨두고, 실제 배포 대상인 **SFF**는 1-2를 보세요.

### 1-1. 이 PC (실측, 이번 도입과 무관)

`nvidia-smi`, `Win32_Processor`, `Win32_PhysicalMemory`, `wsl --list --verbose`로 직접 확인:

| 항목 | 실측값 |
|---|---|
| 호스트명 | `Korenl-Desktop` |
| GPU | **NVIDIA GeForce RTX 4080, 16,376 MiB** (driver 610.88, compute cap 8.9) |
| GPU 여유 | 14,442 MiB (측정 시점, 1,607 MiB 사용 중) |
| CPU | **Intel Core i7-13700K** (16코어 / 24스레드) |
| RAM | **32GB** (34,062,106,624 B) — DDR5-5600 16GB × 2 (Essencore KD5AGUA80) |
| 메인보드 | MSI MS-7D91 |
| WSL | **배포판 미설치** (`wsl --list --verbose` → "배포판이 없습니다") |
| `.wslconfig` | 존재함 (`processors=24`, `memory=16GB`) — 준비만 되고 미사용 |

### 1-2. 실제 배포 대상 — SFF (사용자 확인)

| 항목 | 값 |
|---|---|
| GPU | RTX 4070 SUPER **12GB VRAM** |
| 시스템 RAM | **32GB (물리)** |
| WSL 할당 | **24GB, 가변** (`.wslconfig`의 `memory=24GB`로 추정 — SFF에서 직접 확인 필요) |

레포 문서(`README.md`, `build-guide.md`, `hermes_snapshot.md`)가 기술하는 환경이
바로 이 SFF이고, `build-guide.md` 4번째 줄의 "연구실 PC(호스트)"에 해당합니다.
**이하 4~9장의 모든 분석은 이 SFF 스펙(12GB VRAM / RAM 32GB / WSL 24GB) 기준입니다.**

---

## 2. MoE의 실제 비용 — 개념 정리

Hermes 리포트의 "MoE Tax" 설명은 **정확합니다**. 다시 확인하면:

- **VRAM은 전체 파라미터 수가 결정합니다.** 활성 파라미터(A3B의 "3B")가 아닙니다.
- **속도만 활성 파라미터 수를 따릅니다.** 35B-A3B는 "35B만큼 메모리를 먹고 3B만큼 빠릅니다."
- 그래서 12GB에 안 들어가는 MoE는 `--n-cpu-moe`로 전문가 레이어를 **시스템 RAM**에
  내려야 하고, 이 순간부터 **시스템 RAM 용량과 대역폭이 진짜 병목**이 됩니다.

**이 점 때문에 웹의 상당수 자료가 틀립니다.** 예를 들어 여러 사이트가 Llama 4 Scout
(총 109B / 활성 17B)를 "12GB 카드에 Q4로 들어간다"고 쓰는데, 109B를 4bit로 잡아도
50GB 이상입니다. "17B처럼 VRAM을 쓴다"는 서술은 활성 파라미터와 메모리 점유를 혼동한
것이므로 **믿지 마세요**. 우리 케이스에선 후보에서 제외합니다.

---

## 3. 후보 모델 정리 (2026년 8월 기준)

VRAM 수치는 가중치만 기준이며, 여기에 KV 캐시 + 런타임 오버헤드(1~3GB)가 추가됩니다.

SFF는 12GB VRAM 한 장만 씁니다. 16GB 열은 **참고용(다른 카드였다면)**으로만 남겨둡니다.

| 모델 | 구조 | Q4급 크기 | SFF 12GB | (참고) 16GB | 강점 |
|---|---|---|---|---|---|
| **gpt-oss-20b** | MoE (~3.6B 활성) | **~12-13GB** (MXFP4 네이티브) | 빠듯함 | 여유 | 툴콜 깔끔, 42 tok/s 안정 |
| **Gemma 4 26B-A4B** | MoE (4B 활성) | ~14-18GB | 오프로드 필요 | 빠듯함 | 비전, Gemma 계열 연속성 |
| **GLM-4.7 Flash** | MoE (~3.6B 활성) | ~19.8GB (Q4_K_M) | 큰 오프로드 | 오프로드 필요 | 에이전틱/툴콜, "think before act" |
| **Qwen3.6-35B-A3B** | MoE (3B 활성) | ~19-21GB | 큰 오프로드 | 오프로드 필요 | SWE-bench 73.4, 코딩 최강 |
| **Qwen3.6 27B** | Dense | ~16.8GB | 불가 | 빠듯함 | 코딩 (dense 안정성) |
| **Gemma 4 12B** (현재) | Dense | ~8.5-9GB | **여유** | 여유 | 현행, 비전, 한국어 |

### 3-1. gpt-oss-20b — SFF엔 안 맞음 (참고용)

- MXFP4 네이티브 양자화(~4.25bpw)로 디스크 12-13GB. **4K 컨텍스트에서 이미 12.2GB**라
  SFF의 4070 SUPER 가용 VRAM(약 11GB)을 넘습니다. **SFF 12GB에는 못 씁니다.**
  (16GB 카드였다면 60K 컨텍스트까지 13.7GB, 41-42 tok/s로 유력한 선택지였을 겁니다 — 이번엔 해당 없음.)

### 3-2. Qwen3.6-35B-A3B — build-guide의 선택, 근거는 타당하나 조건이 다름

- SWE-bench Verified 73.4 / Terminal-Bench 2.0 51.5는 이 체급에서 독보적이고,
  build-guide가 이걸 근거로 고른 건 **판단으로선 옳습니다**.
- 문제는 실행 조건입니다. 4장에서 상술합니다.

### 3-3. Gemma 4 26B-A4B — build-guide가 기각했지만 재고 가치 있음

- build-guide 4장은 SWE-bench 17.4(Qwen 73.4 대비 4배 격차)를 이유로 기각했습니다.
  **에이전틱 코딩 목적이라면 이 기각은 타당합니다.**
- 하지만 Q4 기준 14-18GB로 35B-A3B보다 확실히 가볍고, **비전을 지원하며, 현재 쓰는
  Gemma 4-12B와 같은 계열**이라 프롬프트/템플릿 이관 비용이 가장 낮습니다.
- 24GB 카드에서 35~128 tok/s, DGX Spark에서 51.57 tok/s 보고.
- **"코딩 말고 일반 에이전트 + 비전 성능을 올리고 싶다"면 이쪽이 훨씬 현실적입니다.**

### 3-4. GLM-4.7 Flash — 다크호스

- 30B급 MoE, ~3.6B 활성. Q4_K_M 19.8GB.
- **에이전틱 특화**: SWE-bench / Terminal Bench 2.0에서 강하고, "행동 전 사고"
  구조가 자율 작업에 유리하다는 평. 툴 사용·터미널 작업이 GLM-4.6 대비 개선.
- 권장 환경이 24GB VRAM이라 SFF(12GB)에서는 오프로드 부담이 Qwen3.6-35B보다 오히려 큽니다.
  게다가 용도가 Qwen3.6-35B와 겹치므로, SFF에서는 **후순위**로 둡니다.

---

## 4. Qwen3.6-35B-A3B를 SFF(12GB)에 넣을 때의 현실

### 4-1. "110 tok/s" 수치의 조건 — 우리와 다릅니다

커뮤니티에서 자주 인용되는 RTX 4070 SUPER 12GB의 110.24 tok/s 결과는 다음 조건입니다:

| 항목 | 인용된 사례 | SFF |
|---|---|---|
| 백엔드 | **ik_llama.cpp 포크** | mainline llama.cpp (build-guide 6-1) |
| 양자화 | **IQ4_XS (4.19bpw)** | UD-Q4_K_XL (build-guide 6-2) |
| 시스템 RAM | **48GB DDR5-6000** | 32GB, **WSL에 24GB만 할당** |
| OS | CachyOS (베어메탈 리눅스) | WSL2 (가상화 계층 추가) |

**같은 GPU라는 것 말고는 공통점이 거의 없습니다.** 같은 quant로 mainline llama.cpp를
쓴 비교치는 **79.8~97.0 tok/s**였으니, 우리 환경의 현실적 기대치는 그보다 낮습니다.

### 4-2. 진짜 병목은 VRAM이 아니라 시스템 RAM입니다

- 모델 가중치 ~19-20GB 중 GPU가 감당하는 건 많아야 ~10-11GB → **최소 9-10GB를
  시스템 RAM으로 오프로드**해야 합니다.
- 커뮤니티 가이드는 MoE 오프로드 시 **시스템 RAM 32GB를 "하한", 64GB를 "권장"**으로
  보며, "16GB GPU에서 전문가를 오프로드하는 경우"를 128GB가 필요한 케이스로 분류합니다.
- SFF는 물리 32GB지만 **WSL 할당이 24GB**입니다. 여기서 9-10GB를 모델이 먹고,
  KV 캐시와 Ubuntu/Hermes/게이트웨이가 나머지를 나눠 씁니다. **하한선 아래**입니다.

**조치**: 도입한다면 `.wslconfig`의 `memory`를 24GB → 28GB로 올리는 걸 먼저 검토하세요
(호스트 Windows에 4GB만 남기는 건 위험하니 실측 필요).

### 4-3. 컨텍스트 길이 — 128K는 무리, 64K가 하한

- build-guide는 `context: 131072`(128K)를 씁니다. 35B MoE + 128K KV 캐시는
  12GB에서 오프로드 압력을 크게 키웁니다.
- 그렇다고 마음대로 줄일 수도 없습니다. **Hermes Agent는 `context_length`가 64,000
  미만이면 provider 초기화 자체를 거부**합니다(build-guide 3-3).
- 따라서 **선택지는 사실상 64K~128K 사이뿐**이고, Qwen 도입 시엔 **64K로 낮추는 게
  맞습니다.** (Hermes 리포트가 권장한 16K는 애초에 등록이 안 됩니다 — 5장 참고.)

### 4-4. MTP + 비전 동시 사용 리스크

- build-guide 13장 10번이 이미 경고한 대로, `--mmproj`(비전)와
  `--spec-type draft-mtp`(멀티토큰 예측) 동시 사용은 검증 사례가 적습니다.
- 기동 후 로그에 `n_drafted`/`n_accepted`가 안 보이면 MTP가 안 먹는 것이므로,
  `--spec-type draft-mtp --spec-draft-n-max 2` 두 토큰만 빼고 비전 전용으로 쓰세요.
- **처음부터 둘 다 켜지 말고, 비전 없이 MTP만으로 먼저 성공시킨 뒤 비전을 더하는
  순서**를 권합니다. 동시에 켜면 실패 시 원인 분리가 안 됩니다.

---

## 5. Hermes 리포트(`local_llm_analysis_report.md`)에 대한 의견

방향성(자체 엔진 포기 → Hermes 네이티브 + Playbook)은 **동의합니다.** 다만 파라미터를
그대로 `registry.yaml`에 옮기면 안 되는 지점이 있습니다.

| # | 리포트 서술 | 문제 | 권고 |
|---|---|---|---|
| 1 | Context Length `16,384 ~ 65,536` 권장 | **16K로 잡으면 Hermes가 provider 등록을 거부** (하드 체크 64,000) | 하한을 **64K**로 정정 |
| 2 | `-ngl 80~95` 동적 조정 | build-guide는 `-ngl 99` 고정 + `--n-cpu-moe`만 조정. 레버 2개를 동시에 움직이면 병목 구분 불가, dense 레이어까지 CPU로 밀려 속도 손실 | **`-ngl 99` 고정, `--n-cpu-moe`만 튜닝** |
| 3 | "현재 모델 체제(Gemma4 + Qwen3.6)" | Qwen은 **미설치**. registry에 `gemma4` 키 하나뿐 | "현재"가 아닌 "계획"으로 |
| 4 | VRAM 근거를 "Q4_K_M 수준"으로 서술 | build-guide가 받는 건 `UD-Q4_K_XL` (unsloth dynamic). 1-2GB 차이 | quant 명시 통일 |
| 5 | (누락) | 비전+MTP 리스크, `--parallel 1` 직렬화 제약 미언급 | 4-4 및 README 8장 반영 |

특히 1번은 그대로 따르면 **모델이 아예 안 붙는** 문제라 우선순위가 높습니다.

---

## 6. `build-guide.md`에 대한 의견

전반적으로 Hermes 리포트보다 **기술적으로 훨씬 정확합니다.** 3-1(KV 캐시 = 컨텍스트 ×
슬롯 수), 3-3(64K 하드 체크), 13장 리스크 체크리스트는 실제로 유효한 내용입니다.

다만 남은 문제:

1. **quant 불일치**: 6-2는 Gemma를 `unsloth/gemma-4-12b-it-GGUF`의 `UD-Q4_K_XL`로
   받으라 하는데, README 기준 실제 운영 모델은 **QAT Q4_0**입니다. 서로 다른 빌드입니다.
2. **registry 키 불일치**: 7-1은 `gemma4-12b` / `qwen35b`, README 7.1의 실제 운영 키는
   `gemma4`. Qwen 추가 시 반드시 정리해야 합니다.
3. **`--repeat-penalty` 누락**: 7-1의 `extra_flags` 예시에 값이 없어 기본 1.0으로 동작합니다.
   README 7.1 기준 현재 운영값은 **1.1**(생성 폭주 대응)이므로, Qwen 항목에도 넣을지
   판단이 필요합니다. (Qwen은 다른 모델이므로 폭주가 재현될지는 별개 문제입니다.)
4. **3-4 VRAM 표의 낙관**: Qwen3.6-35B-A3B를 "12GB 근접"으로 적었는데, 실제로는
   가중치만 19-21GB라 **12GB에 근접하는 게 아니라 절반 이상을 RAM으로 내리는** 것입니다.
   표현이 오해를 부릅니다.

---

## 7. SFF(12GB, 단일 기계) 기준 권고안

목적에 따라 갈립니다. **하나만 고르세요.**

### 선택지 A — 에이전틱 코딩이 목적이면: Qwen3.6-35B-A3B
build-guide 계획 그대로 가되, 아래를 수정:
- `context: 65536` (128K → 64K)
- `.wslconfig` `memory=28GB`로 상향 후 실측
- `--n-cpu-moe 26`에서 시작, OOM 보며 5씩 증가 (30, 35...)
- MTP 먼저, 비전은 나중에 (4-4)
- 기대치는 110이 아니라 **50-80 tok/s대**로 잡을 것

### 선택지 B — 일반 에이전트 + 비전 강화가 목적이면: Gemma 4 26B-A4B
- Q4 기준 14-18GB로 35B보다 가벼워 오프로드 압력이 작음
- 현재 Gemma 4-12B와 같은 계열 → 프롬프트/템플릿/`--repeat-penalty` 경험 그대로 이관
- 코딩 벤치는 낮지만(SWE-bench 17.4) Hermes의 주 용도가 크론/목표추적/리서치라면
  **코딩 벤치는 애초에 우리 워크로드가 아닙니다**
- build-guide의 기각 사유는 "에이전틱 코딩용"이라는 전제 하에서만 유효

### 선택지 C — 아무것도 안 바꾸기
현재 Gemma 4-12B dense는 12GB에서 8.5-9GB로 **유일하게 여유 있게 도는 구성**입니다.
README 7.1(생성 폭주)이 `--repeat-penalty 1.1`로 잡힌 지 얼마 안 됐으므로,
**안정성을 좀 더 관찰한 뒤 움직이는 것도 합리적입니다.**

**제 추천: B 또는 C.** A는 24GB RAM 제약 때문에 투입 대비 실망할 확률이 높습니다.

> 로컬 데스크탑(16GB)을 함께 쓰는 2-기계 분리 배치안도 검토했지만, 사용자 확인상
> 이번 건은 SFF 단독 운용으로 확정되어 제외했습니다 — WSL2 신규 설치 등 부가 비용 대비
> 실익이 없다고 판단했기 때문입니다.

---

## 8. 최종 결정 및 검증 (2026-08-08)

사용자가 코딩 요구를 명확히 하면서("간단한 코딩은 지금 모델로도 되는 것 아니냐", "코딩
쪽은 한쪽으로 정리해놓자") 7장의 B/C 선택이 **B로 좁혀졌고**, 도입 직전 마지막 기술
검증을 진행했습니다.

### 8-1. 코딩 능력 — "단순"과 "에이전틱"은 다른 문제였습니다

벤치마크를 나눠보면 왜 12B로도 "간단한 코딩"은 충분했는지, 그리고 26B-A4B가 그 선을
넘지 않는 이유가 같이 설명됩니다:

| 벤치마크 | 성격 | Gemma4-12B | Gemma4-26B-A4B | Qwen3.6-35B-A3B |
|---|---|---|---|---|
| HumanEval / LiveCodeBench | 단일 함수·스크립트 | 74-77% (커뮤니티 실측, Q5_K_XL) | 77.1% | — |
| SWE-bench Verified | 레포 탐색·멀티스텝 이슈 해결 | 미측정(낮음 추정) | **17.4%** | **73.4%** |

**결론**: "간단한 코딩"은 12B든 26B-A4B든 이미 잘 처리합니다 — 사용자의 직감이
맞았습니다. 26B-A4B로 바뀌어도 이 영역은 최소 현행 유지, 근소하게 개선됩니다.
"에이전틱 코딩"(SWE-bench급)만 26B-A4B로도 못 메우는 격차이고, 이건 Qwen3.6-35B-A3B가
유일한 해법입니다. → **B(26B-A4B)를 채택하고, 에이전틱 코딩은 build-guide.md v16의
부록 A로 조건부 보류.**

### 8-2. Quant/오프로드 재검증 — B의 실행 가능성이 처음 추정보다 좋습니다

- **QAT 버전이 따로 있고 훨씬 가볍습니다.** `unsloth/gemma-4-26B-A4B-it-qat-GGUF`의
  `UD-Q4_K_XL`은 **14.2GB**(비-QAT 버전 17GB보다 2.8GB 작음). 3장에서 쓴 "14-18GB"
  추정치의 하단에 정확히 맞아떨어집니다.
- SFF 가용 VRAM(~11GB) 대비 오프로드 필요분은 **~3-4GB**뿐입니다. Qwen이 필요로 하는
  9-10GB 오프로드와 비교하면 부담이 1/3 이하 — 4-2에서 지적한 "SFF의 WSL RAM 24GB는
  MoE 오프로드 하한선(32GB) 아래"라는 문제가 **B에는 사실상 적용되지 않습니다.**
- `--n-cpu-moe`가 mainline llama.cpp에서 26B-A4B 아키텍처를 정식 지원함을 확인했습니다
  (Qwen 전용 기능이 아님).
- Gemma 4 전체 계열(12B/26B-A4B/31B)의 최대 컨텍스트는 262,144로, Hermes의 64K 하한
  요구는 문제없이 통과합니다.

### 8-3. 새로 발견한 리스크 — 비전 mmproj CUDA 크래시

`ggml-org/llama.cpp` 이슈 트래커에서 **Gemma4-26B-A4B/31B의 `--mmproj`(비전 인코더)
로딩이 CUDA에서 SIGABRT로 죽는 사례**를 확인했습니다(issue #21402, RTX 5090/Blackwell
기준, "not planned"로 종료 — 즉 자체 해결 가능성 낮음). SFF의 RTX 4070 SUPER(Ada
Lovelace, compute 8.9)에서 재현된다는 보고는 없지만, 안전하다고 확인된 것도 아닙니다.

이건 원래 B를 고른 이유 중 하나("비전 유지")를 직접 건드리는 리스크라 가볍게 넘기지
않았습니다. **대응**: 설치 직후 텍스트 전용으로 먼저 기동 확인 → 비전 추가 후 이미지
테스트를 최우선으로 실행 → 크래시 시 `--no-mmproj`로 텍스트 전용 운영. `build-guide.md`
v16의 3-4, 6-3, 12-3(0번 테스트), 13장(7번 항목)에 전부 반영했습니다.

### 8-4. 최종 확정 사항

| 항목 | 값 |
|---|---|
| 메인 모델 | Gemma4-12B → **Gemma4-26B-A4B** (QAT, UD-Q4_K_XL, 14.2GB) |
| 컨텍스트 | 131072 → **65536** (오프로드 여유 확보, Hermes 64K 하한은 통과) |
| `--n-cpu-moe` 시작값 | **8** (실측하며 5씩 조정) |
| `--repeat-penalty` | 기본값(비활성)으로 시작, 폭주 재현 시에만 1.1 |
| 비전 | 유지하되 **크래시 검증 최우선** (`--no-mmproj` 폴백 준비) |
| Qwen3.6-35B-A3B | 폐기 아님, **조건부 보류** — RAM 28GB+ 확보 & 실제 에이전틱 코딩 수요 확인 시 재검토 (build-guide.md 부록 A) |
| 반영 문서 | `build-guide.md` v16 (전면 개정 완료) |

이 결정 이후 남은 건 **실제 설치와 12-3 테스트 체크리스트 실행뿐**입니다 — 문서 작업은
여기서 마무리합니다.

---

## 참고 자료

**2차 조사 — 26B-A4B 최종 검증 (8장)**
- [unsloth/gemma-4-26B-A4B-it-qat-GGUF (UD-Q4_K_XL, 14.2GB)](https://huggingface.co/unsloth/gemma-4-26B-A4B-it-qat-GGUF/blob/main/gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf)
- [Gemma 4 - How to Run Locally (Unsloth Docs)](https://unsloth.ai/docs/models/gemma-4)
- [Gemma 4 mmproj crashes on CUDA: SIGABRT (ggml-org/llama.cpp #21402)](https://github.com/ggml-org/llama.cpp/issues/21402)
- [Eval bug: Gemma-4-26B-A4B cannot process images (ggml-org/llama.cpp #21497)](https://github.com/ggml-org/llama.cpp/issues/21497)
- [Gemma4 26B-A4B CPU-expert offload discussion (ikawrakow/ik_llama.cpp #1765)](https://github.com/ikawrakow/ik_llama.cpp/issues/1765)
- [Gemma 4 26B A4B vs Qwen3.6-27B vs Qwen3.6-35B-A3B — Real-Coding Verdict](https://gist.github.com/hungson175/61a805368649c225026a69adf2ad87e0)

**1차 조사 — 초기 후보 비교**
- [Best Models to run on 12GB and 16GB VRAM in each use case](https://www.mayhemcode.com/2026/05/best-models-to-run-on-12gb-and-16gb.html)
- [Best Local LLMs by VRAM Tier 2026: 12GB, 24GB, 48GB Guide](https://www.promptquorum.com/local-llms)
- [110 tok/s on RTX 4070 Super with Qwen3.6 35B](https://startupfortune.com/110-toks-on-rtx-4070-super-with-qwen36-35b/)
- [Best Way to Run Qwen 3.6 35B MoE Locally: VRAM, Speed, Setup](https://insiderllm.com/guides/best-way-run-qwen-3-6-35b-moe-locally/)
- [Qwen 3.6 35B A3B VRAM Requirements (21.3GB Q4_K_M)](https://willitrunai.com/models/qwen-3.6-35b-a3b)
- [GPT-OSS 20B for local AI in 2026: the 128k context trap](https://runaihome.com/blog/gpt-oss-20b-local-ai-hardware-guide-2026/)
- [Best Local LLMs for 16GB VRAM: Practical Performance Testing 2026](https://localllm.in/blog/best-local-llms-16gb-vram)
- [guide: running gpt-oss with llama.cpp (ggml-org discussion #15396)](https://github.com/ggml-org/llama.cpp/discussions/15396)
- [Benchmarking Gemma-4-26B (A4B) on the DGX Spark](https://medium.com/@james-tang/benchmarking-gemma-4-26b-a4b-on-the-dgx-spark-dc8245292095)
- [Gemma 4 Local VRAM Guide: Choosing E2B, E4B, 12B, 26B, or 31B](https://knightli.com/en/2026/05/01/gemma-4-local-vram-quantization-table/)
- [We Tested GLM-4.7 Flash 30B MoE — Here's the GPU You Actually Need](https://www.hardware-corner.net/glm-4-7-flash-llm-hardware/)
- [GLM-4.7-Flash: How To Run Locally (Unsloth)](https://unsloth.ai/docs/models/tutorials/glm-4.7-flash)
- [Qwen3.6 Local VRAM Guide: Measuring 27B and 35B-A3B Quantizations](https://knightli.com/en/2026/05/01/qwen3-6-local-vram-quantization-table/)
- [ik_llama.cpp (GitHub)](https://github.com/ikawrakow/ik_llama.cpp)
- [Guide to optimizing inference performance of large MoE models across CPU+GPU](https://gist.github.com/DocShotgun/a02a4c0c0a57e43ff4f038b46ca66ae0)
