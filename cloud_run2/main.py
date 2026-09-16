import os
import json
import uuid
import asyncio
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Google Cloud Auth & Google GenAI SDK (Vertex AI / ADC Mode)
import google.auth
from google.auth.exceptions import DefaultCredentialsError
from google import genai
from google.genai import types
from google.genai.errors import APIError

app = FastAPI(
    title="Gemini Web Chatbot (Cloud Run - ADC Mode)",
    description="GCP Cloud Run 기반 Gemini AI 실시간 웹 챗봇 서비스 (Application Default Credentials 인증)",
    version="2.0.0"
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 프로젝트 디렉터리 경로
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
SESSIONS_FILE = DATA_DIR / "sessions.json"

# ============================================================
# ADC (Application Default Credentials) 자격 증명 관리
# ============================================================
_CACHED_GENAI_CLIENT: Optional[genai.Client] = None
_CACHED_PROJECT_ID: Optional[str] = None
_CACHED_LOCATION: Optional[str] = None

def get_adc_info() -> Dict[str, Any]:
    """
    ADC(애플리케이션 기본 사용자 인증 정보) 상태 및 프로젝트 정보를 감지합니다.
    - Cloud Run: 메타데이터 서버를 통해 인스턴스 서비스 계정 자격 증명 자동 획득
    - 로컬 개발 환경: gcloud auth application-default login 자격 증명 자동 획득
    """
    global _CACHED_PROJECT_ID, _CACHED_LOCATION
    
    # 1. 위치(Region) 설정: 기본값 global (최신 Gemini 모델 전역 지원)
    location = os.environ.get("GOOGLE_CLOUD_LOCATION") or os.environ.get("GCP_REGION") or "global"
    _CACHED_LOCATION = location

    # 2. Google ADC 자격 증명 및 프로젝트 감지
    try:
        creds, detected_project = google.auth.default()
        creds_type = creds.__class__.__name__
        service_account = getattr(creds, "service_account_email", None)

        project_id = (
            os.environ.get("GOOGLE_CLOUD_PROJECT")
            or os.environ.get("GCP_PROJECT")
            or detected_project
            or "iceu-songpa15"
        )
        _CACHED_PROJECT_ID = project_id

        return {
            "adc_configured": True,
            "auth_mode": "ADC (Application Default Credentials)",
            "project_id": project_id,
            "location": location,
            "credentials_type": creds_type,
            "service_account": service_account or "Default Compute SA",
            "status": "authenticated"
        }
    except DefaultCredentialsError as e:
        return {
            "adc_configured": False,
            "auth_mode": "ADC (Application Default Credentials)",
            "project_id": os.environ.get("GOOGLE_CLOUD_PROJECT", "UNKNOWN"),
            "location": location,
            "credentials_type": "None",
            "service_account": "None",
            "status": f"unauthenticated: {str(e)}"
        }
    except Exception as e:
        return {
            "adc_configured": False,
            "auth_mode": "ADC (Application Default Credentials)",
            "project_id": "UNKNOWN",
            "location": location,
            "credentials_type": "Error",
            "service_account": "None",
            "status": f"error: {str(e)}"
        }

def get_genai_client() -> genai.Client:
    """
    ADC를 활용하여 Vertex AI 기반 Google GenAI Client를 초기화합니다.
    API 키 주입이 전혀 필요하지 않습니다.
    """
    global _CACHED_GENAI_CLIENT
    if _CACHED_GENAI_CLIENT:
        return _CACHED_GENAI_CLIENT

    adc_info = get_adc_info()
    if not adc_info["adc_configured"]:
        raise HTTPException(
            status_code=500,
            detail=(
                "Google Cloud ADC(애플리케이션 기본 자격 증명)를 찾을 수 없습니다. "
                "로컬인 경우 'gcloud auth application-default login'을 실행하거나, "
                "Cloud Run의 경우 서비스 계정 권한(roles/aiplatform.user)을 확인하세요."
            )
        )

    project_id = adc_info["project_id"]
    location = adc_info["location"]

    try:
        # Vertex AI 백엔드로 ADC 자동 연동
        client = genai.Client(
            vertexai=True,
            project=project_id,
            location=location
        )
        _CACHED_GENAI_CLIENT = client
        print(f"[INFO] Google GenAI Client (Vertex AI / ADC) 생성 완료 [Project: {project_id}, Location: {location}]")
        return client
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Vertex AI GenAI Client 초기화 실패: {str(e)}"
        )

# 세션 데이터 관리
def load_sessions() -> Dict[str, Any]:
    if SESSIONS_FILE.exists():
        try:
            with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_sessions(sessions: Dict[str, Any]):
    with open(SESSIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(sessions, f, ensure_ascii=False, indent=2)

# 지원 모델 목록 (Vertex AI 최신 모델)
AVAILABLE_MODELS = [
    {
        "id": "gemini-3.8-flash",
        "name": "Gemini 3.8 Flash",
        "badge": "추천 / 최신 모델",
        "tag": "Next-Gen Flash",
        "description": "최고의 반응 속도와 강력한 다목적 추론 능력을 제공하는 차세대 최신 Flash 모델입니다.",
        "is_default": True,
        "speed": "초고속",
        "reasoning": "최상급"
    },
    {
        "id": "gemini-3.7-flash",
        "name": "Gemini 3.7 Flash",
        "badge": "안정적 고속",
        "tag": "Stable Flash",
        "description": "균형 잡힌 품질과 뛰어난 가성비 및 일관된 응답을 제공하는 고성능 모델입니다.",
        "is_default": False,
        "speed": "고속",
        "reasoning": "고급"
    },
    {
        "id": "gemini-2.5-flash",
        "name": "Gemini 2.5 Flash",
        "badge": "경량 표준",
        "tag": "Standard Flash",
        "description": "일상적인 대화 및 요약 작업에 적합한 표준 경량 모델입니다.",
        "is_default": False,
        "speed": "매우 빠름",
        "reasoning": "표준"
    },
    {
        "id": "gemini-2.5-pro",
        "name": "Gemini 2.5 Pro",
        "badge": "심층 추론",
        "tag": "Pro Reasoning",
        "description": "복잡한 코딩, 논리적 수학 문제 및 심층 분석에 최적화된 플래그십 프로 모델입니다.",
        "is_default": False,
        "speed": "보통",
        "reasoning": "최상급"
    }
]

# Request / Response Pydantic 모델
class AttachedFile(BaseModel):
    filename: str
    content: str

class ChatMessage(BaseModel):
    role: str = Field(..., description="'user' 또는 'model'")
    content: str = Field(..., description="메시지 내용")

class ChatRequest(BaseModel):
    model: str = Field(default="gemini-3.8-flash", description="사용할 Gemini 모델")
    messages: List[ChatMessage] = Field(..., description="대화 메시지 히스토리")
    attached_files: Optional[List[AttachedFile]] = Field(default=None, description="첨부 파일 목록")
    system_instruction: Optional[str] = Field(default=None, description="시스템 지침")
    use_web_search: Optional[bool] = Field(default=True, description="Google 검색 연동 활성화 여부")
    temperature: Optional[float] = Field(default=0.7, ge=0.0, le=2.0)
    top_p: Optional[float] = Field(default=0.95, ge=0.0, le=1.0)

class SessionCreateUpdate(BaseModel):
    id: Optional[str] = None
    user_id: Optional[str] = None
    title: str
    model: str = "gemini-3.8-flash"
    messages: List[ChatMessage] = []

def get_request_user_id(request: Request, x_user_id: Optional[str] = None) -> str:
    """요청자 고유 식별자(user_id) 추출"""
    if x_user_id and x_user_id.strip():
        return x_user_id.strip()
    query_user = request.query_params.get("user_id")
    if query_user and query_user.strip():
        return query_user.strip()
    client_host = request.client.host if request.client else "anonymous"
    return f"anon_{client_host}"

# --- API Endpoints ---

@app.get("/healthz")
@app.get("/api/health")
def health_check():
    """Cloud Run 상태 점검(Liveness / Startup Probe)용 엔드포인트"""
    return {
        "status": "ok",
        "service": "gemini-cloud-run-chatbot-adc",
        "auth_mode": "ADC"
    }

@app.get("/api/status")
def get_system_status():
    """시스템 상태 및 ADC 자격 증명 세부 정보 반환"""
    adc = get_adc_info()
    return {
        "status": "healthy" if adc["adc_configured"] else "missing_credentials",
        "api_key_configured": adc["adc_configured"],  # 프론트엔드 호환성 유지
        "api_key_source": "ADC (Google Cloud IAM)",
        "auth_mode": adc["auth_mode"],
        "project_id": adc["project_id"],
        "location": adc["location"],
        "credentials_type": adc["credentials_type"],
        "service_account": adc["service_account"],
        "default_model": "gemini-3.8-flash",
        "web_search_available": True,
        "environment": "Cloud Run Serverless (ADC Authenticated)",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/models")
def get_models():
    return {
        "models": AVAILABLE_MODELS,
        "default": "gemini-3.8-flash"
    }

@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    if not req.messages:
        raise HTTPException(status_code=400, detail="메시지가 비어있습니다.")

    latest_msg = req.messages[-1]
    if latest_msg.role != "user":
        raise HTTPException(status_code=400, detail="마지막 메시지는 사용자(user)의 것이어야 합니다.")

    # 멀티턴 히스토리 빌드
    history_contents = []
    for msg in req.messages[:-1]:
        role = "user" if msg.role == "user" else "model"
        history_contents.append(
            types.Content(
                role=role,
                parts=[types.Part.from_text(text=msg.content)]
            )
        )

    # Google Search 도구 설정 (Vertex AI에서도 Google Search Tool 지원)
    tools = []
    if req.use_web_search:
        tools.append(types.Tool(google_search=types.GoogleSearch()))

    # config 설정
    config_args = {
        "temperature": req.temperature,
        "top_p": req.top_p,
    }
    if tools:
        config_args["tools"] = tools
    if req.system_instruction and req.system_instruction.strip():
        config_args["system_instruction"] = req.system_instruction.strip()

    config = types.GenerateContentConfig(**config_args)

    user_prompt = latest_msg.content
    if req.attached_files:
        attachment_text = ""
        for f in req.attached_files:
            attachment_text += f"\n\n--- [첨부 파일: {f.filename}] ---\n{f.content}\n--- [파일 끝] ---\n\n"
        user_prompt = f"{attachment_text}사용자 요청: {user_prompt}"

    async def event_generator():
        client = get_genai_client()
        try:
            chat = client.chats.create(
                model=req.model,
                history=history_contents,
                config=config
            )

            response_stream = chat.send_message_stream(user_prompt)

            full_reply = []
            search_queries = []
            search_sources = []

            for chunk in response_stream:
                if chunk.text:
                    full_reply.append(chunk.text)
                    data = json.dumps({"chunk": chunk.text}, ensure_ascii=False)
                    yield f"data: {data}\n\n"
                    await asyncio.sleep(0.005)

                if hasattr(chunk, 'candidates') and chunk.candidates:
                    for cand in chunk.candidates:
                        gm = getattr(cand, 'grounding_metadata', None)
                        if gm:
                            queries = getattr(gm, 'web_search_queries', None)
                            if queries:
                                for q in queries:
                                    if q not in search_queries:
                                        search_queries.append(q)
                            chunks = getattr(gm, 'grounding_chunks', None)
                            if chunks:
                                for gc in chunks:
                                    web = getattr(gc, 'web', None)
                                    if web:
                                        title = getattr(web, 'title', None)
                                        uri = getattr(web, 'uri', None)
                                        if uri and not any(s['uri'] == uri for s in search_sources):
                                            search_sources.append({'title': title or '출처 웹사이트', 'uri': uri})

            done_payload = {
                "done": True,
                "model": req.model,
                "search_queries": search_queries,
                "search_sources": search_sources
            }
            yield f"data: {json.dumps(done_payload, ensure_ascii=False)}\n\n"

        except APIError as e:
            err_msg = f"Gemini API 오류 ({e.code}): {e.message}"
            yield f"data: {json.dumps({'error': err_msg}, ensure_ascii=False)}\n\n"
        except Exception as e:
            err_msg = f"서버 처리 오류: {str(e)}"
            yield f"data: {json.dumps({'error': err_msg}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

# 세션 관리 엔드포인트 (사용자별 격리)
@app.get("/api/sessions")
def list_sessions(request: Request, x_user_id: Optional[str] = Header(None, alias="X-User-Id")):
    user_id = get_request_user_id(request, x_user_id)
    sessions = load_sessions()
    session_list = []
    for s_id, data in sessions.items():
        sess_user = data.get("user_id")
        if sess_user == user_id:
            session_list.append({
                "id": s_id,
                "user_id": sess_user,
                "title": data.get("title", "새 대화"),
                "model": data.get("model", "gemini-3.8-flash"),
                "created_at": data.get("created_at"),
                "updated_at": data.get("updated_at"),
                "message_count": len(data.get("messages", []))
            })
    session_list.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return {"sessions": session_list}

@app.get("/api/sessions/{session_id}")
def get_session(session_id: str, request: Request, x_user_id: Optional[str] = Header(None, alias="X-User-Id")):
    user_id = get_request_user_id(request, x_user_id)
    sessions = load_sessions()
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="대화 세션을 찾을 수 없습니다.")
    sess = sessions[session_id]
    if sess.get("user_id") and sess.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="대화 세션을 찾을 수 없습니다.")
    return sess

@app.post("/api/sessions")
def save_session(session_data: SessionCreateUpdate, request: Request, x_user_id: Optional[str] = Header(None, alias="X-User-Id")):
    user_id = session_data.user_id or get_request_user_id(request, x_user_id)
    sessions = load_sessions()
    now_iso = datetime.now().isoformat()

    s_id = session_data.id if session_data.id else str(uuid.uuid4())
    existing = sessions.get(s_id, {})

    if existing and existing.get("user_id") and existing.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="다른 사용자의 세션을 수정할 권한이 없습니다.")

    sessions[s_id] = {
        "id": s_id,
        "user_id": user_id,
        "title": session_data.title,
        "model": session_data.model,
        "messages": [m.dict() for m in session_data.messages],
        "created_at": existing.get("created_at", now_iso),
        "updated_at": now_iso
    }
    save_sessions(sessions)
    return sessions[s_id]

@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str, request: Request, x_user_id: Optional[str] = Header(None, alias="X-User-Id")):
    user_id = get_request_user_id(request, x_user_id)
    sessions = load_sessions()
    if session_id in sessions:
        if sessions[session_id].get("user_id") and sessions[session_id].get("user_id") != user_id:
            raise HTTPException(status_code=404, detail="대화 세션을 찾을 수 없습니다.")
        del sessions[session_id]
        save_sessions(sessions)
        return {"status": "success", "message": "삭제되었습니다."}
    raise HTTPException(status_code=404, detail="대화 세션을 찾을 수 없습니다.")

@app.delete("/api/sessions")
def clear_all_sessions(request: Request, x_user_id: Optional[str] = Header(None, alias="X-User-Id")):
    user_id = get_request_user_id(request, x_user_id)
    sessions = load_sessions()
    new_sessions = {s_id: data for s_id, data in sessions.items() if data.get("user_id") != user_id}
    save_sessions(new_sessions)
    return {"status": "success", "message": "모든 대화 기록이 삭제되었습니다."}

# 정적 파일 서빙
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/", response_class=HTMLResponse)
def index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        with open(index_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Gemini Cloud Run Server (ADC Mode) is running.</h1>"

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    print(f"🚀 Gemini Web Chatbot (Cloud Run - ADC Mode) 시작: http://0.0.0.0:{port}")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
