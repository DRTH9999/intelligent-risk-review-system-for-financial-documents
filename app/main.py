"""FastAPI 应用入口。"""
from __future__ import annotations

from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
from sqlalchemy.orm.exc import StaleDataError
from sqlalchemy.exc import IntegrityError
from pydantic import ValidationError
from fastapi.staticfiles import StaticFiles

from app.config import APP_NAME, APP_VERSION, STATIC_DIR
from app.database import Base, SessionLocal, engine
from app.routers import admin, analysis, approvals, auth, config as config_router, dashboard, documents, reviews, sessions, suppliers
from app.seed import ensure_base_data
from app.migrations import upgrade_database


@asynccontextmanager
async def lifespan(_app: FastAPI):
    upgrade_database(engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        ensure_base_data(db)
    finally:
        db.close()
    from app.services.jobs import JobRunner
    runner = JobRunner(timeout_seconds=int(os.getenv('RISK_REVIEW_TASK_TIMEOUT', '180')))
    enabled = os.getenv('RISK_REVIEW_WORKER_ENABLED', 'true').lower() == 'true'
    if enabled:
        runner.start()
    try:
        yield
    finally:
        if enabled:
            runner.stop()


app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="财务单据智能风险审核系统 API，覆盖单据、附件解析、风险分析、审批与报告导出。",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(StaleDataError)
async def stale_update(_request, _exc):
    return JSONResponse(status_code=409, content={'detail': '数据已被其他操作修改，请刷新后重试'})


@app.exception_handler(IntegrityError)
async def conflicting_update(_request, _exc):
    return JSONResponse(status_code=409, content={'detail': '数据冲突，请刷新后重试；重复任务不会重复执行'})


@app.exception_handler(ValidationError)
async def invalid_model(_request, exc):
    return JSONResponse(status_code=422, content={'detail': '；'.join(error['msg'] for error in exc.errors())})

app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(sessions.router)
app.include_router(analysis.router)
app.include_router(reviews.router)
app.include_router(approvals.router)
app.include_router(config_router.router)
app.include_router(suppliers.router)
app.include_router(dashboard.router)
app.include_router(admin.router)


@app.get("/api/v1/health", tags=["系统"])
def health() -> dict:
    return {"status": "ok", "name": APP_NAME, "version": APP_VERSION}


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
def index():
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        return {"message": "前端尚未构建，请访问 /docs 查看接口文档"}
    return FileResponse(str(index_file))

