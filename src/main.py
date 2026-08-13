import os

from fastapi import APIRouter, FastAPI
from mangum import Mangum

app = FastAPI()
router = APIRouter(prefix="/api")

@router.get("/health")
def get_health():
    return "OK"

app.include_router(router=router)
# Later Routers Here

api_stage = os.environ.get("API_STAGE")
handler = Mangum(app, lifespan="off", api_gateway_base_path=f"/{api_stage}" if api_stage else "/")
