# Hermes Agent 로컬 LLM 구축 가이드 (v15, Gemma4-12B + Qwen3.6-35B-A3B 2모델 체제)

> 대상 하드웨어: AMD Ryzen 9 7900 / RTX 4070 SUPER 12GB / DDR5 32GB / Fractal Design Terra (ITX)
> 구성: 연구실 PC(Windows 11 + WSL2 Ubuntu 24.04, 호스트) ↔ 집 데스크톱(Tailscale + Orca SSH, 클라이언트)
>
> v14(Ternary Bonsai 27B 메인 전환판)에서 이어지는 세션 종합 개정판입니다. 이번 개정의 핵심은 **모델 구성을 단순화**한 것입니다 — Bonsai 27B와 Ollama 기반 Hermes 4/3 폴백 조합을 모두 걷어내고, **비전 입력이 가능한 Gemma4-12B를 메인으로, 에이전틱 코딩에 특화된 Qwen3.6-35B-A3B(MoE)를 두 번째 모델로** 두는 2모델 체제로 정리했습니다. 두 모델 모두 llama.cpp 단일 빌드로 구동하고, 포트를 8000번으로 통일해 전환이 단순해졌습니다.
>
> 위에서 아래로 그대로 실행하면 재작업 없이 완성됩니다.

---

> **문서 상태 안내 (README 우선)**: 이 문서는 외부에서 작성된 원본 구축 가이드(v15)를 그대로
> 첨부한 것이며, 현재 운영 환경 기준으로 전부 검증된 것은 아닙니다. `README.md`와 내용이
> 충돌하면 **`README.md`가 우선**합니다. 특히 아래 항목은 실제로 따라 하기 전 재확인하세요:
> - **모델 quant**: 이 문서는 `unsloth/gemma-4-12b-it-GGUF`의 `UD-Q4_K_XL` 양자화를 받도록
>   안내하지만, README 기준 현재 운영 모델명은 **Gemma 4-12B (IT, QAT Q4_0)**입니다. 같은
>   빌드가 아닐 수 있으니 다운로드 전에 확인하세요.
> - **`--repeat-penalty`**: 이 문서의 registry.yaml 예시에는 값이 없어 기본값 1.0으로
>   동작합니다. README 7.1의 현재 운영 방침(기본 1.0, 폭주 증상 재현 시 1.1로 전환)과는
>   방향은 같지만, registry 키 이름(`gemma4-12b` 등)을 포함한 세부 구조가 README가 실제로
>   쓰는 설정과 다를 수 있습니다.
> - 그 외 Slack/Telegram 연동 등 나머지 절차도 미검증 상태이니 단계별로 확인하며 진행하세요.

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

## 3. 하드웨어 제약과 VRAM 계산 (v15: 2모델 체제 기준으로 갱신)

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

Qwen3.6-35B-A3B는 MoE(Mixture of Experts) 구조라, 전문가(expert) 레이어의 일부를 VRAM이 아니라 **시스템 RAM에 올릴 수 있는 `--n-cpu-moe` 플래그**가 VRAM 계산에 추가로 개입합니다. 이 숫자를 올릴수록 VRAM 사용량은 줄고 속도는 소폭 느려집니다. Dense 모델(Gemma4-12B)에는 해당하지 않는 옵션입니다.

### 3-3. Hermes Agent의 컨텍스트 하드 체크

Hermes Agent는 **64,000 토큰 미만 컨텍스트로 등록된 모델은 provider 초기화 자체를 거부**합니다(`config.yaml`의 `context_length` 필드 기준이며, 서버가 실제로 그 값을 감당하는지와 무관하게 하드코딩된 체크입니다). 즉 서버도 64K 이상으로 실제 기동해야 하고, config에도 64K 이상으로 기입해야 둘 다 통과합니다.

### 3-4. 실측 VRAM 표

| 모델 | 조건 | 실측/추정 VRAM |
|---|---|---|
| Gemma4-12B (Q4_K_XL, 비전 포함) | `-c 131072 -np 1` | 약 8.5~9GB / 12GB (여유 약 3~3.5GB) |
| Qwen3.6-35B-A3B (UD-Q4_K_XL, 비전+MTP) | `-c 131072 --n-cpu-moe 26 -np 1` | 12GB 근접 (커뮤니티 실측 45~110 tok/s대) |
| (참고, 사용 중단) Ternary Bonsai 27B (Q2_0) | `-c 65536 --parallel 1` | 약 9.3GB — 비전 미지원으로 v15에서 제외 |

**결론**: 두 모델(Gemma4-12B, Qwen3.6-35B-A3B) 모두 단독으로는 12GB 안에 들어오지만, **동시 상주는 불가능**합니다. 7장의 전환 스크립트로 번갈아 씁니다.

---

## 4. 모델 선정 — 왜 이 2개인가 (v15)

| 모델 | 역할 | 실행 방식 | 근거 |
|---|---|---|---|
| **Gemma4-12B** | 메인 | llama-server (systemd 상시구동, 포트 8000) | 비전 지원, 8.5~9GB로 VRAM 여유 확보, 서술·한국어·이미지 설명에 안정적 |
| **Qwen3.6-35B-A3B** | 서브 (에이전틱 코딩용) | llama-server (온디맨드 전환, 포트 8000 공유) | SWE-bench Verified 73.4, Terminal-Bench 2.0 51.5로 에이전틱 벤치마크 최고치, 12GB에서 실측 검증 다수 |

### 검토 후 제외한 모델들

- **Ternary Bonsai 27B**: 코딩·수학은 강했지만 비전 미지원이라, "이미지 입력이 기본"이라는 이번 세션의 요구사항과 맞지 않아 제외.
- **Gemma4-26B-A4B**: 같은 Gemma4 계열의 더 큰 MoE 버전이지만, 의외로 SWE-bench Verified가 17.4점에 그쳐(Qwen3.6-35B-A3B의 73.4점과 4배 이상 격차) 에이전틱 용도로는 부적합 판정.
- **Hermes 4/3 (Ollama)**: Bonsai의 툴콜 폴백용이었으나, Bonsai 자체를 빼면서 폴백 체인의 필요성이 사라져 함께 정리.

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

두 모델 다 llama-server 단일 빌드로 띄우므로, 마법사에서는 항상 **Custom (OpenAI-compatible API)** 를 선택합니다. 아직 6장에서 서버를 안 띄웠다면 이 단계는 잠시 건너뛰고, 6장 완료 후 `/model`에서 등록해도 됩니다.

```
Choose a provider:
  Nous Portal          ← 선택 금지 (클라우드)
  Nous Subscription    ← 선택 금지 (클라우드, 유료)
→ Custom (OpenAI-compatible API)   ← 선택
```
```
API base URL: http://localhost:8000/v1
API key: (비워두고 Enter)
Detected model: gemma-4-12b-it (예시) — Use this model? Y
Context length in tokens: 131072
```

**Terminal Backend**: Docker를 설치했으면 `docker`, 아니면 `local` 유지.
**Messaging Platforms**: 스킵 (9~10장에서 별도 설정).
**Web Search & Extract**: `DuckDuckGo (ddgs)` 추천.
**Browser/Vision/TTS**: 기본값 유지 — 두 모델 다 비전 지원이므로 Vision 관련 옵션은 켜두세요.

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

**Gemma4-12B**
```bash
mkdir -p ~/llm-stack/models/gemma4-12b
uvx --from huggingface_hub hf download unsloth/gemma-4-12b-it-GGUF \
  --include "*mmproj-F16*" \
  --include "*UD-Q4_K_XL*" \
  --local-dir ~/llm-stack/models/gemma4-12b
```

**Qwen3.6-35B-A3B (MTP + 비전 통합본)**
```bash
mkdir -p ~/llm-stack/models/qwen3.6-35b
uvx --from huggingface_hub hf download unsloth/Qwen3.6-35B-A3B-MTP-GGUF \
  --include "*mmproj-F16*" \
  --include "*UD-Q4_K_XL*" \
  --local-dir ~/llm-stack/models/qwen3.6-35b
```

### 6-3. 단발성 CLI 테스트 — ⚠️ 사고 모드 토큰 소진 주의

Qwen 계열은 답변 전에 긴 `[thinking]` 사고 과정을 생성합니다. `-n`(토큰 한도)이 작으면 생각만 하다가 실제 답변을 못 내고 끊깁니다.
```bash
cd ~/llama.cpp
./build/bin/llama-cli \
  -m ~/llm-stack/models/qwen3.6-35b/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf \
  -cnv --jinja \
  -p "간단한 인사말을 해줘." \
  -n 2048 --temp 0.7 --top-p 0.95 --top-k 20 -ngl 99
```
- `-n`을 2048 이상으로 넉넉히 줄 것
- 사고 과정 없이 빠른 답만 원하면 프롬프트 끝에 `/no_think` 추가
- `-cnv --jinja`로 모델 내장 채팅 템플릿을 적용해야 사고 블록과 답변이 깔끔히 분리됨

---

## 7. registry.yaml 및 llm-switch.sh — 2모델 전환 체계

### 7-1. registry.yaml 최종본

```yaml
models:
  gemma4-12b:
    display_name: "Gemma4-12B (메인, 비전 지원)"
    build: mainline
    model_path: "~/llm-stack/models/gemma4-12b/gemma-4-12b-it-UD-Q4_K_XL.gguf"
    mmproj_path: "~/llm-stack/models/gemma4-12b/mmproj-F16.gguf"
    port: 8000
    context: 131072
    cache_k: q8_0
    cache_v: q8_0
    extra_flags: "--jinja --no-mmproj-offload -ngl 99 -fa on -np 1"

  qwen35b:
    display_name: "Qwen3.6-35B-A3B (에이전틱 코딩용, 비전+MTP 시도)"
    build: mainline
    model_path: "~/llm-stack/models/qwen3.6-35b/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf"
    mmproj_path: "~/llm-stack/models/qwen3.6-35b/mmproj-F16.gguf"
    port: 8000
    context: 131072
    cache_k: q8_0
    cache_v: q8_0
    extra_flags: "--jinja --mmproj-auto --no-mmproj-offload -ngl 99 --n-cpu-moe 26 --spec-type draft-mtp --spec-draft-n-max 2 -fa on -np 1"

default_model: gemma4-12b
```

> `qwen35b` 기동 후 로그에 `n_drafted`/`n_accepted` 값이 안 보이면, 현재 빌드에서 MTP+비전 동시 사용이 아직 안 먹히는 것입니다. 이 경우 `extra_flags`에서 `--spec-type draft-mtp --spec-draft-n-max 2` 두 토큰만 지우고 재기동하면 비전 전용으로 정상 동작합니다.

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

### 7-3. 전환 명령 및 검증

```bash
~/llm-stack/bin/llm-switch.sh list
~/llm-stack/bin/llm-switch.sh use gemma4-12b
curl http://localhost:8000/v1/models

~/llm-stack/bin/llm-switch.sh use qwen35b
curl http://localhost:8000/v1/models
nvidia-smi        # VRAM이 12GB를 넘지 않는지 확인, 넘으면 --n-cpu-moe 값을 30 정도로 올려 재시도
```

### 7-4. Hermes와의 연동

두 모델 다 `port: 8000`으로 통일해뒀으므로 `~/.hermes/.env`는 한 번만 설정하면 됩니다.
```bash
# ~/.hermes/.env
LLM_BASE_URL=http://localhost:8000/v1
```
모델을 바꿀 때마다 `.env`를 고칠 필요 없이, `llm-switch.sh use <키>`만 실행하고 Hermes를 재시작(또는 `/model` 재선택)하면 됩니다.

### 7-5. 다른 provider/모델을 추후 추가하는 법 (범용 절차)

이 2모델 외에 나중에 다른 로컬/클라우드 모델을 더 추가하고 싶다면 동일 패턴을 씁니다.

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

### 8-4. Gemma4-12B를 systemd로 상시 구동

메인 모델(Gemma4-12B)만 상시 서비스로 등록해두고, Qwen3.6-35B-A3B는 필요할 때만 `llm-switch.sh use qwen35b`로 온디맨드 전환하는 방식을 권장합니다.

```bash
sudo tee /etc/systemd/system/gemma4-llama.service <<'EOF'
[Unit]
Description=Gemma4-12B llama-server
After=network.target

[Service]
ExecStart=/home/%u/llama.cpp/build/bin/llama-server \
  -m /home/%u/llm-stack/models/gemma4-12b/gemma-4-12b-it-UD-Q4_K_XL.gguf \
  --mmproj /home/%u/llm-stack/models/gemma4-12b/mmproj-F16.gguf \
  --host 127.0.0.1 --port 8000 \
  -c 131072 --cache-type-k q8_0 --cache-type-v q8_0 \
  --jinja --no-mmproj-offload -ngl 99 -fa on -np 1
Restart=always
User=%u

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now gemma4-llama
sudo systemctl status gemma4-llama   # active (running) 확인
```
> Qwen3.6-35B-A3B로 전환할 때는 `sudo systemctl stop gemma4-llama` 후 `llm-switch.sh use qwen35b`를 실행하고, 다시 메인으로 돌아올 때는 `llm-switch.sh use gemma4-12b` 또는 `sudo systemctl start gemma4-llama`를 쓰면 됩니다.

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

### 10-6. 게이트웨이 상시 운용 vs 모델 전환 충돌 주의

게이트웨이는 상시 프로세스이므로, 7~8장의 모델 전환과 겹칠 수 있습니다.
- 게이트웨이를 상시 서비스로 쓸 계획이면 메인 모델(Gemma4-12B)도 상시 구동 유지, Qwen3.6-35B-A3B 전환은 트래픽 없는 시간대에만.
- 여러 사람이 동시에 게이트웨이로 접근하면 `-np 1` 설정이 병목이 될 수 있음 — 이 경우 VRAM 재확인 후 `-np 2` + 컨텍스트 축소 트레이드오프를 검토하세요.

---

## 11. 리소스 운용 및 모델 선택 원칙

| 상황 | 실행할 명령 | 근거 |
|---|---|---|
| 평소 서술형·비전·한국어 응답 | `llm-switch.sh use gemma4-12b` | 8.5~9GB로 VRAM 여유, 안정적 |
| GitHub 이슈 해결, 터미널 자동화, 멀티스텝 에이전틱 코딩 | `llm-switch.sh use qwen35b` | SWE-bench 73.4, Terminal-Bench 51.5 |

- 두 모델 동시 상주는 VRAM 부족으로 불가 — 전환 전 반드시 `pkill -f llama-server` 또는 `llm-switch.sh use`로 정리 후 새 모델을 띄웁니다.
- 장시간 추론 시 `nvidia-smi -l 2`로 온도/메모리 모니터링.
- 전환 후에는 항상 `curl http://localhost:8000/v1/models`로 실제 로드된 모델명을 재확인하세요. 포트가 고정돼 있어 겉으로는 구분이 안 됩니다.

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

| # | 테스트 | 프롬프트 예시 | 확인 사항 |
|---|---|---|---|
| 1 | 단일 도구 호출 | `오늘 날짜 기준 최신 GPU 뉴스 찾아줘` | 툴콜 JSON 파싱 정상 여부 |
| 2 | 멀티스텝 에이전트 | `GitHub 레포 목록 가져와서 가장 최근 커밋 알려줘` | 도구 선택·순차 계획 능력 (Qwen35B 강점 확인용) |
| 3 | 긴 컨텍스트 | 긴 문서 붙여넣고 `3번째 섹션 수치 다시 말해줘` | 131072 컨텍스트 실제 활용도 |
| 4 | 비전 | 이미지 첨부 후 `이 이미지 설명해줘` | mmproj 정상 작동 (두 모델 공통) |
| 5 | 코딩 | `피보나치 메모이제이션 구현 + 테스트 코드` | Qwen35B 강점 영역 확인 |
| 6 | 메모리 | `내 이름은 윤이고 RTX 4070 SUPER를 써. 기억해줘` → 재시작 후 재질문 | `USER.md` 자동 생성 |
| 7 | 브라우저 | `example.com 접속해서 제목 알려줘` | Playwright 정상 작동 |
| 8 | 모델 전환 | `llm-switch.sh use qwen35b` 후 1~5번 재실행 | 전환 후에도 동일 품질 유지되는지 |

### 12-4. Slack/Telegram 연동 테스트
```bash
hermes gateway start
```
응답이 없으면 `hermes gateway logs`를 확인하세요.

### 12-5. 재부팅 후 자동 복구 검증
1. Windows 재부팅
2. 5분 뒤 Orca에서 Tailscale IP 재접속
3. `systemctl status gemma4-llama` `active (running)` 확인
4. `hermes doctor`로 provider/컨텍스트 131072 유지 확인

---

## 13. 남은 리스크 체크리스트 (v15 갱신)

1. **선제 점검 순서 준수**: GPU 확인 → 메모리 할당 → dpkg → Node 툴체인 → 5장 순서.
2. CUDA 빌드는 `-j` 무제한 병렬 시 OOM으로 컴파일러/WSL2 자체가 죽을 수 있음 — `-j2`부터 시작, 필요시 스왑 추가.
3. WSL2 `E_UNEXPECTED` 크래시는 대개 RAM 소진 — `wsl --shutdown` → `wsl --update` → 재부팅 순으로 복구.
4. YAML config에서 콜론 포함 키는 반드시 따옴표로 감싸기.
5. Qwen 계열 추론 모델은 `-n` 토큰 한도가 작으면 사고 과정만 하다 끝남 — 넉넉한 `-n` 또는 `/no_think` 사용.
6. `n_parallel`을 `auto`로 두면 슬롯 수만큼 KV 캐시가 배로 소비됨 — 1인 사용 환경에선 `-np 1`로 고정.
7. Hermes Agent는 config.yaml `context_length` < 64,000이면 provider 자체를 초기화 거부 — 서버 실제 컨텍스트와 config 값을 반드시 64K 이상으로 일치시킬 것.
8. **[v15]** Gemma4-12B(8.5~9GB)와 Qwen3.6-35B-A3B(12GB 근접)는 동시 상주 불가 — 7장의 `llm-switch.sh`로 순차 운용.
9. **[v15]** Qwen3.6-35B-A3B의 `--n-cpu-moe` 값은 컨텍스트 길이·카드에 따라 재조정 필요 — 시작값 26에서 OOM 여부 보며 5씩 조정.
10. **[v15]** `--mmproj`와 `--spec-type draft-mtp` 동시 사용은 최신 llama.cpp 빌드(b9620+)에서만 보고된 사례이며, 검증 사례가 많지 않으니 로그의 `n_drafted`/`n_accepted`로 반드시 재확인.
11. **[v15]** 두 모델 다 `port: 8000`으로 통일했으므로, 전환 후 `curl .../v1/models`로 실제 로드된 모델을 재확인하는 습관 필수 — 포트만으로는 구분 불가.
12. Slack/Telegram 게이트웨이를 상시 운용할 경우 7~8장의 모델 전환과 충돌 가능 — 10-6 참고.
13. Telegram/GitHub 등 토큰은 대화 로그에 노출되는 즉시 폐기·재발급을 기본 원칙으로.
14. Node 버전 24 고정, 임의 업그레이드 금지.
15. Tailscale auth key 만료 시 재발급 필요.
