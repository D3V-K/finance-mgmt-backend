import os

from fastapi import APIRouter, FastAPI
from mangum import Mangum

from .routers import categories, reports, transactions

app = FastAPI()
router = APIRouter(prefix="/api")

@router.get("/health")
def get_health():
    return "OK"

app.include_router(router=router)
app.include_router(router=categories.router)
app.include_router(router=transactions.router)
app.include_router(router=reports.router)

api_stage = os.environ.get("API_STAGE")
handler = Mangum(app, lifespan="off", api_gateway_base_path=f"/{api_stage}" if api_stage else "/")
