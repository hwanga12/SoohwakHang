from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# 도커로 띄울 PostgreSQL 접속 주소
SQLALCHEMY_DATABASE_URL = "postgresql://agribot:password@localhost:5432/agribot_db"

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()