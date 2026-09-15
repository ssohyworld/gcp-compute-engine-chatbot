# 🌐 GCP Compute Engine 기반 Gemini 웹 챗봇 서비스

Google Cloud Platform(GCP) Compute Engine 인스턴스에 배포된 **FastAPI 기반 실시간 Gemini AI 웹 챗봇** 프로젝트입니다.  
GCP Secret Manager를 통해 보안 API 키를 안전하게 주입받으며, Nginx 리버스 프록시와 Let's Encrypt 공인 SSL 인증서를 적용하여 **보안 HTTPS(HTTP/2)** 통신 환경을 구축하였습니다.

---

## 🔗 서비스 접속 링크
- 🔒 **공식 HTTPS 서비스 주소**: **`https://<YOUR_VM_IP>.sslip.io`**
- *(일반 HTTP 또는 포트 80으로 접근 시에도 HTTPS로 자동 301 리다이렉트됩니다.)*

---

## 🏗️ 시스템 아키텍처 (Architecture)

```
[ 사용자 웹 브라우저 ]
        │  HTTPS (포트 443 / TLS 1.3)
        ▼
[ GCP Compute Engine (us-central1-a) ]
  ├── [ 방화벽 (Firewall) ] : 80(HTTP), 443(HTTPS) 인바운드 허용
  │
  ├── [ Nginx Web Server / Reverse Proxy ]
  │     ├── 포트 80  : HTTPS(443)로 301 강제 리다이렉트
  │     └── 포트 443 : Let's Encrypt SSL 종료 (SSL Termination)
  │                   및 SSE 스트리밍 버퍼링 해제 (proxy_buffering off)
  │                   │
  │                   ▼ (127.0.0.1:8000 프록시 패스)
  │
  ├── [ FastAPI / Uvicorn 백엔드 (chatbot.service) ]
  │     ├── Google GenAI SDK (Gemini 3.8 Flash, 3.7 Flash 등)
  │     ├── SSE (Server-Sent Events) 실시간 스트리밍
  │     └── Web Search Grounding 연동
  │
  └── [ GCP Secret Manager ]
        └── projects/<YOUR_PROJECT_NUMBER>/secrets/GEMINI_API_KEY
            (인스턴스 내부 /etc/chatbot.env 권한 600 보안 주입)
```

---

## 🔐 HTTP vs HTTPS 프로토콜의 차이점

본 프로젝트는 초기 단계에서 `HTTP (포트 8000)` 기반으로 구동되었으나, 이후 보안성과 신뢰성을 위해 `HTTPS (포트 443)`로 전면 전환되었습니다. 두 프로토콜의 핵심 차이점은 다음과 같습니다:

| 비교 항목 | HTTP (HyperText Transfer Protocol) | HTTPS (HTTP Secure / over TLS) |
| :--- | :--- | :--- |
| **기본 포트** | `TCP 80` (또는 사용자 지정 포트 8000) | `TCP 443` |
| **데이터 암호화** | **평문(Plaintext)** 전송 | **SSL/TLS 암호화(Symmetric/Asymmetric Key)** 전송 |
| **도청/스니핑 위험** | 통신 경로의 네트워크 패킷 감청 시 대화 내용/헤더 원본 노출 | 패킷을 가로채도 암호문으로만 보여 **도청 불가능** |
| **위변조 (무결성)** | 중간자 공격(MITM)을 통한 데이터 변조에 취약 | 메시지 인증 코드(MAC)로 **데이터 위·변조 즉시 감지** |
| **서버 인증 (신뢰성)** | 접속한 서버가 실제 신뢰할 수 있는 서버인지 증명 불가 | **공인 CA 인증서**를 통해 신뢰할 수 있는 서버임을 보증 (자물쇠 아이콘) |
| **웹 프로토콜 성능** | 주로 HTTP/1.1 사용 | **HTTP/2 다중화(Multiplexing)** 지원으로 로딩 속도 향상 |
| **브라우저 정책** | 최신 브라우저에서 **'주의 요함 / 안전하지 않음'** 경고 표시 | **보안 연결(초록색 자물쇠)** 정상 표시 및 보안 기능(Web Crypto 등) 허용 |

---

## 🛠️ HTTPS 전환을 위해 도입된 핵심 기술 및 구현 원리

HTTP에서 공인 HTTPS 환경으로 무중단 전환하기 위해 다음과 같은 인프라 및 소프트웨어 기술들이 적용되었습니다:

### 1. Nginx 리버스 프록시 (Reverse Proxy) & SSL Termination
- **역할**: 클라이언트의 최초 진입점으로서 SSL/TLS 핸드셰이크 및 암호화/복호화를 전담(SSL Termination)하고, 내부 백엔드 FastAPI(`127.0.0.1:8000`)로 안전하게 요청을 중계합니다.
- **SSE 스트리밍 최적화 (`proxy_buffering off;`)**:
  - Gemini AI의 실시간 토큰 출력(Server-Sent Events)이 Nginx의 응답 버퍼에 묶여 지연되는 현상을 방지하기 위해 버퍼링을 해제하여 실시간 타이핑 효과를 구현했습니다.

### 2. 와일드카드 DNS 서비스 (`sslip.io`)
- **도입 이유**: 고정 도메인을 별도로 구매하지 않은 상태의 GCP 공인 IP(`YOUR_VM_IP`)에 대해 공인 SSL 인증서를 발급받기 위함.
- **원리**: `<YOUR_VM_IP>.sslip.io`로 들어오는 모든 DNS 쿼리를 자동으로 해당 IP로 라우팅해주는 오픈 DNS 서비스입니다.

### 3. Let's Encrypt CA & Certbot 자동화
- **공인 인증서 발급**: 글로벌 신뢰 공인 인증기관(CA)인 Let's Encrypt의 ACME 프로토콜(HTTP-01 챌린지)을 이용하여 `<YOUR_VM_IP>.sslip.io` 도메인에 대한 공인 SSL/TLS 인증서를 무료 발급받았습니다.
- **자동 갱신 (Certbot Timer)**: 90일 만료 주기 이전에 `certbot.timer` 데몬이 자동으로 인증서를 갱신하도록 구성되었습니다.

### 4. HTTP 301 영구 리다이렉트 (Permanent Redirect)
- 일반 `http://` 접속(포트 80)으로 들어오는 모든 트래픽을 즉시 `https://` (포트 443)로 강제 전환하여 보안 취약점을 원천 차단했습니다.

### 5. GCP Compute Engine 방화벽 (VPC Firewall Rules)
- `allow-chatbot-web` 인바운드 규칙을 생성하여 표준 웹 트래픽(`tcp:80`, `tcp:443`)을 허용하고 인스턴스에 `http-server`, `https-server` 태그를 부여했습니다.

### 6. GCP Secret Manager 기반 보안 키 관리
- `GEMINI_API_KEY`를 코드나 Git 저장소에 노출하지 않고, GCP Secret Manager(`projects/<YOUR_PROJECT_NUMBER>/secrets/GEMINI_API_KEY`)에서 직접 조회하여 인스턴스 내부의 root 전용 보안 파일(`/etc/chatbot.env`, `chmod 600`)로 안전하게 주입했습니다.

### 7. systemd 백그라운드 서비스 데몬화
- FastAPI 애플리케이션을 `systemd` 서비스(`chatbot.service`)로 등록하여 VM 재부팅 시 자동 실행 및 장애 발생 시 자동 복구(`Restart=always`)를 보장합니다.

---

## 📁 프로젝트 파일 구조

```
gcp-compute-engine-chatbot/
├── main.py                    # FastAPI 서버, Gemini SDK 연동, 세션 및 스트리밍 API
├── requirements.txt           # Python 필수 패키지 목록
├── run.sh                     # 로컬 실행 스크립트
├── README.md                  # 애플리케이션 세부 설명서
├── .gitignore                 # Git 제외 설정 (보안 키, 세션 데이터, 캐시 등 차단)
├── static/                    # 프론트엔드 정적 파일
│   ├── index.html             # 웹 챗봇 메인 UI
│   ├── style.css              # 스타일시트 (다크/라이트 모드, 반응형 레이아웃)
│   └── app.js                 # 실시간 SSE 챗봇 상호작용 및 UI 로직
└── data/
    └── .gitkeep               # 세션 디렉터리 유지 (sessions.json은 .gitignore로 제외)
```

---

## 🚀 로컬 환경 실행 방법

```bash
# 1. 디렉터리 이동
cd gcp-compute-engine-chatbot

# 2. 가상환경 생성 및 활성화
python3 -m venv venv
source venv/bin/activate  # macOS / Linux

# 3. 의존성 패키지 설치
pip install -r requirements.txt

# 4. Gemini API Key 환경변수 설정
export GEMINI_API_KEY="your-gemini-api-key"

# 5. 서버 실행
./run.sh
# 또는 python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 🧪 API 엔드포인트 명세

- **`GET /`** : 웹 챗봇 프론트엔드 UI 페이지
- **`GET /api/status`** : 시스템 상태, API 키 구성 상태, 활성 모델 확인
- **`GET /api/models`** : 사용 가능한 Gemini 모델 목록 조회 (`gemini-3.8-flash`, `gemini-3.7-flash` 등)
- **`POST /api/chat/stream`** : 실시간 Server-Sent Events (SSE) 대화 스트리밍
- **`GET /api/sessions`** : 저장된 대화 세션 목록 조회
- **`POST /api/sessions`** : 신규 세션 생성 및 대화 저장
