from fastapi import APIRouter

router = APIRouter(prefix="/api")
openai_router = APIRouter(prefix="/v1")
wecom_router = APIRouter(prefix="/wecom")
