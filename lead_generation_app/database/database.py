import os
import logging
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine import URL

load_dotenv()

engine = None
SessionLocal = sessionmaker(autocommit=False, autoflush=False)


def _build_url():
    host = os.getenv("DB_HOST")
    port = os.getenv("DB_PORT")
    name = os.getenv("DB_NAME")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASS")
    if host and name and user:
        return URL.create(
            drivername="postgresql+psycopg2",
            username=user,
            password=password,
            host=host,
            port=int(port) if port else None,
            database=name,
        )
    sqlite_path = os.path.abspath(os.getenv("DB_SQLITE_PATH", "dev.db"))
    return f"sqlite+pysqlite:///{sqlite_path}"


def get_engine():
    global engine
    if engine is None:
        url = _build_url()
        engine = create_engine(url, pool_pre_ping=True)
        logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
        logging.info("{\"event\":\"db_engine_ready\"}")
    return engine


def get_session():
    get_engine()
    SessionLocal.configure(bind=engine)
    return SessionLocal()


def _ensure_soft_delete_columns(conn):
    if getattr(conn, "dialect", None) and conn.dialect.name != "postgresql":
        return
    res = conn.execute(text("select count(*) from information_schema.columns where table_name='business_clients' and column_name='is_deleted'"))
    if int(res.scalar_one()) == 0:
        conn.execute(text("alter table business_clients add column is_deleted boolean default false"))
    res2 = conn.execute(text("select count(*) from information_schema.columns where table_name='business_clients' and column_name='deleted_at'"))
    if int(res2.scalar_one()) == 0:
        conn.execute(text("alter table business_clients add column deleted_at timestamp null"))


def init_db():
    from .models import Base

    eng = get_engine()
    with eng.begin() as conn:
        logging.info("{\"event\":\"db_connection_ok\"}")
        Base.metadata.create_all(bind=conn)
        _ensure_soft_delete_columns(conn)
        logging.info("{\"event\":\"tables_ensured\"}")
