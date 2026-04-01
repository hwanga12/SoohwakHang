# 이 모듈은 FastAPI 백엔드의 진입점으로, 라우터와 공통 미들웨어를 등록.
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import Response
import models
from database import engine

# ⭐️ Import all routers
from routers import (
    actuations,
    alerts,
    camera,
    dashboard,
    environment,
    harvests,
    inference,
    iot,
    media,
    missions,
    plants,
    realtime,
    robots,
    zones,
)

logger = logging.getLogger(__name__)

try:
    models.Base.metadata.create_all(bind=engine)
except Exception as exc:
    logger.warning("DB 초기화를 건너뜁니다: %s", exc)

app = FastAPI(title=" AgriBot API", version="1.0.0", description="수확해조 로봇 백엔드 서버입니다.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def disable_docs_cache(request: Request, call_next) -> Response:
    # disable docs 캐시 정보를 계산해 반환한다.
    response = await call_next(request)
    if request.url.path in {"/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}:
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

app.include_router(dashboard.router, prefix="/api/v1/dashboard", tags=["Dashboard"])
app.include_router(robots.router, prefix="/api/v1/robot", tags=["Robot"])
app.include_router(missions.router, prefix="/api/v1/missions", tags=["Missions"])
app.include_router(zones.router, prefix="/api/v1/zones", tags=["Zones"])
app.include_router(plants.router, prefix="/api/v1/plants", tags=["Plants"])
app.include_router(alerts.router, prefix="/api/v1/alerts", tags=["Alerts"])
app.include_router(environment.router, prefix="/api/v1/environment", tags=["Environment"])
app.include_router(iot.router, prefix="/api/v1/iot", tags=["IoT Devices"])
app.include_router(actuations.router, prefix="/api/v1/actuations", tags=["Actuations & Control"])
app.include_router(harvests.router, prefix="/api/v1/harvests", tags=["Harvests"])
app.include_router(media.router, prefix="/api/v1/media", tags=["Media"])
app.include_router(camera.router, prefix="/api/v1/camera", tags=["Camera"])
app.include_router(inference.router, prefix="/api/v1/inference", tags=["Inference"])
app.include_router(realtime.router, prefix="/ws", tags=["Realtime WebSocket"])

@app.get("/")
def root():
    # 서비스 기본 응답을 반환해 서버가 정상 동작 중인지 확인할 수 있게 한다.
    return {"message": "AgriBot API is running. Visit http://localhost:8000/docs 에 접속해서 API 명세서를 확인하세요."}
