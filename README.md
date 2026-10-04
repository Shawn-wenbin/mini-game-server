# MiniGameServer

为 `MiniGameClient`（Cocos2d-x + Lua）提供真实 HTTP、FastAPI 和 MySQL 持久化的本地联调环境。目前实现 **Server Phase 1 + Phase 2**：健康检查、用户名登录、当前玩家、静态商品列表、购买和背包，以及 `players`、`inventory_items` 两张表。Phase 3 的成绩提交、排行榜和后续 WebSocket 尚未实现。

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

## Phase 2 API 契约

三个接口均需要 `Authorization: Bearer <登录返回的 token>`；缺失或非法 token 使用与 `/player/me` 相同的 HTTP `401/code=2001`。成功响应均为 HTTP `200`。

### GET /api/v1/shop/products

无请求体，商品由 `app/shop_config.py` 中的 `SHOP_PRODUCTS` 提供，不创建商店表：

```json
{
  "code": 0,
  "message": "ok",
  "data": [
    {"id": 1001, "name": "Potion", "price": 100, "item_id": 2001},
    {"id": 1002, "name": "Chest", "price": 300, "item_id": 2002},
    {"id": 1003, "name": "Skin A", "price": 500, "item_id": 2003}
  ]
}
```

`id` 是购买请求使用的商品 ID，`item_id` 是背包中的物品 ID，二者不能混用。价格均以金币计算。

### POST /api/v1/shop/purchase

请求头 `Content-Type: application/json`。每次请求购买一个商品：

```json
{"product_id":1001}
```

`product_id` 必须为正整数，不接受字符串、小数或布尔值；缺失或类型/范围错误返回 HTTP `422/code=422`。

初始金币为 1000 的玩家第一次购买 Potion 时：

```json
{
  "code": 0,
  "message": "ok",
  "data": {"gold": 900, "item": {"item_id": 2001, "count": 1}}
}
```

`gold` 是购买后的余额，`item.count` 是该物品购买后的总库存，不是本次增加量。重复购买累加同一条库存记录。

商品不存在返回 HTTP `404`：

```json
{"code":1002,"message":"product not found","data":null}
```

金币不足返回 HTTP `400`：

```json
{"code":1001,"message":"not enough gold","data":null}
```

购买时先验证商品，再锁定并重新读取玩家余额和库存；同一玩家的并发购买在 MySQL 中按事务串行处理。扣金币与新增/累加库存只执行一次提交，数据库异常回滚并返回 HTTP `503/code=503`，失败不会只扣金币或只增加库存。

### GET /api/v1/bag

无请求体，仅返回当前 token 对应玩家的库存，按 `item_id` 升序排列：

```json
{
  "code": 0,
  "message": "ok",
  "data": [{"item_id": 2001, "name": "Potion", "count": 2}]
}
```

新玩家没有库存时返回 `{"code":0,"message":"ok","data":[]}`。物品名称来自静态商品配置；手动写入数据库且配置中不存在的物品以 `Unknown` 显示。

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

Phase 2 验证可登录一个新用户名，例如 `phase2_demo`，将下方 token 替换为实际登录响应的 token：

```bash
curl -i -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"phase2_demo"}'

TOKEN=dev-1

curl -i http://127.0.0.1:8000/api/v1/shop/products \
  -H "Authorization: Bearer $TOKEN"

curl -i http://127.0.0.1:8000/api/v1/bag \
  -H "Authorization: Bearer $TOKEN"

curl -i -X POST http://127.0.0.1:8000/api/v1/shop/purchase \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"product_id":1001}'

curl -i http://127.0.0.1:8000/api/v1/player/me \
  -H "Authorization: Bearer $TOKEN"

curl -i http://127.0.0.1:8000/api/v1/bag \
  -H "Authorization: Bearer $TOKEN"

curl -i -X POST http://127.0.0.1:8000/api/v1/shop/purchase \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"product_id":9999}'

docker compose exec -T db mysql -uroot -proot minigame -e \
  "SELECT p.id, p.username, p.gold, i.item_id, i.count FROM players p LEFT JOIN inventory_items i ON i.player_id=p.id WHERE p.username='phase2_demo' ORDER BY i.item_id;"
```

全新玩家应先返回空背包；购买后余额为 900、物品 2001 的数量为 1；无效商品返回 `404/code=1002`，不改变数据。重复购买后应为 800/2；耗尽金币后再购买应返回 `400/code=1001`。重启 API，再请求 `/player/me`、`/bag` 并查询 MySQL，数据应保持一致。同名账号不会重置，因此重复验证时请换用新用户名或按实际余额判断结果。

也可在 Swagger 中登录并 `Authorize`，依次调用商品列表、购买和背包。`/openapi.json` 应只有 Phase 1 + Phase 2 的六个应用路径，不包含 `/api/v1/game/result` 或 `/api/v1/rankings`。

## 自动化测试

```bash
uv sync --locked
uv run pytest
```

测试使用 FastAPI TestClient，并运行实际的启动建表和关闭生命周期。每个测试使用独立 SQLite 文件，启用外键；测试后清理连接，不会修改开发 MySQL 数据。覆盖 Phase 1 原有行为、静态商品、购买后的持久化、库存累加、余额恰好足够/不足、无效商品与参数、三个新增接口的鉴权、空背包、多物品顺序、玩家隔离，以及只注册 Phase 1 + Phase 2 接口。

提交失败测试先执行 `flush()`，再模拟提交异常，通过独立 Session 确认金币和库存同时回滚，并验证实际 `get_db` 返回 `503`。SQLite 测试不能验证 MySQL 行锁，需要通过真实 MySQL 另行验证并发购买。

当前锁定的 Starlette 在使用 httpx 的 TestClient 时会发出一条弃用提示；44 个测试均通过。项目保留规格要求的 httpx，未隐藏这条提示。

## Phase 1 验证记录（2026-10-04）

- 已验证：`uv sync`、`uv sync --locked`、`uv run pytest`（23 passed）、`docker compose config --quiet`。
- 已验证：Compose MySQL 8.4 就绪，`uv run uvicorn app.main:app --reload` 成功启动并创建两张表；真实 curl 健康检查、登录、重复登录、当前玩家、非法 token 和 Swagger 页面符合契约。
- 已验证：直接查询 MySQL，`alice` 只有一条记录，初始值为 `1 / 1000 / 100 / 0`，`inventory_items` 为空；重启 API 后仍返回同一玩家和 token。
- 未验证：MiniGameClient 端到端联调，需要在 Cocos2d-x + Lua 客户端接入上述接口后进行。

## Phase 2 验证记录（2026-10-04）

- 已验证：`uv run --locked pytest`，44 passed；保留一条已有的 Starlette TestClient 弃用提示。
- 已验证：真实 FastAPI 进程连接 MySQL 8.4.11；通过 HTTP 检查商品、购买、空背包、重复购买、商品/参数错误、鉴权、玩家隔离；curl 检查健康与重启后的背包响应，Swagger 页面可访问。
- 已验证：独立 SQLAlchemy Session 和 MySQL 命令行查询确认提交后的金币、库存，以及数据库仍然只有两张表。
- 已验证：同一玩家 12 个并发 Potion 购买请求，10 次成功、2 次返回 `400/code=1001`；余额为 0，只有一条物品 2001 库存，数量为 10，没有覆盖更新或负余额。
- 已验证：重启 API 后再次登录并查询玩家、背包与 MySQL，玩家 ID、余额和库存不变。
- 已验证：OpenAPI 只有六个 Phase 1 + Phase 2 应用路径；成绩提交和排行榜请求均返回 `404`。
- 验证结束后已停止测试 API 进程，并清理仅本次创建的三个测试账号及其三条库存记录。
- 未验证：MiniGameClient 实际端到端联调；提交失败回滚通过 SQLite 自动化测试模拟，未对真实 MySQL 注入数据库故障。

## 数据库结构

只创建以下两张表：

- `players`：`id`（自增主键）、`username`（非空、最长 50、唯一）、`level`（默认 1）、`gold`（默认 1000）、`diamond`（默认 100）、`high_score`（默认 0）、`created_at`、`updated_at`。
- `inventory_items`：`id`（自增主键）、`player_id`（外键指向 `players.id`）、`item_id`、`count`（默认 0）、`created_at`、`updated_at`；`(player_id, item_id)` 唯一。

所有字段均非空。时间字段由数据库初始化，`updated_at` 在 SQLAlchemy 更新记录时刷新。登录不会创建背包记录；Phase 2 购买修改 `players.gold` 并新增/更新 `inventory_items.count`，没有新增表、列或数据库迁移。

## MiniGameClient 接入

- `NetworkManager` 使用 `http://127.0.0.1:8000/api/v1` 作为本机联调地址，发送和解析 JSON；先调用 `/health` 检查服务。
- `LoginController` 发送 `POST /auth/login`，读取 `data.token` 保存 token，并用 `data.player` 初始化 `PlayerModel`。
- 大厅刷新玩家时发送 `GET /player/me`，添加 `Authorization: Bearer <token>`，使用响应的 `data` 更新 `PlayerModel`。
- `ShopController` 使用 `GET /shop/products` 的 `data` 展示商品；点击购买时发送 `POST /shop/purchase`，请求 JSON 为 `{"product_id":<商品 id>}`，两者都携带 token。
- 购买成功后用 `data.gold` 更新 `PlayerModel`，用 `data.item` 更新对应库存，或再调用 `/player/me` 和 `/bag` 刷新。`BagController` 使用 `GET /bag` 的 `data` 展示物品名称和总数量，空数组表示空背包。
- `400/code=1001` 表示金币不足；`404/code=1002` 表示商品不存在。失败时不要本地预扣金币或添加物品；数据库不可用时可提示稍后刷新。
- 客户端同时处理 HTTP 状态码和应用 `code`；遇到 `401/code=2001` 时重新执行开发登录。
- 真机上的 `127.0.0.1` 指向真机自身。局域网联调时用 `uv run uvicorn app.main:app --reload --host 0.0.0.0` 启动，再将客户端地址改为开发电脑的局域网 IP。

## 开发鉴权与简化

**DEV ONLY / NOT SECURE / NOT PRODUCTION AUTH**

仅按用户名登录，没有密码。`dev-{player_id}` 直接暴露玩家 ID，可以伪造，没有签名或有效期。不能把本服务作为生产鉴权系统，也不要暴露到公网。

架构仅为路由 → 每请求同步 SQLAlchemy Session → MySQL。商品配置静态，每次购买一件，Skin A 也按普通物品累加；没有支付或道具使用逻辑。购买接口没有幂等键，客户端重复发送会重复购买，超时后应先查询玩家和背包确认状态。没有服务/仓储层、迁移、JWT/OAuth 或生产部署设施。当前完成范围仅限 Phase 1 + Phase 2；Phase 3 须明确请求后再实现。
