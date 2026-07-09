from sqlmodel import create_engine, Session, SQLModel
from sqlalchemy.orm import sessionmaker
from app.utils.config import settings

engine = create_engine(settings.env.DATABASE_URL, echo=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=Session)

def init_db():
    SQLModel.metadata.create_all(engine)

def get_session():
    with SessionLocal() as session:
        yield session
