import os

from fastapi import APIRouter, FastAPI
from mangum import Mangum

from .routers import transactions

app = FastAPI()
router = APIRouter(prefix="/api")

@router.get("/health")
def get_health():
    return "OK"

app.include_router(router=router)
router.include_router(router=transactions.router)

api_stage = os.environ.get("API_STAGE")
handler = Mangum(app, lifespan="off", api_gateway_base_path=f"/{api_stage}" if api_stage else "/")
