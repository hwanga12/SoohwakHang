from fastapi import FastAPI
import models
from database import engine

# ⭐️ Import all routers
from routers import (
    dashboard, robots, missions, zones, plants, 
    alerts, environment, iot, actuations, harvests, media, realtime
)

# 핵심: 서버를 켤 때 DB에 테이블이 없으면 파이썬이 알아서 생성해 줍니다!
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="🌱 AgriBot API", version="1.0.0", description="수확해조 로봇 백엔드 서버입니다.")

# ⭐️ 각각의 라우터를 앱에 등록 (prefix로 기본 URL을 맞춰줍니다)
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
app.include_router(realtime.router, prefix="/ws", tags=["Realtime WebSocket"])

@app.get("/")
def root():
    return {"message": "AgriBot API is running. Visit http://localhost:8000/docs 에 접속해서 API 명세서를 확인하세요."}