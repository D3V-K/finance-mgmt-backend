import os, boto3, json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

_db_url: str | None = None

def get_db_url() -> str:
    global _db_url
    if _db_url:
        return _db_url

    dev_db_url = os.getenv("DATABASE_URL")
    if dev_db_url:
        _db_url = dev_db_url
        return _db_url

    client = boto3.client("secretsmanager")

    secret = json.loads(
        client.get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])["SecretString"]
    )
    _db_url = (
        f"postgresql+psycopg2://{secret['username']}:{secret['password']}"
        f"@{secret['host']}:{secret['port']}/{secret['dbname']}"
    )
    return _db_url

engine = create_engine(get_db_url(), poolclass=NullPool)
SessionLocal = sessionmaker(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()