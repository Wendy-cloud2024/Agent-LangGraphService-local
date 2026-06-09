"""FastAPI 应用工厂 — CORS、lifespan、路由挂载"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.server.config import CORS_ORIGINS
from src.server.graph_manager import graph_manager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时预编译图"""
    logger.info("正在初始化服务...")
    graph_manager.get_graph()  # 预编译
    logger.info("图编译完成，服务就绪")
    yield
    logger.info("服务关闭")


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例"""
    app = FastAPI(
        title="电商智能客服 Agent",
        description="基于 LangGraph 的多 Agent 电商客服系统 — FastAPI 后端",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册路由（延迟导入避免循环依赖）
    from src.server.rest_routes import router as rest_router
    from src.server.ws_handler import router as ws_router

    app.include_router(rest_router, prefix="/api")
    app.include_router(ws_router)

    return app
