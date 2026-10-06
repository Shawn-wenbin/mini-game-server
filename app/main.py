from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.config import settings
from app.database import Base, engine
from app.routers import auth, bag, game, health, player, shop, websocket
from app.schemas import ErrorResponse


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # 只自动创建缺失的表，不执行数据库迁移。
    try:
        Base.metadata.create_all(bind=engine)
        yield
    finally:
        engine.dispose()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

import logging
import time

from starlette.concurrency import iterate_in_threadpool
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import StreamingResponse

_logger = logging.getLogger("app.http")
_MAX_LOG_BODY = 4096  # 超过 4KB 的 body 截断，避免刷爆 Terminal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s:%(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

def _safe_truncate(data: str, max_len: int = _MAX_LOG_BODY) -> str:
    if len(data) <= max_len:
        return data
    return f"{data[:max_len]}...[truncated {len(data)} bytes total]"

@app.middleware("http")
async def log_request_response(request: Request, call_next: RequestResponseEndpoint):
    # 记录请求基本信息 + 开始计时
    start = time.perf_counter()
    method, path, client = request.method, request.url.path, request.client
    query = request.url.query
    qs = f"?{query}" if query else ""

    # 读取请求体（注意：必须先缓存到 request.state 才能在后续路由里再读一次）
    req_body_bytes = await request.body()
    # 跳过二进制 / 表单文件，只打文本类 JSON
    content_type = request.headers.get("content-type", "") or ""
    is_text_body = content_type.startswith(
        ("application/json", "text/", "application/x-www-form-urlencoded")
    )
    req_body = (
        _safe_truncate(req_body_bytes.decode("utf-8", errors="replace"))
        if is_text_body and req_body_bytes
        else "<binary or empty>"
    )
    # 脱敏：Authorization / token 不要打到日志里
    safe_headers = {
        k: ("***" if k.lower() in {"authorization", "cookie"} else v)
        for k, v in request.headers.mutablecopy().items()
    }
    _logger.info(
        f"[REQ] {method} {path}{qs} from {client.host}:{client.port}\n"
        f"       headers={safe_headers}\n"
        f"       body={req_body}"
    )

    # 调用业务路由
    response = await call_next(request)

    # 读取响应体（StreamingResponse 要特殊处理，否则读完后客户端拿不到数据）
    resp_body = "<binary or streaming>"
    if (
        isinstance(response, StreamingResponse)
        or "application/octet-stream" in (response.headers.get("content-type") or "")
    ):
        pass  # 不打二进制/流式响应
    else:
        resp_body_chunks = [chunk async for chunk in response.body_iterator]
        resp_body_bytes = b"".join(resp_body_chunks)
        resp_body = _safe_truncate(
            resp_body_bytes.decode("utf-8", errors="replace")
        ) if resp_body_bytes else "<empty>"
        # 关键：重新组装 body_iterator，否则响应就被我们消费掉了，客户端收不到
        async def _body_it():
            for c in resp_body_chunks:
                yield c
        response.body_iterator = _body_it()

    elapsed_ms = (time.perf_counter() - start) * 1000
    _logger.info(
        f"[RES] {method} {path}{qs} -> {response.status_code} ({elapsed_ms:.1f}ms)\n"
        f"       body={resp_body}"
    )
    return response

@app.exception_handler(HTTPException)
async def handle_http_error(request: Request, exc: HTTPException) -> JSONResponse:
    response = ErrorResponse(
        code=2001 if exc.status_code == 401 else exc.status_code,
        message=str(exc.detail),
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=response.model_dump(),
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    message = "; ".join(
        f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
        for error in exc.errors()
    )
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(code=422, message=message).model_dump(),
    )


app.include_router(health.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(player.router, prefix="/api/v1")
app.include_router(shop.router, prefix="/api/v1")
app.include_router(bag.router, prefix="/api/v1")
app.include_router(game.router, prefix="/api/v1")
app.include_router(websocket.router, prefix="/api/v1")
