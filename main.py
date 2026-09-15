import os
import json
import uuid
import asyncio
from datetime import datetime
from typing import List, Optional, Dict, Any
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Google GenAI SDK
from google import genai
from google.genai import types
from google.genai.errors import APIError

app = FastAPI(
    title="Gemini Web Chatbot",
    description="Gemini 3.8 Flash & 3.7 Flash 기반 로컬 웹 챗봇 서비스",
    version="1.0.0"
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

# API 키 확인 (GEMINI_API_KEY 우선, GOOGLE_API_KEY 대체)
def get_api_key() -> tuple[Optional[str], str]:
    if "GEMINI_API_KEY" in os.environ and os.environ["GEMINI_API_KEY"]:
        return os.environ["GEMINI_API_KEY"], "GEMINI_API_KEY"
    if "GOOGLE_API_KEY" in os.environ and os.environ["GOOGLE_API_KEY"]:
        return os.environ["GOOGLE_API_KEY"], "GOOGLE_API_KEY"
    return None, "NONE"

def mask_key(key: Optional[str]) -> str:
    if not key:
        return "미설정"
    if len(key) <= 8:
        return "****"
    return f"{key[:6]}...{key[-4:]}"

def get_genai_client() -> genai.Client:
    api_key, _ = get_api_key()
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="Gemini API 키가 설정되지 않았습니다. 환경변수 GEMINI_API_KEY 또는 GOOGLE_API_KEY를 확인하세요."
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
    title: str
    model: str = "gemini-3.8-flash"
    messages: List[ChatMessage] = []

# --- API Endpoints ---

@app.get("/api/status")
def get_system_status():
    api_key, key_source = get_api_key()
    return {
        "status": "healthy" if api_key else "missing_key",
        "api_key_configured": bool(api_key),
        "api_key_source": key_source,
        "masked_key": mask_key(api_key),
        "default_model": "gemini-3.8-flash",
        "web_search_available": True,
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
            detail="Gemini API 키가 환경변수에 없습니다. GEMINI_API_KEY를 설정해주세요."
        )

    if not req.messages:
        raise HTTPException(status_code=400, detail="메시지가 비어있습니다.")

    latest_msg = req.messages[-1]
    if latest_msg.role != "user":
        raise HTTPException(status_code=400, detail="마지막 메시지는 사용자(user)의 것이어야 합니다.")

    # 멀티턴 히스토리 빌드 (마지막 사용자 메시지 제외)
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
            # 채팅 세션 생성
            chat = client.chats.create(
                model=req.model,
                history=history_contents,
                config=config
            )

            # 스트리밍 메시지 전송
            response_stream = chat.send_message_stream(user_prompt)

            full_reply = []
            search_queries = []
            search_sources = []

            for chunk in response_stream:
                if chunk.text:
                    full_reply.append(chunk.text)
                    data = json.dumps({"chunk": chunk.text}, ensure_ascii=False)
                    yield f"data: {data}\n\n"
                    await asyncio.sleep(0.005)  # 부드러운 스트리밍 버퍼링

                # 실시간 Google Search Grounding 메타데이터 추출
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

            # 완료 알림 (Google Search 정보 포함)
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

# 세션 관리 엔드포인트
@app.get("/api/sessions")
def list_sessions():
    sessions = load_sessions()
    session_list = []
    for s_id, data in sessions.items():
        session_list.append({
            "id": s_id,
            "title": data.get("title", "새 대화"),
            "model": data.get("model", "gemini-3.8-flash"),
            "created_at": data.get("created_at"),
            "updated_at": data.get("updated_at"),
            "message_count": len(data.get("messages", []))
        })
    # 최신 업데이트 순 정렬
    session_list.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return {"sessions": session_list}

@app.get("/api/sessions/{session_id}")
def get_session(session_id: str):
    sessions = load_sessions()
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="대화 세션을 찾을 수 없습니다.")
    return sessions[session_id]

@app.post("/api/sessions")
def save_session(session_data: SessionCreateUpdate):
    sessions = load_sessions()
    now_iso = datetime.now().isoformat()

    s_id = session_data.id if session_data.id else str(uuid.uuid4())
    existing = sessions.get(s_id, {})

    sessions[s_id] = {
        "id": s_id,
        "title": session_data.title,
        "model": session_data.model,
        "messages": [m.dict() for m in session_data.messages],
        "created_at": existing.get("created_at", now_iso),
        "updated_at": now_iso
    }
    save_sessions(sessions)
    return sessions[s_id]

@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str):
    sessions = load_sessions()
    if session_id in sessions:
        del sessions[session_id]
        save_sessions(sessions)
        return {"status": "success", "message": "삭제되었습니다."}
    raise HTTPException(status_code=404, detail="대화 세션을 찾을 수 없습니다.")

@app.delete("/api/sessions")
def clear_all_sessions():
    save_sessions({})
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
    return "<h1>Gemini Chatbot Server is running. Static files missing.</h1>"

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    print(f"🚀 Gemini Web Chatbot 서버 시작: http://localhost:{port}")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
