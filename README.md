# MiniGameServer

为 `MiniGameClient`（Cocos2d-x + Lua）提供真实 HTTP、FastAPI 和 MySQL 持久化的本地联调环境。目前只实现 **Server Phase 1**：健康检查、用户名登录和当前玩家查询，以及 `players`、`inventory_items` 两张表。没有商店、背包接口、购买、成绩、排行榜或 WebSocket。

## 环境要求

- Python 3.12+；项目默认使用 3.12。
- 已安装 `uv`。
- Docker 和 Docker Compose，且 Docker 服务已启动。
- 本机端口 `3306` 和 `8000` 可用。

依赖包括 FastAPI、Uvicorn、SQLAlchemy 2.x 同步 Session、PyMySQL、Pydantic Settings；开发依赖为 pytest 和 httpx。`pymysql[rsa]` 提供 MySQL 8 默认认证所需的支持。

## 本地启动

在项目根目录执行：

```bash
uv python install 3.12
uv sync
cp .env.example .env
docker compose up -d --wait db
uv run uvicorn app.main:app --reload
```

已有 Python 3.12 时可跳过第一条命令。`.env` 已被 Git 忽略，不要提交。默认数据库连接：

```env
APP_NAME=MiniGameServer
APP_ENV=development
DATABASE_URL=mysql+pymysql://root:root@127.0.0.1:3306/minigame?charset=utf8mb4
```

环境变量优先于 `.env`。`APP_ENV` 是环境标识，修改它不会将开发鉴权变为生产鉴权。

Compose 只运行 MySQL 8.4，API 在本机运行。`root/root` 是公开的本地开发凭据。MySQL 端口仅绑定 `127.0.0.1`，数据保存在 `mysql_data` 命名卷中；`docker compose stop db` 不会删除数据。如果已有 MySQL 占用 3306，可修改 Compose 的宿主端口，并同步修改 `.env` 的连接地址。

启动时执行 `Base.metadata.create_all(bind=engine)`。MySQL 不可用时 API 启动失败；此时先检查 `docker compose ps` 和 `docker compose logs db`。自动建表只创建缺失的表，不修改已有表结构，没有 Alembic。

- Swagger：<http://127.0.0.1:8000/docs>
- OpenAPI：<http://127.0.0.1:8000/openapi.json>
- 健康检查：<http://127.0.0.1:8000/api/v1/health>

## Phase 1 API 契约

所有应用接口使用 `/api/v1` 前缀，请求与响应使用 JSON。成功 HTTP 状态码均为 `200`。

### GET /api/v1/health

无需鉴权，无请求体。响应：

```json
{"status":"ok"}
```

此接口确认 HTTP 服务可响应，不会执行数据库探活查询。

### POST /api/v1/auth/login

无需鉴权，请求头 `Content-Type: application/json`。请求：

```json
{"username":"alice"}
```

`username` 必须为字符串，去除首尾空白后长度为 1～50 个字符。同名玩家已存在时返回原玩家，不会重置资产；否则创建玩家，默认 `level=1`、`gold=1000`、`diamond=100`、`high_score=0`。

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "token": "dev-1",
    "player": {
      "id": 1,
      "username": "alice",
      "level": 1,
      "gold": 1000,
      "diamond": 100,
      "high_score": 0
    }
  }
}
```

`id` 由数据库分配，客户端必须使用实际返回的 `token`。缺失或非法用户名返回 HTTP `422`，响应包含 `code=422`、描述验证问题的 `message` 和 `data=null`。

### GET /api/v1/player/me

无请求体，必须携带登录返回的 token：

```http
Authorization: Bearer dev-1
```

响应的 `data` 直接是玩家对象：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "id": 1,
    "username": "alice",
    "level": 1,
    "gold": 1000,
    "diamond": 100,
    "high_score": 0
  }
}
```

缺失、格式错误或指向不存在玩家的 token 返回 HTTP `401`，并携带 `WWW-Authenticate: Bearer`：

```json
{"code":2001,"message":"invalid dev token","data":null}
```

请求处理期间发生数据库错误时回滚并返回 HTTP `503`：

```json
{"code":503,"message":"database unavailable","data":null}
```

## curl 验证

API 启动后，在另一个终端执行：

```bash
curl -i http://127.0.0.1:8000/api/v1/health

curl -i -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice"}'

curl -i -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice"}'

# 将 dev-1 替换为实际登录响应里的 token。
curl -i http://127.0.0.1:8000/api/v1/player/me \
  -H 'Authorization: Bearer dev-1'

curl -i http://127.0.0.1:8000/api/v1/player/me \
  -H 'Authorization: Bearer invalid'
```

两次登录应返回相同的玩家 ID 和 token；最后一个请求应返回 `401` 和 `code=2001`。Swagger 中可先调用登录，再在 `Authorize` 中输入实际 token（例如 `dev-1`），随后调用 `/player/me`。

使用真实 MySQL 查询确认已提交的数据及表结构：

```bash
docker compose exec -T db mysql -uroot -proot minigame -e \
  "SHOW TABLES; SHOW CREATE TABLE players; SHOW CREATE TABLE inventory_items; SELECT id, username, level, gold, diamond, high_score FROM players WHERE username='alice'; SELECT COUNT(*) AS alice_count FROM players WHERE username='alice';"
```

重启 API 后再次登录 `alice`，应仍返回相同玩家。MySQL 客户端可能提示命令行密码警告，这里的凭据仅用于本地开发。

## 自动化测试

```bash
uv sync --locked
uv run pytest
```

测试使用 FastAPI TestClient，并运行实际的启动建表和关闭生命周期。每个测试使用独立 SQLite 文件，启用外键；测试后清理连接，不会修改开发 MySQL 数据。覆盖健康检查、登录默认值及提交结果、重复登录、保留已有玩家数据、用户名验证、有效和无效 token，以及 Phase 1 路由范围。SQLite 测试不能替代上面的真实 MySQL 持久化验证。

当前锁定的 Starlette 在使用 httpx 的 TestClient 时会发出一条弃用提示；23 个测试均通过。项目保留规格要求的 httpx，未隐藏这条提示。

## 本次验证记录（2026-10-04）

- 已验证：`uv sync`、`uv sync --locked`、`uv run pytest`（23 passed）、`docker compose config --quiet`。
- 已验证：Compose MySQL 8.4 就绪，`uv run uvicorn app.main:app --reload` 成功启动并创建两张表；真实 curl 健康检查、登录、重复登录、当前玩家、非法 token 和 Swagger 页面符合契约。
- 已验证：直接查询 MySQL，`alice` 只有一条记录，初始值为 `1 / 1000 / 100 / 0`，`inventory_items` 为空；重启 API 后仍返回同一玩家和 token。
- 未验证：MiniGameClient 端到端联调，需要在 Cocos2d-x + Lua 客户端接入上述接口后进行。

## 数据库结构

只创建以下两张表：

- `players`：`id`（自增主键）、`username`（非空、最长 50、唯一）、`level`（默认 1）、`gold`（默认 1000）、`diamond`（默认 100）、`high_score`（默认 0）、`created_at`、`updated_at`。
- `inventory_items`：`id`（自增主键）、`player_id`（外键指向 `players.id`）、`item_id`、`count`（默认 0）、`created_at`、`updated_at`；`(player_id, item_id)` 唯一。

所有字段均非空。时间字段由数据库初始化，`updated_at` 在 SQLAlchemy 更新记录时刷新。Phase 1 登录不会创建背包记录，也不提供背包接口。

## MiniGameClient 接入

- `NetworkManager` 使用 `http://127.0.0.1:8000/api/v1` 作为本机联调地址，发送和解析 JSON；先调用 `/health` 检查服务。
- `LoginController` 发送 `POST /auth/login`，读取 `data.token` 保存 token，并用 `data.player` 初始化 `PlayerModel`。
- 大厅刷新玩家时发送 `GET /player/me`，添加 `Authorization: Bearer <token>`，使用响应的 `data` 更新 `PlayerModel`。
- 客户端同时处理 HTTP 状态码和应用 `code`；遇到 `401/code=2001` 时重新执行开发登录。
- 真机上的 `127.0.0.1` 指向真机自身。局域网联调时用 `uv run uvicorn app.main:app --reload --host 0.0.0.0` 启动，再将客户端地址改为开发电脑的局域网 IP。

## 开发鉴权与简化

**DEV ONLY / NOT SECURE / NOT PRODUCTION AUTH**

仅按用户名登录，没有密码。`dev-{player_id}` 直接暴露玩家 ID，可以伪造，没有签名或有效期。不能把本服务作为生产鉴权系统，也不要暴露到公网。

架构仅为路由 → 每请求同步 SQLAlchemy Session → MySQL。没有服务/仓储层、迁移、JWT/OAuth 或生产部署设施。当前完成范围仅限 Phase 1；后续阶段须明确请求后再实现。
