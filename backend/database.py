# 이 모듈은 백엔드가 공통으로 사용하는 데이터베이스 연결과 세션 구성을 정의.
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

SQLALCHEMY_DATABASE_URL = os.environ.get(
    "AGRIBOT_DATABASE_URL",
    "postgresql://agribot:password@localhost:5432/agribot_db",
)

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    # DB를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
