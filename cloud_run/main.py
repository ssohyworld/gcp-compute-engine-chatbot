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

# Google GenAI SDK
from google import genai
from google.genai import types
from google.genai.errors import APIError

app = FastAPI(
    title="Gemini Web Chatbot (Cloud Run)",
    description="GCP Cloud Run 기반 Gemini AI 실시간 웹 챗봇 서비스",
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

# GCP Secret Manager 키 캐시 (불필요한 중복 API 호출 방지)
_CACHED_SECRET_KEY: Optional[str] = None

def get_secret_from_secret_manager() -> Optional[str]:
    """GCP Secret Manager에서 안전하게 GEMINI_API_KEY를 동적 조회 (Fallback)"""
    global _CACHED_SECRET_KEY
    if _CACHED_SECRET_KEY:
        return _CACHED_SECRET_KEY

    # 1. 환경변수에서 프로젝트 번호/ID 자동 탐색
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT") or "404380364167"
    secret_id = os.environ.get("GEMINI_SECRET_NAME", "GEMINI_API_KEY")

    try:
        from google.cloud import secretmanager
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        secret_value = response.payload.data.decode("UTF-8").strip()
        if secret_value:
            _CACHED_SECRET_KEY = secret_value
            print(f"[INFO] Secret Manager ({name})로부터 API 키를 안전하게 로드했습니다.")
            return _CACHED_SECRET_KEY
    except Exception as e:
        # 민감 정보(키 값)가 로그에 남지 않도록 에러 타입만 간략히 로깅
        print(f"[WARN] Secret Manager 자동 조회 실패 (환경변수 주입 모드 사용 권장): {type(e).__name__}")
    return None

# API 키 확인 함수 (1. Cloud Run Secret 환경변수 주입 -> 2. Secret Manager API 직접 조회)
def get_api_key() -> Tuple[Optional[str], str]:
    # 1순위: Cloud Run --set-secrets로 안전하게 주입된 환경변수
    if "GEMINI_API_KEY" in os.environ and os.environ["GEMINI_API_KEY"]:
        return os.environ["GEMINI_API_KEY"], "Cloud Run Secret Injected (GEMINI_API_KEY)"
    
    if "GOOGLE_API_KEY" in os.environ and os.environ["GOOGLE_API_KEY"]:
        return os.environ["GOOGLE_API_KEY"], "Environment Variable (GOOGLE_API_KEY)"
    
    # 2순위: Secret Manager API 직접 Fallback 조회
    secret_key = get_secret_from_secret_manager()
    if secret_key:
        return secret_key, "Secret Manager Direct API (projects/404380364167/secrets/GEMINI_API_KEY)"
    
    return None, "NONE"

def get_genai_client() -> genai.Client:
    api_key, _ = get_api_key()
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="Gemini API 키가 설정되지 않았습니다. Cloud Run Secret Manager 주입 설정을 확인하세요."
        )
    return genai.Client(api_key=api_key)

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

# 모델 정의
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
    return {"status": "ok", "service": "gemini-cloud-run-chatbot"}

@app.get("/api/status")
def get_system_status():
    api_key, key_source = get_api_key()
    return {
        "status": "healthy" if api_key else "missing_key",
        "api_key_configured": bool(api_key),
        "api_key_source": key_source,
        "default_model": "gemini-3.8-flash",
        "web_search_available": True,
        "environment": "Cloud Run Serverless Container",
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
    api_key, _ = get_api_key()
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="Gemini API 키가 설정되지 않았습니다. Secret Manager 연동을 확인하세요."
        )

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

    # Google Search 도구 설정
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
        # 해당 사용자 ID와 일치하는 세션만 반환
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

    # 타인 세션 덮어쓰기 방어
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
    # 본인 세션만 필터링하여 삭제, 타인 세션 보존
    new_sessions = {s_id: data for s_id, data in sessions.items() if data.get("user_id") != user_id}
    save_sessions(new_sessions)
    return {"status": "success", "message": "모든 대화 기록이 삭제되었습니다."}

# 정적 파일 서빙
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
def index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        with open(index_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Gemini Cloud Run Server is running.</h1>"

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    print(f"🚀 Gemini Web Chatbot (Cloud Run) 시작: http://0.0.0.0:{port}")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
