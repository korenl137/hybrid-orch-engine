# Hermes Agent 로컬 LLM 구축 가이드 (v16, Gemma4-26B-A4B 단일모델 체제 · Qwen3.6-35B-A3B 조건부 보류)

> 대상 하드웨어(SFF): RTX 4070 SUPER 12GB / DDR5 32GB (WSL 24GB 가변 할당)
> 구성: 연구실 SFF(Windows 11 + WSL2 Ubuntu 24.04, 호스트) ↔ 클라이언트(Tailscale + Orca SSH)
>
> v15(Gemma4-12B + Qwen3.6-35B-A3B 2모델 체제)에서 이어지는 개정판입니다. `reviews/moe-hardware-review.md`
> 검토 결과 다음과 같이 방향을 바꿨습니다:
> - **메인 모델을 Gemma4-12B → Gemma4-26B-A4B(MoE)로 교체.** 같은 Gemma 계열이라 비전·
>   `--repeat-penalty` 튜닝 경험을 그대로 이관할 수 있고, 12GB VRAM 대비 오프로드 부담도
>   작습니다(4-2 참고).
> - **Qwen3.6-35B-A3B는 완전히 버리지 않고 "조건부 보류"로 재분류.** 실제 코딩 요구가
>   "간단한 함수/스크립트" 수준이면 26B-A4B(LiveCodeBench 77.1%)로 충분하고, "레포 전체
>   탐색·멀티스텝 이슈 해결" 같은 진짜 에이전틱 코딩(SWE-bench)이 필요해질 때만 별도로
>   재검토합니다. 근거는 4장, 설정 예시는 부록 A 참고.
> - 두 모델 모두 llama.cpp 단일 빌드로 구동, 포트 8000 통일 방침은 그대로 유지합니다.
>
> 위에서 아래로 그대로 실행하면 재작업 없이 완성됩니다. **아직 SFF에 실제로 설치되지 않은
> 계획안**이므로(README 기준 현재 운영 모델은 여전히 Gemma4-12B), 실행 전 README와
> 대조해 최신 상태인지 확인하세요.

---

> **문서 상태 안내 (README 우선)**: 이 문서는 원래 외부에서 받은 v15 원본을, 이번 세션의
> 자체 분석(`reviews/moe-hardware-review.md`)을 반영해 **v16으로 직접 개정**한 것입니다. 아직 SFF에
> 실제로 적용되지 않았으므로 README 기준으로는 전부 미검증입니다. `README.md`와 내용이
> 충돌하면 **`README.md`가 우선**합니다. 특히 아래 항목은 실제로 따라 하기 전 재확인하세요:
> - **모델 quant**: 현재(구) 운영 모델은 README 기준 **Gemma 4-12B (IT, QAT Q4_0)**입니다.
>   이 문서가 안내하는 신규 모델(Gemma4-26B-A4B QAT UD-Q4_K_XL)은 아예 다른 빌드이므로
>   기존 모델 파일을 그대로 재사용할 수 없습니다.
> - **`--repeat-penalty`**: README 7.1 기준 현재 운영값은 **1.1**(생성 폭주 대응, `gemma4`
>   키). 26B-A4B는 다른 아키텍처라 같은 증상이 재현될지 검증 전까지는 알 수 없으니, 처음엔
>   기본값(1.0)으로 띄우고 폭주 시에만 1.1을 시도하세요.
> - **registry 키 이름**: 이 문서는 `gemma4`(신규 26B-A4B) 키를 씁니다. README 7.1이
>   참조하는 기존 `gemma4` 키(12B)와 이름이 겹치므로, 실제 전환 시 기존 키를 덮어쓸지
>   새 이름을 쓸지 먼저 정하세요.
> - Slack/Telegram 연동 등 모델과 무관한 절차는 v15 그대로이며 미검증 상태이니 단계별로
>   확인하며 진행하세요.

---

## 0. 보안 확인 (가장 먼저)

- ✅ 공식: `hermes-agent.nousresearch.com`, `github.com/NousResearch/hermes-agent`
- ⚠️ 사칭 확인됨: `hermes-agent.ai` — 결제를 요구하면 100% 사칭이니 절대 정보를 입력하지 마세요.
- 이후 8~11장에서 다루는 Telegram/Slack 봇 토큰은 노출되는 즉시 폐기(`/revoke`) 대상입니다. 대화 로그나 스크린샷에 토큰이 그대로 찍혔다면, 문제가 없어 보여도 새로 발급받는 습관을 들이세요.

---

## 1. 선제 점검 — 아무것도 설치하기 전에

### 1-1. GPU 패스스루 확인
```bash
nvidia-smi
```
RTX 4070 SUPER가 정상 출력되면 통과입니다. 안 보이면 Windows에서 [NVIDIA 드라이버](https://www.nvidia.com/drivers)를 최신화한 뒤 `wsl --shutdown` → 재시작하세요.

> ⚠️ WSL 안에서 `nvidia-driver-XXX` 같은 전체 드라이버 패키지는 절대 설치하지 마세요. Windows 쪽 드라이버가 패스스루를 처리하는 구조라, WSL 안에 드라이버를 따로 깔면 오히려 GPU 인식이 깨집니다.

### 1-2. WSL2 메모리 할당량 조정 (빌드 중 OOM 예방)

기본값은 호스트 RAM의 50%(32GB 중 16GB)로 제한돼 있습니다. CUDA 컴파일과 MoE 모델의 CPU 오프로드(`--n-cpu-moe`)가 메모리를 많이 쓰므로 미리 늘려둡니다. Windows `%UserProfile%\.wslconfig`:
```ini
[wsl2]
memory=24GB
processors=8
swap=8GB
```
저장 후 `wsl --shutdown` → 재시작하세요.

### 1-3. dpkg 상태 점검
```bash
sudo dpkg --configure -a
```

### 1-4. Orca 원격 접속용 Node.js 툴체인
```bash
sudo apt update
sudo apt install -y build-essential python3
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
source ~/.bashrc
nvm install 24 && nvm alias default 24 && nvm use 24
node -v
```
> Node 버전은 24로 고정해서 쓰세요. 임의로 업그레이드하면 node-pty 재빌드가 필요해질 수 있습니다.

---

## 2. 원격 접속 구성

### 2-1. 연구실 PC(호스트) WSL2 설치
```powershell
wsl --install -d Ubuntu-24.04
```

### 2-2. Tailscale 설치 및 SSH 활성화 (양쪽 PC)
```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --ssh   # 집 데스크톱은 --ssh 없이 실행
tailscale ip -4
```

### 2-3. Orca에서 SSH target 등록
Host = Tailscale IP, User = `whoami` 결과값, Port = 22

### 2-4. 트러블슈팅

**node-pty 로드 실패**: 빌드 툴체인/Node v24 재확인 → 재접속 재빌드 → target 재등록.

**WSL 자체가 `Wsl/Service/E_UNEXPECTED`로 죽었을 때**: 관리자 PowerShell에서 `wsl --shutdown` → `wsl --update` → 그래도 안 되면 PC 재부팅. 대개 RAM 소진이 원인이므로 1-2의 메모리 설정을 재확인하세요.

**Tailscale auth key 만료**: 재발급 후 `sudo tailscale up --ssh --authkey=새키`로 재인증하세요.

---

## 3. 하드웨어 제약과 VRAM 계산 (v16: 26B-A4B 단일모델 기준으로 갱신)

| 리소스 | 사양 |
|---|---|
| GPU VRAM | RTX 4070 SUPER 12,281 MiB (부팅 직후 여유 약 11,049 MiB) |
| 시스템 RAM | DDR5 32GB (WSL 내 24GB 할당, 1-2 참고) |
| 케이스/PSU | Terra ITX / SF850 SFX |

### 3-1. KV 캐시와 슬롯 수의 관계

```
KV 캐시(bytes) = 2(K,V) × 레이어 수 × KV 헤드 수 × head_dim × 컨텍스트 길이 × 슬롯 수 × 정밀도(byte)
```

**컨텍스트 길이가 아니라 "컨텍스트 × 슬롯 수"가 진짜 메모리 소비량**입니다. `n_parallel`(슬롯 수)이 `auto`로 잡히면 llama-server가 슬롯을 여러 개 만들어 컨텍스트 길이를 그대로 곱한 만큼 VRAM을 더 씁니다. 1인 사용 환경에서는 반드시 `-np 1`(또는 `--parallel 1`)로 슬롯을 1개로 고정하세요.

### 3-2. MoE 모델의 추가 변수 — `--n-cpu-moe`

Gemma4-26B-A4B는 MoE(Mixture of Experts) 구조라(128개 전문가 중 토큰당 8개만 활성화), 전문가(expert) 레이어의 일부를 VRAM이 아니라 **시스템 RAM에 올릴 수 있는 `--n-cpu-moe` 플래그**가 VRAM 계산에 추가로 개입합니다. 이 숫자를 올릴수록 VRAM 사용량은 줄고 속도는 소폭 느려집니다. 이전 메인이었던 Dense 모델(Gemma4-12B)에는 해당하지 않던 옵션입니다. `--n-cpu-moe`는 mainline llama.cpp에서 26B-A4B 아키텍처를 정식 지원합니다.

### 3-3. Hermes Agent의 컨텍스트 하드 체크

Hermes Agent는 **64,000 토큰 미만 컨텍스트로 등록된 모델은 provider 초기화 자체를 거부**합니다(`config.yaml`의 `context_length` 필드 기준이며, 서버가 실제로 그 값을 감당하는지와 무관하게 하드코딩된 체크입니다). 즉 서버도 64K 이상으로 실제 기동해야 하고, config에도 64K 이상으로 기입해야 둘 다 통과합니다.

### 3-4. 실측/추정 VRAM 표

| 모델 | 조건 | 가중치 크기 | VRAM |
|---|---|---|---|
| (구, 현재 운영중) Gemma4-12B (QAT Q4_0, 비전 포함) | `-c 131072 -np 1` | ~8GB | 약 8.5~9GB / 12GB (여유 약 3~3.5GB) |
| **(신규) Gemma4-26B-A4B (QAT UD-Q4_K_XL)** | `-c 65536 --n-cpu-moe 8 -np 1` | **14.2GB** | 가중치가 SFF 가용 VRAM(약 11GB)을 넘으므로 **~3-4GB를 `--n-cpu-moe`로 오프로드 필수** |
| (보류) Qwen3.6-35B-A3B (UD-Q4_K_XL, 비전+MTP) | `-c 65536 --n-cpu-moe 26 -np 1` | ~19-21GB | **~9-10GB 오프로드 필요** — SFF의 WSL RAM 할당(24GB)로는 하한선 아래. 부록 A 참고 |
| (참고, 사용 중단) Ternary Bonsai 27B (Q2_0) | `-c 65536 --parallel 1` | ~9GB | 약 9.3GB — 비전 미지원으로 v15에서 제외 |

**26B-A4B 관련 참고사항**:
- 비표준 `-it-GGUF`(17GB)가 아니라 **QAT(Quantization-Aware Training) 버전**
  (`unsloth/gemma-4-26B-A4B-it-qat-GGUF`)의 `UD-Q4_K_XL`(14.2GB)을 받으세요 — 현재 운영 중인
  12B도 QAT 버전이라 일관성이 맞고, 오프로드 부담도 2.8GB 더 적습니다.
- `--n-cpu-moe 8`은 시작 추정치입니다(가중치 14.2GB 중 오프로드 필요분 ~3GB를 26B-A4B의
  MoE 레이어 비율로 환산한 값). Qwen처럼 실측하며 5 단위로 조정하세요.
- **컨텍스트를 128K가 아니라 64K로 시작**하는 걸 권장합니다 — 오프로드가 이미 있는 상태에서
  128K KV 캐시까지 얹으면 여유가 더 줄어듭니다. Hermes 하드 체크(3-3)는 64K부터 통과합니다.
- ⚠️ **비전(`--mmproj`) 로딩이 CUDA에서 크래시하는 사례가 보고돼 있습니다**
  (`ggml-org/llama.cpp` issue #21402, 26B-A4B/31B 대상, RTX 5090에서 SIGABRT). SFF의
  RTX 4070 SUPER(Ada Lovelace)에서 재현된다는 보고는 아직 없지만 확인된 것도 아니므로,
  **설치 직후 반드시 이미지 입력을 먼저 테스트**하세요. 크래시하면 `--no-mmproj`로
  텍스트 전용 운영하고 upstream 수정을 기다리는 게 유일한 대응입니다(해당 이슈는
  "not planned"로 종료됨 — 자체 해결 가능성 낮음).

**결론**: 26B-A4B는 12GB 안에 단독으로는 안 들어오고 `--n-cpu-moe` 오프로드가 필수입니다.
Qwen보다는 오프로드 폭이 훨씬 작아 SFF의 24GB WSL RAM 한도 안에서 현실적입니다.

---

## 4. 모델 선정 — 왜 26B-A4B인가 (v16)

| 모델 | 역할 | 실행 방식 | 근거 |
|---|---|---|---|
| **Gemma4-26B-A4B** | 메인(단일) | llama-server (systemd 상시구동, 포트 8000) | 비전 지원 유지, 같은 Gemma 계열이라 12B에서 검증한 `--repeat-penalty` 튜닝·프롬프트 이관 비용 최소, LiveCodeBench 77.1%로 "간단한 코딩"까지 커버, 12GB에서 오프로드로 실행 가능 |

### 코딩 능력 — 왜 이걸로 충분하다고 판단했는가

Hermes의 실제 사용 기록(README 1~6장: 알림·cron·`/goal`·리서치 위임)은 에이전틱 코딩이
아니라 일반 비서·리서치 용도입니다. 코딩 벤치마크를 "단순 코딩"과 "에이전틱 코딩" 둘로
나눠 보면 이 선택의 근거가 갈립니다:

| 벤치마크 유형 | 의미 | Gemma4-12B(현) | Gemma4-26B-A4B | Qwen3.6-35B-A3B |
|---|---|---|---|---|
| HumanEval / LiveCodeBench (단일 함수·스크립트) | "간단한 코딩" | 74-77% | 77.1% | — |
| SWE-bench Verified (레포 탐색·멀티스텝 이슈 해결) | "에이전틱 코딩" | 미측정(낮음 추정) | **17.4%** | **73.4%** |

**즉 "간단한 코딩"은 12B에서도 이미 문제없고 26B-A4B가 이를 유지·소폭 개선하지만,
"에이전틱 코딩"만큼은 26B-A4B로도 안 풀립니다.** 이 갭을 메우려면 Qwen3.6-35B-A3B가
유일한 대안인데, SFF의 RAM 여유(WSL 24GB 할당, 커뮤니티 기준 하한 32GB)로는 지금
감당이 안 됩니다(3-4 참고). 그래서 이번 v16에서는:
- **에이전틱 코딩을 지금 당장의 요구사항에서 제외**하고(실사용 기록상 필요하지 않았음),
- Qwen3.6-35B-A3B는 완전히 버리지 않고 **"조건부 보류"**로 남겨 부록 A에 설정 예시를
  보존합니다. 실제로 SWE-bench급 작업이 반복적으로 필요해지고, `.wslconfig` RAM을
  28GB 이상으로 올릴 수 있게 되면 그때 재도입을 검토하세요.

### 검토 후 제외한 모델들

- **Ternary Bonsai 27B**: 코딩·수학은 강했지만 비전 미지원이라, "이미지 입력이 기본"이라는 요구사항과 맞지 않아 제외.
- **Hermes 4/3 (Ollama)**: Bonsai의 툴콜 폴백용이었으나, Bonsai 자체를 빼면서 폴백 체인의 필요성이 사라져 함께 정리.
- **Gemma4-12B 유지(현행 무변경)**: 안정성은 최고지만, 26B-A4B가 지식 용량·tool calling 정확도에서 더 나을 것으로 기대되고 RAM 여유 안에서 실행 가능해 굳이 미룰 이유가 없다고 판단.

---

## 5. Hermes Agent 설치 절차

### 5-1. 필수 시스템 패키지
```bash
sudo apt update
sudo apt install -y ripgrep ffmpeg zstd cmake build-essential
```

### 5-2. CUDA Toolkit (WSL2 전용, GPU 드라이버와 별개)
```bash
wget https://developer.download.nvidia.com/compute/cuda/repos/wsl-ubuntu/x86_64/cuda-wsl-ubuntu.pin
sudo mv cuda-wsl-ubuntu.pin /etc/apt/preferences.d/cuda-repository-pin-600
wget https://developer.download.nvidia.com/compute/cuda/12.6.0/local_installers/cuda-repo-wsl-ubuntu-12-6-local_12.6.0-1_amd64.deb
sudo dpkg -i cuda-repo-wsl-ubuntu-12-6-local_12.6.0-1_amd64.deb
sudo cp /var/cuda-repo-wsl-ubuntu-12-6-local/cuda-*-keyring.gpg /usr/share/keyrings/
sudo apt-get update && sudo apt-get -y install cuda-toolkit-12-6
echo 'export PATH=/usr/local/cuda/bin:$PATH' >> ~/.bashrc
source ~/.bashrc
nvcc --version
```

### 5-3. Hermes Agent 본체 설치
```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
source ~/.bashrc
```

### 5-4. 설치 마법사

llama-server 단일 빌드로 띄우므로, 마법사에서는 항상 **Custom (OpenAI-compatible API)** 를 선택합니다. 아직 6장에서 서버를 안 띄웠다면 이 단계는 잠시 건너뛰고, 6장 완료 후 `/model`에서 등록해도 됩니다.

```
Choose a provider:
  Nous Portal          ← 선택 금지 (클라우드)
  Nous Subscription    ← 선택 금지 (클라우드, 유료)
→ Custom (OpenAI-compatible API)   ← 선택
```
```
API base URL: http://localhost:8000/v1
API key: (비워두고 Enter)
Detected model: gemma-4-26b-a4b-it (예시) — Use this model? Y
Context length in tokens: 65536
```

**Terminal Backend**: Docker를 설치했으면 `docker`, 아니면 `local` 유지.
**Messaging Platforms**: 스킵 (9~10장에서 별도 설정).
**Web Search & Extract**: `DuckDuckGo (ddgs)` 추천.
**Browser/Vision/TTS**: 기본값 유지 — Vision 관련 옵션은 켜두되, 3-4의 CUDA 크래시 캐비어트를
먼저 확인하세요.

### 5-5. Playwright Chromium 설치 (⚠️ sudo 없이)
```bash
cd ~/.hermes/hermes-agent
npx playwright install --with-deps chromium
```

### 5-6. GitHub Personal Access Token
1. [github.com/settings/tokens](https://github.com/settings/tokens) → Generate new token (classic)
2. Note: `hermes-agent-skills`, Expiration 90일, Scopes: `public_repo`만
3. 토큰 복사 후:
```bash
hermes config set GITHUB_TOKEN ghp_여기에_복사한_토큰
```

### 5-7. YAML 문법 주의사항 (config.yaml 직접 편집 시)

콜론(`:`)이 포함된 키(모델명, provider 표시명 등)는 반드시 따옴표로 감싸야 합니다. 저장 전 문법 검증:
```bash
python3 -c "import yaml; yaml.safe_load(open('/home/yun/.hermes/config.yaml'))" && echo "YAML OK"
```

### 5-8. AGENTS.md 컨텍스트 잘림 경고 대응

`~/.hermes/hermes-agent`(설치 소스 디렉터리) 안에서 `hermes`를 실행하면 그 저장소의 대용량 `AGENTS.md`(7만 자 이상)를 읽으려다 20,000자 기본 한도에 걸립니다. 별도 작업 디렉터리를 만들어 거기서 실행하세요.
```bash
mkdir -p ~/hermes-workspace
cd ~/hermes-workspace
hermes
```

### 5-9. 최종 점검
```bash
hermes doctor
curl http://localhost:8000/v1/models
```

---

## 6. llama.cpp 빌드 및 모델 준비

### 6-1. llama.cpp 빌드 — OOM 예방 필수

```bash
git clone https://github.com/ggml-org/llama.cpp ~/llama.cpp
cd ~/llama.cpp
cmake -B build -DGGML_CUDA=ON
cmake --build build --config Release -j2
```
> ⚠️ `-j`(무제한 병렬)로 돌리면 CUDA 템플릿 컴파일 중 `Killed`/`cc1plus` OOM이 나거나, 심하면 WSL2 자체가 `E_UNEXPECTED`로 죽습니다. **반드시 `-j2`처럼 병렬 수를 제한**하세요. 그래도 죽으면 스왑을 추가하세요.
```bash
sudo fallocate -l 8G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
```
빌드 완료 확인:
```bash
git -C ~/llama.cpp log -1 --oneline
~/llama.cpp/build/bin/llama-server --version   # 빌드 번호가 최신(b9620 이상)인지 확인
```
> MTP(Multi-Token Prediction) 추측 디코딩을 쓰려면 최신 빌드가 필수입니다. 오래된 빌드는 `--spec-type draft-mtp` 자체를 인식하지 못합니다.

### 6-2. GGUF 다운로드 — pip 대신 uv 사용

Ubuntu 24.04는 PEP 668 정책으로 `pip install`이 기본 차단됩니다. Hermes가 이미 설치해둔 `uv`를 씁니다.
```bash
echo 'export PATH=$HOME/.hermes/bin:$PATH' >> ~/.bashrc
source ~/.bashrc
uv --version
```

**Gemma4-26B-A4B (QAT, 신규 메인)**
```bash
mkdir -p ~/llm-stack/models/gemma4-26b-a4b
uvx --from huggingface_hub hf download unsloth/gemma-4-26B-A4B-it-qat-GGUF \
  --include "*mmproj*" \
  --include "*UD-Q4_K_XL*" \
  --local-dir ~/llm-stack/models/gemma4-26b-a4b
```
> QAT 버전(`-it-qat-GGUF`)을 받으세요 — 비-QAT `-it-GGUF`의 같은 quant보다 2.8GB 더
> 작습니다(14.2GB vs 17GB, 3-4 참고). 현재 운영 중인 12B도 QAT라 일관성이 맞습니다.

**(구, 유지) Gemma4-12B** — 이미 받아둔 파일을 그대로 씁니다. 재다운로드 불필요.

**(보류) Qwen3.6-35B-A3B** — 지금은 받지 않습니다. 부록 A에 조건부 재도입 시 쓸 명령을
남겨뒀습니다.

### 6-3. 단발성 CLI 테스트 — ⚠️ 비전(mmproj) 크래시 먼저 확인

3-4에서 언급한 CUDA 크래시 보고 때문에, **비전 옵션 없이 텍스트 전용으로 먼저 기동을
확인**한 뒤 `--mmproj`를 추가하는 순서를 권장합니다.

```bash
cd ~/llama.cpp
# 1단계: 텍스트 전용으로 기동 확인
./build/bin/llama-cli \
  -m ~/llm-stack/models/gemma4-26b-a4b/gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf \
  -cnv --jinja \
  -p "간단한 인사말을 해줘." \
  -n 512 --temp 0.7 --top-p 0.95 --top-k 20 -ngl 99 --n-cpu-moe 8
```
정상 종료하면 2단계로 `--mmproj`를 추가한 llama-server를 띄우고 이미지 1장을 넣어
확인하세요(7-3 참고). 여기서 SIGABRT가 나면 `--no-mmproj`로 텍스트 전용 운영하고
upstream 수정을 기다리세요(해당 이슈는 "not planned"로 종료돼 자체 해결 가능성은 낮습니다).

---

## 7. registry.yaml 및 llm-switch.sh — 단일모델 + 보류 모델 등록 체계

### 7-1. registry.yaml 최종본

`gemma4` 키를 신규 26B-A4B로 교체합니다. 기존 12B를 롤백용으로 남겨두고 싶으면
`gemma4-12b-legacy`처럼 별도 키로 옮겨두세요(README의 실제 운영 키와 이름이 겹치지
않도록 전환 직전에 실제 `registry.yaml` 현재 상태를 먼저 확인하는 걸 권장합니다 — 문서
상단 안내 참고).

```yaml
models:
  gemma4:
    display_name: "Gemma4-26B-A4B (메인, 비전 지원, MoE)"
    build: mainline
    model_path: "~/llm-stack/models/gemma4-26b-a4b/gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf"
    mmproj_path: "~/llm-stack/models/gemma4-26b-a4b/mmproj-F16.gguf"
    port: 8000
    context: 65536
    cache_k: q8_0
    cache_v: q8_0
    extra_flags: "--jinja --no-mmproj-offload -ngl 99 --n-cpu-moe 8 -fa on -np 1"

  gemma4-12b-legacy:
    display_name: "Gemma4-12B (구 메인, 롤백용)"
    build: mainline
    model_path: "~/llm-stack/models/gemma4-12b/gemma-4-12b-it-UD-Q4_K_XL.gguf"
    mmproj_path: "~/llm-stack/models/gemma4-12b/mmproj-F16.gguf"
    port: 8000
    context: 131072
    cache_k: q8_0
    cache_v: q8_0
    extra_flags: "--jinja --no-mmproj-offload -ngl 99 --repeat-penalty 1.1 -fa on -np 1"

default_model: gemma4
```

> `--n-cpu-moe 8`은 3-4에서 추정한 시작값입니다. `nvidia-smi`로 VRAM이 12GB를 넘는지
> 보며 5 단위로 조정하세요. `gemma4-12b-legacy`엔 README 7.1에서 검증된
> `--repeat-penalty 1.1`을 그대로 남겨뒀습니다 — 26B-A4B에서 폭주가 재현되면 `gemma4`
> 항목에도 같은 값을 추가하세요.
>
> Qwen3.6-35B-A3B 조건부 재도입 시 쓸 registry 항목은 **부록 A**에 따로 보존해뒀습니다.

### 7-2. llm-switch.sh 전환 스크립트

```bash
#!/bin/bash
# ~/llm-stack/bin/llm-switch.sh
REGISTRY=~/llm-stack/registry.yaml
LOGDIR=~/llm-stack/logs

case "$1" in
  list)
    yq '.models | keys' "$REGISTRY"
    ;;
  status)
    curl -s http://localhost:8000/v1/models | jq -r '.data[].id' 2>/dev/null || echo "서버 응답 없음"
    ;;
  use)
    KEY="$2"
    pkill -f llama-server 2>/dev/null
    sleep 1
    MODEL_PATH=$(yq ".models.$KEY.model_path" "$REGISTRY")
    MMPROJ=$(yq ".models.$KEY.mmproj_path" "$REGISTRY")
    PORT=$(yq ".models.$KEY.port" "$REGISTRY")
    CTX=$(yq ".models.$KEY.context" "$REGISTRY")
    CACHE_K=$(yq ".models.$KEY.cache_k" "$REGISTRY")
    CACHE_V=$(yq ".models.$KEY.cache_v" "$REGISTRY")
    FLAGS=$(yq ".models.$KEY.extra_flags" "$REGISTRY")
    mkdir -p "$LOGDIR"
    nohup ~/llama.cpp/build/bin/llama-server \
      -m "$(eval echo $MODEL_PATH)" \
      --mmproj "$(eval echo $MMPROJ)" \
      --host 127.0.0.1 --port "$PORT" \
      -c "$CTX" --cache-type-k "$CACHE_K" --cache-type-v "$CACHE_V" \
      $FLAGS > "$LOGDIR/$KEY.log" 2>&1 &
    echo "$KEY 기동 중... 로그: $LOGDIR/$KEY.log"
    ;;
  *)
    echo "사용법: ./llm-switch.sh [list|status|use <모델키>]"
    ;;
esac
```
```bash
chmod +x ~/llm-stack/bin/llm-switch.sh
```

### 7-3. 기동 명령 및 검증

```bash
~/llm-stack/bin/llm-switch.sh list
~/llm-stack/bin/llm-switch.sh use gemma4
curl http://localhost:8000/v1/models
nvidia-smi        # VRAM이 12GB를 넘지 않는지 확인, 넘으면 --n-cpu-moe 값을 5씩 올려 재시도
```

문제가 생겨 구 모델로 롤백하려면:
```bash
~/llm-stack/bin/llm-switch.sh use gemma4-12b-legacy
curl http://localhost:8000/v1/models
```

### 7-4. Hermes와의 연동

`port: 8000`으로 고정해뒀으므로 `~/.hermes/.env`는 한 번만 설정하면 됩니다.
```bash
# ~/.hermes/.env
LLM_BASE_URL=http://localhost:8000/v1
```
롤백 등으로 모델을 바꿀 때도 `.env`를 고칠 필요 없이, `llm-switch.sh use <키>`만 실행하고 Hermes를 재시작(또는 `/model` 재선택)하면 됩니다.

### 7-5. 다른 provider/모델을 추후 추가하는 법 (범용 절차)

나중에 다른 로컬/클라우드 모델을 더 추가하고 싶다면(예: 부록 A의 Qwen3.6-35B-A3B 조건부 재도입) 동일 패턴을 씁니다.

1. 모델 서버를 OpenAI 호환 `/v1` 엔드포인트로 띄운다 (llama-server, Ollama, vLLM, LM Studio 등 모두 해당).
2. Hermes에서 `/model` → **Custom endpoint (enter URL manually)** 선택.
3. `API base URL` 입력 (예: `http://localhost:8001/v1`처럼 겹치지 않는 포트).
4. 로컬 서버라 API 키가 필요 없으면 비워두고 Enter.
5. 자동 감지된 모델명 확인 → **컨텍스트 길이를 반드시 64,000 이상**으로 입력(3-3의 하드 제한과 동일 원리).
6. `display name`을 알아보기 쉽게 지정.

> ⚠️ 5번 조건 때문에, 새 모델을 추가할 때마다 VRAM이 실제로 그 컨텍스트를 감당하는지 3장의 방식(`-np 1` 등 슬롯 조정)으로 먼저 검증해야 합니다.

---

## 8. 상시 구동을 위한 초기 세팅

### 8-1. Windows 절전 완전 비활성화
```powershell
powercfg.exe /hibernate off
```

### 8-2. WSL2 systemd 활성화
`/etc/wsl.conf`:
```ini
[boot]
systemd=true
```
```powershell
wsl --shutdown
wsl
```

### 8-3. Windows 부팅 시 WSL2 자동 실행
작업 스케줄러 → 트리거 "로그온할 때" → 동작: `wsl.exe -d Ubuntu-24.04 -- echo booted`

### 8-4. Gemma4-26B-A4B를 systemd로 상시 구동

단일모델 체제이므로 메인 모델 하나만 상시 서비스로 등록합니다.

```bash
sudo tee /etc/systemd/system/gemma4-llama.service <<'EOF'
[Unit]
Description=Gemma4-26B-A4B llama-server
After=network.target

[Service]
ExecStart=/home/%u/llama.cpp/build/bin/llama-server \
  -m /home/%u/llm-stack/models/gemma4-26b-a4b/gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf \
  --mmproj /home/%u/llm-stack/models/gemma4-26b-a4b/mmproj-F16.gguf \
  --host 127.0.0.1 --port 8000 \
  -c 65536 --cache-type-k q8_0 --cache-type-v q8_0 \
  --jinja --no-mmproj-offload -ngl 99 --n-cpu-moe 8 -fa on -np 1
Restart=always
User=%u

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now gemma4-llama
sudo systemctl status gemma4-llama   # active (running) 확인
```
> 3-4의 비전 CUDA 크래시가 재현되면 `--mmproj` 줄을 지우고 재기동해 텍스트 전용으로
> 운영하세요. 구 모델(12B)로 롤백하려면 `sudo systemctl stop gemma4-llama` 후
> `llm-switch.sh use gemma4-12b-legacy`를 쓰면 됩니다.

### 8-5. Tailscale 상시 인증
```bash
sudo tailscale up --ssh --authkey=tskey-auth-xxxxxxxx
```

---

## 9. Slack 게이트웨이 연동

Socket Mode 사용 — 공개 URL 불필요, 방화벽 뒤에서도 작동합니다.

### 9-1. 앱 매니페스트 생성 및 Slack 앱 등록
```bash
hermes slack manifest --agent-view --write
```
1. [api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → **From an app manifest**
2. 워크스페이스 선택 → `~/.hermes/slack-manifest.json` 내용 붙여넣기 → **Create**
3. **Install App to Workspace** → **Bot User OAuth Token**(`xoxb-...`) 복사

### 9-2. Socket Mode 활성화
1. **Settings → Socket Mode** → ON
2. App-Level Token 생성 (`connections:write` 스코프) → `xapp-...` 복사

### 9-3. 필수 확인 사항 (수동 생성 시 누락 주의)
- Bot Token Scopes: `chat:write`, `app_mentions:read`, `channels:history`, `groups:history`, `im:history`, `im:read`, `users:read`, `files:read`, `files:write`
- Event Subscriptions: `message.im`, `message.channels`, `message.groups`, `app_mention`
- **App Home → Messages Tab ON** (안 하면 DM 자체가 차단됨)

### 9-4. 사용자 Member ID 확인
Slack 프로필 → **⋮ → Copy member ID** (예: `U01ABC2DEF3`)

### 9-5. Hermes 설정
```bash
# ~/.hermes/.env
SLACK_BOT_TOKEN=xoxb-your-bot-token-here
SLACK_APP_TOKEN=xapp-your-app-token-here
SLACK_ALLOWED_USERS=U01ABC2DEF3
```

### 9-6. 게이트웨이 시작 및 자동화
```bash
hermes gateway install
sudo hermes gateway install --system
```

### 9-7. 채널에 봇 초대
```
/invite @Hermes Agent
```

---

## 10. Telegram 게이트웨이 연동

### 10-1. 봇 생성
1. Telegram에서 **@BotFather** 검색 → `/newbot`
2. 표시 이름, `bot`으로 끝나는 username 입력
3. 발급된 API 토큰 복사 — 유출 시 `/revoke`로 즉시 폐기

### 10-2. 내 사용자 ID 확인
Telegram에서 **@userinfobot**에게 메시지 → 숫자 ID 회신받음 (봇 토큰의 숫자와 다르니 혼동 주의)

### 10-3. 그룹에서 쓸 경우 — Privacy Mode 해제
1. @BotFather → `/mybots` → 봇 선택 → **Bot Settings → Group Privacy → Turn off**
2. 봇을 그룹에서 제거 후 재초대 (설정 캐시 때문에 필수)

### 10-4. Hermes 설정
```bash
# ~/.hermes/.env
TELEGRAM_BOT_TOKEN=여기에_토큰
TELEGRAM_ALLOWED_USERS=여기에_숫자ID
```

### 10-5. 게이트웨이 시작 및 검증
```bash
hermes gateway install
hermes gateway
```
webhook이 비어있고(`"url":""`) `pending_update_count`가 0인 상태에서 시작하면 깨끗한 상태입니다. Telegram에서 봇에게 메시지를 보내 정상 응답을 확인하세요.

### 10-6. 게이트웨이 상시 운용 시 주의

단일모델 체제라 8-4의 systemd 서비스가 상시 떠 있으면 평소엔 전환 걱정이 없습니다.
다만 **롤백(7-3, `gemma4-12b-legacy`)이나 부록 A의 Qwen 조건부 재도입으로 모델을
바꾸는 동안엔 게이트웨이가 응답 없는 것처럼 보입니다** — 트래픽 없는 시간대에 하세요.
- 여러 사람이 동시에 게이트웨이로 접근하면 `-np 1` 설정이 병목이 될 수 있음 — 이 경우 VRAM 재확인 후 `-np 2` + 컨텍스트 축소 트레이드오프를 검토하세요.

---

## 11. 리소스 운용 및 모델 선택 원칙

단일모델 체제라 평소엔 전환이 필요 없습니다. 26B-A4B 하나로 알림·cron·`/goal`·리서치·
비전·간단한 코딩까지 커버합니다(4장 근거 참고).

| 상황 | 대응 |
|---|---|
| 평소 전체 사용 (알림·cron·`/goal`·리서치·비전·간단한 코딩) | `gemma4`(26B-A4B) 그대로 사용 |
| 26B-A4B에서 문제 발생, 안정 버전으로 급히 되돌려야 함 | `llm-switch.sh use gemma4-12b-legacy`로 롤백 |
| 레포 전체 탐색·멀티스텝 이슈 해결 등 진짜 에이전틱 코딩이 반복적으로 필요해짐 | 4장의 조건(RAM 28GB+ 확보) 재확인 후 부록 A로 Qwen3.6-35B-A3B 조건부 재도입 검토 |

- 장시간 추론 시 `nvidia-smi -l 2`로 온도/메모리 모니터링.
- 모델을 바꿀 때는 항상 `curl http://localhost:8000/v1/models`로 실제 로드된 모델명을 재확인하세요. 포트가 고정돼 있어 겉으로는 구분이 안 됩니다.

---

## 12. 실행 및 테스트

### 12-1. Hermes 실행 (데일리 루틴)
```bash
sudo systemctl status gemma4-llama          # 꺼져있으면 start
curl http://localhost:8000/v1/models        # API 응답 확인
cd ~/hermes-workspace
hermes
```

### 12-2. 기본 응답 및 컨텍스트 확인
```
> 안녕, 너는 지금 어떤 모델로 동작하고 있어? 컨텍스트 길이도 알려줘.
```

### 12-3. 도구별 테스트 체크리스트

**0번(비전)을 가장 먼저 실행하세요** — 3-4의 CUDA 크래시가 우리 카드에서 재현되는지가
이후 운영 방식(비전 포함 vs `--no-mmproj` 텍스트 전용)을 가릅니다.

| # | 테스트 | 프롬프트 예시 | 확인 사항 |
|---|---|---|---|
| 0 | **비전 (최우선)** | 이미지 첨부 후 `이 이미지 설명해줘` | `--mmproj` 로딩이 SIGABRT 없이 되는지 (3-4 크래시 리스크) |
| 1 | 단일 도구 호출 | `오늘 날짜 기준 최신 GPU 뉴스 찾아줘` | 툴콜 JSON 파싱 정상 여부 |
| 2 | 멀티스텝 에이전트 | `GitHub 레포 목록 가져와서 가장 최근 커밋 알려줘` | 도구 선택·순차 계획 능력 |
| 3 | 긴 컨텍스트 | 긴 문서 붙여넣고 `3번째 섹션 수치 다시 말해줘` | 65536 컨텍스트 실제 활용도 |
| 4 | 간단한 코딩 | `피보나치 메모이제이션 구현 + 테스트 코드` | LiveCodeBench급 단일 함수 작성 품질 (4장 근거 확인용) |
| 5 | 메모리 | `내 이름은 윤이고 RTX 4070 SUPER를 써. 기억해줘` → 재시작 후 재질문 | `USER.md` 자동 생성 |
| 6 | 브라우저 | `example.com 접속해서 제목 알려줘` | Playwright 정상 작동 |
| 7 | 생성 폭주 재확인 | README 7.1의 재현 프롬프트로 동일 테스트 | 26B-A4B에서도 폭주 증상이 나오는지(아키텍처가 달라 재현 여부 미지) |

### 12-4. Slack/Telegram 연동 테스트
```bash
hermes gateway start
```
응답이 없으면 `hermes gateway logs`를 확인하세요.

### 12-5. 재부팅 후 자동 복구 검증
1. Windows 재부팅
2. 5분 뒤 Orca에서 Tailscale IP 재접속
3. `systemctl status gemma4-llama` `active (running)` 확인
4. `hermes doctor`로 provider/컨텍스트 65536 유지 확인

---

## 13. 남은 리스크 체크리스트 (v16 갱신)

1. **선제 점검 순서 준수**: GPU 확인 → 메모리 할당 → dpkg → Node 툴체인 → 5장 순서.
2. CUDA 빌드는 `-j` 무제한 병렬 시 OOM으로 컴파일러/WSL2 자체가 죽을 수 있음 — `-j2`부터 시작, 필요시 스왑 추가.
3. WSL2 `E_UNEXPECTED` 크래시는 대개 RAM 소진 — `wsl --shutdown` → `wsl --update` → 재부팅 순으로 복구.
4. YAML config에서 콜론 포함 키는 반드시 따옴표로 감싸기.
5. `n_parallel`을 `auto`로 두면 슬롯 수만큼 KV 캐시가 배로 소비됨 — 1인 사용 환경에선 `-np 1`로 고정.
6. Hermes Agent는 config.yaml `context_length` < 64,000이면 provider 자체를 초기화 거부 — 서버 실제 컨텍스트와 config 값을 반드시 64K 이상으로 일치시킬 것.
7. **[v16] 비전(`--mmproj`) CUDA 크래시 리스크(최우선 확인)**: Gemma4-26B-A4B/31B에서
   SIGABRT 보고 있음(`ggml-org/llama.cpp` #21402, RTX 5090 기준, "not planned"로 종료).
   SFF의 RTX 4070 SUPER에서 재현 여부 미확인 — 12-3의 0번 테스트로 반드시 먼저 검증하고,
   크래시하면 `--no-mmproj` 텍스트 전용으로 운영.
8. **[v16]** Gemma4-26B-A4B(14.2GB, QAT UD-Q4_K_XL)는 SFF 12GB에 단독으로도 안 들어가
   `--n-cpu-moe` 오프로드가 필수 — 시작값 8에서 OOM 여부 보며 5씩 조정(3-4 참고).
9. **[v16]** `--repeat-penalty`는 26B-A4B에서 기본값(비활성)으로 시작 — README 7.1의
   생성 폭주가 이 아키텍처에서도 재현되는지 12-3의 7번 테스트로 확인 후에만 1.1 적용.
10. **[v16]** registry 키 `gemma4`를 신규 26B-A4B로 재사용하므로, 실제 SFF의 현재
    `registry.yaml`에 이미 있는 `gemma4`(12B) 정의와 충돌하지 않는지 적용 전 확인 필수
    (문서 상단 안내 참고).
11. **[v16, 보류]** Qwen3.6-35B-A3B 조건부 재도입 시엔 이전 v15의 리스크가 그대로
    적용됨 — 부록 A 참고: 오프로드 9-10GB(RAM 32GB 하한 필요), MTP+비전 동시 사용
    미검증, 사고 모드 토큰 소진.
12. Slack/Telegram 게이트웨이를 상시 운용할 경우 모델 롤백/재도입 작업과 충돌 가능 — 10-6 참고.
13. Telegram/GitHub 등 토큰은 대화 로그에 노출되는 즉시 폐기·재발급을 기본 원칙으로.
14. Node 버전 24 고정, 임의 업그레이드 금지.
15. Tailscale auth key 만료 시 재발급 필요.

---

## 부록 A. Qwen3.6-35B-A3B 조건부 재도입 (지금은 미설치, v15 계획 보존)

4장 근거대로, **레포 전체 탐색·멀티스텝 이슈 해결 같은 진짜 에이전틱 코딩이 반복적으로
필요해지고 `.wslconfig` RAM을 28GB 이상으로 올릴 수 있을 때만** 아래를 진행하세요.
그 전까지는 실행하지 마세요 — SFF의 WSL RAM 할당(24GB)으로는 부족합니다(3-4 참고).

**다운로드**:
```bash
mkdir -p ~/llm-stack/models/qwen3.6-35b
uvx --from huggingface_hub hf download unsloth/Qwen3.6-35B-A3B-MTP-GGUF \
  --include "*mmproj-F16*" \
  --include "*UD-Q4_K_XL*" \
  --local-dir ~/llm-stack/models/qwen3.6-35b
```

**registry.yaml에 추가**:
```yaml
  qwen35b:
    display_name: "Qwen3.6-35B-A3B (에이전틱 코딩용, 비전+MTP 시도)"
    build: mainline
    model_path: "~/llm-stack/models/qwen3.6-35b/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf"
    mmproj_path: "~/llm-stack/models/qwen3.6-35b/mmproj-F16.gguf"
    port: 8000
    context: 65536
    cache_k: q8_0
    cache_v: q8_0
    extra_flags: "--jinja --mmproj-auto --no-mmproj-offload -ngl 99 --n-cpu-moe 26 --spec-type draft-mtp --spec-draft-n-max 2 -fa on -np 1"
```

**CLI 테스트 시 주의 — 사고 모드 토큰 소진**: Qwen 계열은 답변 전에 긴 `[thinking]` 사고
과정을 생성합니다. `-n`을 2048 이상으로 넉넉히 주고, 빠른 답만 원하면 프롬프트 끝에
`/no_think`를 추가하세요.

**MTP+비전 동시 사용 미검증**: 기동 후 로그에 `n_drafted`/`n_accepted` 값이 안 보이면
현재 빌드에서 MTP+비전 동시 사용이 안 먹히는 것입니다. `extra_flags`에서
`--spec-type draft-mtp --spec-draft-n-max 2` 두 토큰만 지우고 재기동하면 비전 전용으로
정상 동작합니다.

**전환**: `llm-switch.sh use qwen35b`, VRAM은 `nvidia-smi`로 12GB 초과 여부 확인하며
`--n-cpu-moe`를 30, 35...로 올려 재시도. 상시 서비스(8-4)와 병행 시 `sudo systemctl stop
gemma4-llama` 후 전환하고, 복귀 시 `llm-switch.sh use gemma4` 또는
`sudo systemctl start gemma4-llama`.
