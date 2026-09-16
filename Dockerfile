# 1. Python 3.11 슬림 베이스 이미지 사용
FROM python:3.11-slim

# 2. 파이썬 버퍼링 및 바이트코드 생성 비활성화
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

# 3. 컨테이너 내부 작업 디렉터리 설정
WORKDIR /app

# 4. 의존성 패키지 복사 및 설치 (도커 빌드 캐시 최적화)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. 프로젝트 소스 코드 및 정적 리소스 복사
COPY . .

# 6. 대화 세션 데이터 디렉터리 권한 확인 및 생성
RUN mkdir -p /app/data

# 7. 서비스 포트 개방
EXPOSE 8080

# 8. Uvicorn 기반 FastAPI 서버 구동 (Cloud Run 동적 포트 수신)
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}
