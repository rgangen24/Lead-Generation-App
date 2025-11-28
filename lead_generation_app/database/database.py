import os
import logging
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine import URL

load_dotenv()

engine = None
SessionLocal = sessionmaker(autocommit=False, autoflush=False)


def _build_url():
    sslmode = os.getenv("DB_SSLMODE", "require")
    raw = os.getenv("DATABASE_URL") or os.getenv("DB_URL") or os.getenv("EXTERNAL_DB_URL")
    if raw:
        if "sslmode=" not in raw:
            sep = "&" if "?" in raw else "?"
            raw = f"{raw}{sep}sslmode={sslmode}"
        return raw
    host = os.getenv("DB_HOST")
    port = os.getenv("DB_PORT")
    name = os.getenv("DB_NAME")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASS")
    return URL.create(
        drivername="postgresql+psycopg2",
        username=user,
        password=password,
        host=host,
        port=int(port) if port else None,
        database=name,
        query={"sslmode": sslmode},
    )


def get_engine():
    global engine
    if engine is None:
        url = _build_url()
        if isinstance(url, str):
            engine = create_engine(url, pool_pre_ping=True)
        else:
            engine = create_engine(url, pool_pre_ping=True)
        logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
        try:
            safe = engine.url.render_as_string(hide_password=True)
            logging.info("{\"event\":\"db_url_used\",\"url\":\"%s\"}" % safe.replace("\"", "\\\""))
        except Exception:
            pass
        logging.info("{\"event\":\"db_engine_ready\"}")
    return engine


def get_session():
    get_engine()
    SessionLocal.configure(bind=engine)
    return SessionLocal()


def init_db():
    from .models import Base

    eng = get_engine()
    with eng.begin() as conn:
        logging.info("{\"event\":\"db_connection_ok\"}")
        Base.metadata.create_all(bind=conn)
        logging.info("{\"event\":\"tables_ensured\"}")
