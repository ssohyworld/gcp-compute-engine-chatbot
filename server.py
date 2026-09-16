"""
Gemini Web Chatbot Server Entry Point
강사님 예제(server.py) 및 uvicorn server:app 호환용 파일
"""
import os
import uvicorn
from main import app, client, SUPPORTED_MODELS

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
