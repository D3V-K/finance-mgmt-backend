# Finance App — Python Backend

A serverless REST API for the personal finance management application, built with FastAPI and deployed as a container image on AWS Lambda. Sits behind API Gateway HTTP API (v2) with Cognito JWT authorization, and reads/writes to an Aurora Serverless v2 PostgreSQL database inside a private VPC.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Tech Stack](#tech-stack)
- [Authentication & Authorization](#authentication--authorization)
- [Database Layer](#database-layer)
- [API Reference](#api-reference)
- [Environment Variables](#environment-variables)
- [Local Development](#local-development)
- [Building and Deployment](#building-and-deployment)
- [CI/CD Pipeline](#cicd-pipeline)
- [Observability](#observability)

---

## Overview

The backend is a FastAPI application wrapped with Mangum to run as an AWS Lambda function. It is packaged as a Docker container image (rather than a zip artifact) to accommodate the combined size of FastAPI, SQLAlchemy, and psycopg2 binary dependencies. All database credentials are retrieved at cold-start from AWS Secrets Manager — nothing sensitive lives in environment variables or the container image.

```
API Gateway HTTP API (v2)
  └── Cognito JWT Authorizer (validates Bearer token)
        └── Lambda Function (FastAPI + Mangum, container image)
              ├── Aurora Serverless v2 PostgreSQL (private subnet)
              └── Secrets Manager (DB credentials at cold-start)
```

---

## Architecture

### Lambda Container Image

The function is packaged as a Docker container image stored in Amazon ECR. This approach is chosen over a zip deployment for two reasons: the combined size of FastAPI, SQLAlchemy, and psycopg2-binary comfortably exceeds the 50 MB zip limit, and container images support up to 10 GB, giving full control over the runtime environment.

The Lambda handler entry point is the `Mangum` adapter in `src/main.py`. Mangum translates the API Gateway event format into a standard ASGI request that FastAPI can process, and translates the FastAPI response back into the format API Gateway expects.

### VPC Placement

The Lambda function runs inside a private VPC alongside the Aurora cluster. This is a requirement for Aurora Serverless v2 — it does not have a public endpoint. The function is placed in private subnets with a NAT Gateway providing outbound internet access for calls to Secrets Manager and ECR during cold starts.

The security group on the Lambda function allows only outbound traffic. The security group on the Aurora cluster allows inbound PostgreSQL (port 5432) only from the Lambda security group — no broader access.

### Aurora Serverless v2

The database is Aurora PostgreSQL Serverless v2. It scales from 0.5 ACUs (Aurora Capacity Units) up to 4 ACUs based on load, and can pause after a period of inactivity. For a personal-use application this means near-zero database cost during idle periods, at the cost of a ~20–30 second cold-start delay when the cluster resumes from pause.

A `NullPool` SQLAlchemy connection pool is used instead of the default pool. Lambda execution contexts are ephemeral and do not persist between invocations reliably, so a persistent connection pool would leak connections to Aurora. `NullPool` opens a fresh connection per request and closes it immediately after — the correct pattern for Lambda.

### Secrets Manager

Database credentials (host, port, username, password, database name) are stored as a single JSON secret in AWS Secrets Manager. The Lambda function retrieves and parses this secret once per cold start and caches the resulting database URL in the module scope. Subsequent warm invocations reuse the cached URL without calling Secrets Manager again, keeping latency low.

---

## Project Structure

```
backend/
├── src/
│   ├── main.py                  # FastAPI app, router registration, Mangum handler
│   ├── db.py                    # Engine + session setup, Secrets Manager retrieval
│   ├── dependencies.py          # Shared FastAPI dependencies (get_db, get_current_user)
│   │
│   ├── routers/
│   │   ├── transactions.py      # CRUD for transactions
│   │   ├── categories.py        # CRUD for categories + tree structure
│   │   └── reports.py           # Aggregation queries (monthly, by category, net worth)
│   │
│   ├── models/
│   │   ├── base.py              # SQLAlchemy declarative base
│   │   ├── user.py              # User model
│   │   ├── category.py          # Category model (self-referential for sub-categories)
│   │   └── transaction.py       # Transaction model
│   │
│   ├── schemas/
│   │   ├── transaction.py       # Pydantic request/response schemas for transactions
│   │   ├── category.py          # Pydantic schemas for categories
│   │   └── report.py            # Pydantic schemas for report responses
│   │
│   └── utils/
│       └── pagination.py        # Shared pagination helpers
│
├── migrations/
│   ├── env.py                   # Alembic environment config
│   ├── script.py.mako
│   └── versions/                # Individual migration files
│
├── tests/
│   ├── conftest.py              # Pytest fixtures (test DB, test client, auth mock)
│   ├── test_transactions.py
│   ├── test_categories.py
│   └── test_reports.py
│
├── Dockerfile                   # Lambda container image definition
├── requirements.txt             # Production dependencies
├── requirements-dev.txt         # Dev + test dependencies
├── alembic.ini                  # Alembic migration config
└── template.yaml                # AWS SAM template
```

---

## Tech Stack

| Concern | Library | Reason |
|---|---|---|
| Framework | FastAPI | Async, automatic OpenAPI docs, Pydantic integration |
| ASGI adapter | Mangum | Translates API Gateway events to ASGI for FastAPI |
| ORM | SQLAlchemy 2.0 | Declarative models, typed queries, migration support |
| Migrations | Alembic | Schema version control tied to SQLAlchemy models |
| DB driver | psycopg2-binary | PostgreSQL driver for SQLAlchemy |
| Validation | Pydantic v2 | Request/response schema validation, built into FastAPI |
| AWS SDK | boto3 | Secrets Manager access, any future AWS service calls |
| Testing | pytest + httpx | Async test client for FastAPI endpoints |
| Packaging | Docker + ECR | Container image deployment to Lambda |
| IaC | AWS SAM | Lambda + API Gateway + VPC provisioning |

---

## Authentication & Authorization

The backend itself contains no authentication logic. JWT validation is offloaded entirely to API Gateway's native Cognito JWT Authorizer. When a request arrives, API Gateway validates the token signature, expiry, issuer, and audience against the configured Cognito User Pool before the Lambda function is ever invoked. An invalid or missing token returns a 401 directly from API Gateway — Lambda is never called.

Once inside the Lambda, the validated JWT claims are injected by API Gateway into the request context. The `get_current_user` dependency extracts the `sub` claim (the Cognito user ID) from the event context, looks up or creates the corresponding user record in the database, and returns it. Every router endpoint that needs user scoping declares this dependency.

```python
# dependencies.py
from fastapi import Request, Depends, HTTPException
from sqlalchemy.orm import Session
from .models.user import User
from .db import get_db

def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    claims = request.state.aws_event["requestContext"]["authorizer"]["jwt"]["claims"]
    cognito_sub = claims.get("sub")
    if not cognito_sub:
        raise HTTPException(status_code=401, detail="Missing user identity")

    user = db.query(User).filter(User.cognito_sub == cognito_sub).first()
    if not user:
        user = User(cognito_sub=cognito_sub)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user
```

All data queries are scoped to the authenticated user's ID — there is no admin role or cross-user data access.

---

## Database Layer

### Connection Setup

The database URL is constructed once at module load time (cold start) from credentials retrieved via Secrets Manager. SQLAlchemy uses `NullPool` to avoid connection leaks across Lambda invocations.

```python
# db.py
import os, boto3, json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

_db_url: str | None = None

def _get_db_url() -> str:
    global _db_url
    if _db_url:
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

engine = create_engine(_get_db_url(), poolclass=NullPool)
SessionLocal = sessionmaker(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

### Models

SQLAlchemy ORM models map directly to the Aurora schema. The `Category` model uses a self-referential foreign key to support nested sub-categories.

```python
# models/category.py
from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from .base import Base

class Category(Base):
    __tablename__ = "categories"

    id        = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id   = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    name      = Column(String(100), nullable=False)
    type      = Column(String(10))          # 'income' or 'expense'
    color     = Column(String(7))           # hex color e.g. '#4A90E2'
    parent_id = Column(UUID(as_uuid=True), ForeignKey("categories.id"), nullable=True)

    children  = relationship("Category", backref="parent", remote_side=[id])
```

### Migrations

Database schema changes are managed with Alembic. Migrations run from a developer machine or a one-off Lambda invocation — they do not run automatically on deployment.

```bash
# Create a new migration after changing a model
alembic revision --autogenerate -m "add currency column to transactions"

# Apply all pending migrations
alembic upgrade head

# Roll back one migration
alembic downgrade -1
```

---

## API Reference

All endpoints are prefixed with the stage path set by API Gateway (e.g. `/prod`). Every endpoint requires a valid Cognito JWT in the `Authorization: Bearer` header.

### Transactions

| Method | Path | Description |
|---|---|---|
| `GET` | `/transactions` | List transactions with optional `from`, `to`, `category_id` filters |
| `POST` | `/transactions` | Create a new transaction |
| `GET` | `/transactions/{id}` | Get a single transaction |
| `PUT` | `/transactions/{id}` | Update a transaction |
| `DELETE` | `/transactions/{id}` | Delete a transaction |

### Categories

| Method | Path | Description |
|---|---|---|
| `GET` | `/categories` | List all categories as a flat list |
| `GET` | `/categories/tree` | List categories as a nested tree structure |
| `POST` | `/categories` | Create a category (set `parent_id` for sub-categories) |
| `PUT` | `/categories/{id}` | Update a category |
| `DELETE` | `/categories/{id}` | Delete a category (cascades to transactions) |

### Reports

| Method | Path | Description |
|---|---|---|
| `GET` | `/reports/monthly` | Monthly income vs expense totals for a date range |
| `GET` | `/reports/by-category` | Spending breakdown by category for a date range |
| `GET` | `/reports/net-worth` | Cumulative net worth trend over time |

Full OpenAPI documentation is auto-generated by FastAPI and available at `/docs` when running locally.

---

## Environment Variables

The Lambda function reads the following environment variables at runtime. These are set in the SAM template and never committed to the repository.

```bash
DB_SECRET_ARN=arn:aws:secretsmanager:ap-northeast-1:123456789:secret:finance/db-credentials
AWS_REGION=ap-northeast-1
COGNITO_USER_POOL_ID=ap-northeast-1_XXXXXXXXX
ENVIRONMENT=production   # used to toggle debug logging
```

For local development, create a `.env` file at the project root and load it with `python-dotenv`. When running locally, `DB_SECRET_ARN` can point to a real Secrets Manager secret (requires AWS credentials) or be bypassed entirely by pointing directly at a local PostgreSQL instance.

---

## Local Development

**Prerequisites**: Python 3.12+, Docker, AWS SAM CLI, a local PostgreSQL instance (or Docker)

```bash
# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install all dependencies including dev tools
pip install -r requirements.txt -r requirements-dev.txt

# Run database migrations against a local PostgreSQL instance
export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/finance
alembic upgrade head

# Start the API locally with hot reload (bypasses Lambda/API Gateway)
uvicorn src.main:app --reload --port 8000
# → http://localhost:8000
# → http://localhost:8000/docs  (Swagger UI)
```

To test with the full Lambda + API Gateway emulation using SAM:

```bash
# Build the container image
sam build

# Start the local API Gateway emulator
sam local start-api --env-vars env.local.json
# → http://localhost:3000
```

`env.local.json` supplies environment variables to the local Lambda invocation and can point `DB_SECRET_ARN` at a real secret or override the database URL for a local instance.

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=src --cov-report=term-missing

# Run a specific test file
pytest tests/test_transactions.py -v
```

Tests use an in-memory SQLite database via a pytest fixture in `conftest.py` and mock the Cognito JWT claim injection so no real AWS resources are needed.

---

## Building and Deployment

```bash
# Build the Docker container image via SAM
sam build

# Deploy to AWS (first time — guided setup)
sam deploy --guided

# Subsequent deploys
sam deploy
```

`sam deploy` publishes the container image to ECR, updates the Lambda function, and applies any CloudFormation stack changes (API Gateway routes, IAM roles, VPC config).

To deploy manually without SAM:

```bash
# Build and push the image to ECR
aws ecr get-login-password --region ap-northeast-1 | \
  docker login --username AWS --password-stdin $ECR_URI

docker build -t finance-api .
docker tag finance-api:latest $ECR_URI/finance-api:latest
docker push $ECR_URI/finance-api:latest

# Update the Lambda function to use the new image
aws lambda update-function-code \
  --function-name FinanceAPI \
  --image-uri $ECR_URI/finance-api:latest
```

---

## CI/CD Pipeline

Backend deployment is automated via GitHub Actions on every push to `main` that touches files in the `backend/` directory.

```yaml
# .github/workflows/deploy-backend.yml
name: Deploy backend

on:
  push:
    branches: [main]
    paths: ['backend/**']

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: pip

      - run: pip install -r requirements.txt -r requirements-dev.txt

      - run: pytest --cov=src --cov-fail-under=80

  deploy:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ap-northeast-1

      - uses: aws-actions/amazon-ecr-login@v2

      - name: Build and push container image
        run: |
          docker build -t finance-api .
          docker tag finance-api:latest ${{ secrets.ECR_URI }}/finance-api:${{ github.sha }}
          docker push ${{ secrets.ECR_URI }}/finance-api:${{ github.sha }}

      - uses: aws-actions/setup-sam@v2

      - name: Deploy with SAM
        run: |
          sam deploy \
            --no-confirm-changeset \
            --no-fail-on-empty-changeset \
            --parameter-overrides ImageUri=${{ secrets.ECR_URI }}/finance-api:${{ github.sha }}
```

The `deploy` job only runs if the `test` job passes, enforcing a minimum 80% test coverage gate before any code reaches the Lambda function.

---

## Observability

All Lambda invocations automatically emit logs to CloudWatch Logs under the log group `/aws/lambda/FinanceAPI`. Structured JSON logging is used so log entries can be queried and filtered in CloudWatch Insights.

```python
# Structured logging setup in main.py
import logging, json

class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        })

handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logging.getLogger().addHandler(handler)
logging.getLogger().setLevel(
    logging.DEBUG if os.environ.get("ENVIRONMENT") != "production" else logging.INFO
)
```

Useful CloudWatch Insights queries:

```sql
-- All errors in the last 24 hours
fields @timestamp, message
| filter level = "ERROR"
| sort @timestamp desc
| limit 50

-- Average Lambda duration by hour
stats avg(@duration) as avg_ms by bin(1h)
| sort bin(1h) desc
```

Lambda function metrics (invocation count, error rate, duration, throttles) are visible in the CloudWatch console under the function's monitoring tab without any additional configuration.

---

## Related

- [`/frontend`](../frontend/README.md) — React + Vite frontend
