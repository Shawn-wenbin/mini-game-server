# MiniGameServer PROJECT_SPEC

## 1. Project Goal

`MiniGameServer` is a small backend used only for local integration testing of `MiniGameClient`.

The client stack is:

```text
Cocos2d-x + Lua
```

The server stack is:

```text
Python + FastAPI + MySQL
```

Primary goal:

> Replace the client's in-memory mock network responses with real HTTP requests and persistent MySQL data, while keeping the backend intentionally small.

This is **not** a production game server.

---

# 2. Architecture

```text
MiniGameClient
Cocos2d-x + Lua
        |
        | HTTP / JSON
        v
MiniGameServer
FastAPI
        |
        | SQLAlchemy
        v
MySQL
```

Optional later extension:

```text
WebSocket
```

for heartbeat/reconnect learning.

HTTP is the first priority.

---

# 3. Technology Stack

Use:

```text
Python 3.12+
FastAPI
Uvicorn
SQLAlchemy 2.x
PyMySQL
MySQL 8.x / 8.4
pydantic-settings
uv
pytest
httpx
Docker Compose for MySQL only
```

Use synchronous SQLAlchemy.

Do not add Alembic initially.

---

# 4. Repository Structure

Recommended:

```text
MiniGameServer/

├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── database.py
│   ├── models.py
│   ├── schemas.py
│   ├── deps.py
│   │
│   ├── config/
│   │   └── shop.py
│   │
│   └── routers/
│       ├── health.py
│       ├── auth.py
│       ├── player.py
│       ├── shop.py
│       ├── bag.py
│       └── game.py
│
├── tests/
│   ├── test_health.py
│   ├── test_auth.py
│   ├── test_shop.py
│   └── test_game.py
│
├── docs/
│   └── PROJECT_SPEC.md
│
├── AGENTS.md
├── .env.example
├── .gitignore
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

Do not create service/repository layers initially.

---

# 5. Environment

Example `.env.example`:

```env
APP_NAME=MiniGameServer
APP_ENV=development
DATABASE_URL=mysql+pymysql://root:root@127.0.0.1:3306/minigame
```

Real `.env` must not be committed.

---

# 6. MySQL

Use Docker Compose only for MySQL.

Example:

```yaml
services:
  db:
    image: mysql:8.4
    environment:
      MYSQL_ROOT_PASSWORD: root
      MYSQL_DATABASE: minigame
    ports:
      - "3306:3306"
    volumes:
      - mysql_data:/var/lib/mysql

volumes:
  mysql_data:
```

Start:

```bash
docker compose up -d db
```

FastAPI runs directly on the host.

---

# 7. Database Schema

Only two tables are required initially.

## 7.1 players

Fields:

```text
id
username
level
gold
diamond
high_score
created_at
updated_at
```

Suggested constraints:

```text
id          primary key
username    unique, not null
level       not null, default 1
gold        not null, default 1000
diamond     not null, default 100
high_score  not null, default 0
```

---

## 7.2 inventory_items

Fields:

```text
id
player_id
item_id
count
created_at
updated_at
```

Constraints:

```text
id primary key
player_id foreign key -> players.id
unique(player_id, item_id)
```

---

# 8. Static Shop Configuration

Do not create a shop database table.

Use Python configuration:

```python
SHOP_PRODUCTS = {
    1001: {
        "name": "Potion",
        "price": 100,
        "item_id": 2001,
    },
    1002: {
        "name": "Chest",
        "price": 300,
        "item_id": 2002,
    },
    1003: {
        "name": "Skin A",
        "price": 500,
        "item_id": 2003,
    },
}
```

---

# 9. Common Response Format

Prefer:

```json
{
  "code": 0,
  "message": "ok",
  "data": {}
}
```

Suggested application codes:

```text
0     success
1001  not enough gold
1002  product not found
1003  item not found
2001  invalid dev token
```

Use normal HTTP 400/401/404 where appropriate.

---

# 10. Development Authentication

Authentication is intentionally simplified.

After login, return:

```text
dev-{player_id}
```

Example:

```text
dev-1
```

Client sends:

```http
Authorization: Bearer dev-1
```

This is:

```text
DEV ONLY
NOT SECURE
NOT PRODUCTION AUTH
```

Do not add password hashing/JWT/OAuth initially.

---

# 11. API Contract

All APIs use:

```text
/api/v1
```

## 11.1 Health

```http
GET /api/v1/health
```

Response:

```json
{
  "status": "ok"
}
```

No authentication.

## 11.2 Login

```http
POST /api/v1/auth/login
```

Request:

```json
{
  "username": "alice"
}
```

Behavior:

```text
lookup player by username
if found: return existing player
if missing: create player with defaults
```

Defaults:

```text
level      1
gold       1000
diamond    100
high_score 0
```

Response:

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

## 11.3 Current Player

```http
GET /api/v1/player/me
```

Header:

```http
Authorization: Bearer dev-1
```

Response:

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
    "high_score": 27
  }
}
```

## 11.4 Shop Products

```http
GET /api/v1/shop/products
```

Prefer authenticated access for consistency.

Response:

```json
{
  "code": 0,
  "message": "ok",
  "data": [
    {
      "id": 1001,
      "name": "Potion",
      "price": 100,
      "item_id": 2001
    },
    {
      "id": 1002,
      "name": "Chest",
      "price": 300,
      "item_id": 2002
    }
  ]
}
```

## 11.5 Purchase Product

```http
POST /api/v1/shop/purchase
```

Header:

```http
Authorization: Bearer dev-1
```

Request:

```json
{
  "product_id": 1001
}
```

Transaction:

```text
load player
load product from SHOP_PRODUCTS
validate product exists
validate player.gold >= price
load/create inventory item
player.gold -= price
inventory.count += 1
commit once
```

Success:

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "gold": 900,
    "item": {
      "item_id": 2001,
      "count": 1
    }
  }
}
```

Insufficient gold:

```json
{
  "code": 1001,
  "message": "not enough gold",
  "data": null
}
```

## 11.6 Bag

```http
GET /api/v1/bag
```

Header:

```http
Authorization: Bearer dev-1
```

Response:

```json
{
  "code": 0,
  "message": "ok",
  "data": [
    {
      "item_id": 2001,
      "name": "Potion",
      "count": 5
    }
  ]
}
```

## 11.7 Submit Game Result

```http
POST /api/v1/game/result
```

Header:

```http
Authorization: Bearer dev-1
```

Request:

```json
{
  "score": 27
}
```

Behavior:

```text
validate score >= 0
if score > player.high_score:
    update high_score
    new_record = true
else:
    new_record = false
```

Response:

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "score": 27,
    "high_score": 27,
    "new_record": true
  }
}
```

No anti-cheat is required.

## 11.8 Rankings

```http
GET /api/v1/rankings?limit=20
```

Rules:

```text
limit default 20
limit min 1
limit max 100
sort high_score DESC, id ASC
```

Response:

```json
{
  "code": 0,
  "message": "ok",
  "data": [
    {
      "rank": 1,
      "username": "alice",
      "score": 100
    },
    {
      "rank": 2,
      "username": "bob",
      "score": 80
    }
  ]
}
```

---

# 12. Client Mapping

```text
MiniGameClient               MiniGameServer

LoginController       ->     POST /auth/login
PlayerModel           <-     GET /player/me
ShopController        ->     GET /shop/products
ShopController        ->     POST /shop/purchase
BagController         ->     GET /bag
ResultView            ->     POST /game/result
RankView              ->     GET /rankings
NetworkManager        ->     HTTP transport
```

---

# 13. Local Development

Install dependencies:

```bash
uv sync
```

or during initialization:

```bash
uv add fastapi "uvicorn[standard]" sqlalchemy pymysql pydantic-settings
uv add --dev pytest httpx
```

Start MySQL:

```bash
docker compose up -d db
```

Start API:

```bash
uv run uvicorn app.main:app --reload
```

Swagger:

```text
http://127.0.0.1:8000/docs
```

Health:

```text
http://127.0.0.1:8000/api/v1/health
```

---

# 14. Database Initialization

Initial version may create tables at app startup:

```python
Base.metadata.create_all(bind=engine)
```

No Alembic initially.

---

# 15. Tests

Minimum tests:

```text
health returns ok
login creates player
second login returns same player
player/me requires valid token
purchase deducts gold
purchase adds inventory
purchase rejects insufficient gold
bag returns inventory
game result updates high score
lower score does not replace high score
rankings sorted by high score
```

---

# 16. Server Phase 1 — Core Integration

Implement:

```text
project scaffold
configuration
database connection
players table
inventory_items table
GET /health
POST /auth/login
GET /player/me
```

Success milestone:

```text
Cocos client
    ↓
real HTTP login
    ↓
FastAPI
    ↓
MySQL player
    ↓
Lobby shows real player data
```

Do not implement Shop/Game APIs yet.

---

# 17. Server Phase 2 — Shop + Bag

Implement:

```text
SHOP_PRODUCTS
GET /shop/products
POST /shop/purchase
GET /bag
```

Success milestone:

```text
Cocos Shop
    ↓
FastAPI purchase
    ↓
MySQL gold update
    ↓
MySQL inventory update
    ↓
client refresh
```

---

# 18. Server Phase 3 — Game Result + Ranking

Implement:

```text
POST /game/result
GET /rankings
```

Success milestone:

```text
Cocos mini game
    ↓
submit real score
    ↓
MySQL high_score
    ↓
ranking screen
```

At the end of Phase 3, the server is considered functionally complete for MiniGameClient.

---

# 19. Server Phase 4 — Optional WebSocket Training

Only implement if explicitly requested.

Purpose:

```text
heartbeat
disconnect
reconnect
玩家login后主动向client发送一条notice消息，数据类似Welcom这种
```

Minimal behavior:

```text
client -> ping
server -> pong
```

Do not implement a full realtime game server.

After reconnect, the client should use HTTP:

```text
GET /player/me
GET /bag
```

to restore state.

---

# 20. Explicit Non-Goals

Do not implement initially:

```text
passwords
JWT
refresh tokens
OAuth
real registration
email
real payment
anti-cheat
Redis
Celery
Kafka
RabbitMQ
microservices
admin site
game match server
game state synchronization
database migrations
deployment
production security
```

---

# 21. Definition of Done

The backend is complete enough when MiniGameClient can:

```text
1. health check server
2. login with username
3. receive and store dev token
4. load player data
5. load shop products
6. purchase item
7. persist gold change
8. load persisted bag
9. submit game result
10. load ranking list
```

All of the above should work against a real FastAPI process and MySQL database.
