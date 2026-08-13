from fastapi import APIRouter, FastAPI
from mangum import Mangum

app = FastAPI()
router = APIRouter(prefix="/api")

app.include_router(router=router)
# Later Routers Here

handler = Mangum(app, lifespan="off")
