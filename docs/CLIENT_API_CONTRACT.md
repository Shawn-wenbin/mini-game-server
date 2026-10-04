# MiniGameClient 客户端交互契约

本文面向 Cocos2d-x + Lua 客户端研发，覆盖 MiniGameServer Phase 1～4 的全部交互。接口以当前服务端实现为准。所有示例的玩家 ID、token、余额、库存和排名仅用于说明，客户端必须读取实际响应。

## 1. 地址、格式与鉴权

本机联调地址：

```text
HTTP_BASE = http://127.0.0.1:8000/api/v1
WS_URL    = ws://127.0.0.1:8000/api/v1/ws
Swagger   = http://127.0.0.1:8000/docs
OpenAPI   = http://127.0.0.1:8000/openapi.json
```

真机的 `127.0.0.1` 指向真机自身。局域网联调时服务端运行：

```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0
```

客户端将 HTTP 和 WebSocket 地址中的主机都替换为开发电脑的局域网 IP，并确保能访问 8000 端口。

HTTP 请求体使用 UTF-8 JSON，POST 必须设置 `Content-Type: application/json`。GET 无请求体。所有 HTTP 成功响应的状态码均为 `200`。除健康检查外，成功结构为：

```json
{"code":0,"message":"ok","data":{}}
```

`data` 的类型由接口决定，可能是对象或数组；错误时为 `null`。客户端先检查网络结果及 HTTP 状态，再检查应用 `code`，仅在成功时更新本地模型。`message` 用于诊断，业务分支依赖状态码和 `code`，不要比较验证错误的英文文本。

**DEV ONLY / NOT SECURE / NOT PRODUCTION AUTH**

登录只需要用户名。返回的 token 为 `dev-{player_id}`，没有密码、签名、有效期或刷新接口，可以伪造。HTTP 受保护接口必须携带：

```http
Authorization: Bearer dev-1
```

token 中的 ID 必须是 1～2147483647 的十进制整数，没有前导零，且玩家必须存在。客户端直接保存并使用登录返回的字符串，避免自行拼接或写死 `dev-1`。

WebSocket 使用 URL 查询参数 `token`，不读取 `Authorization` 请求头：

```text
ws://127.0.0.1:8000/api/v1/ws?token=dev-1
```

无服务端登出接口。退出账号时，客户端关闭 WebSocket、停止心跳和重连计时器、清除当前账号的 token 与缓存；已有开发 token 不会被服务端撤销。

## 2. HTTP 公共错误

以下是已实现的应用错误；HTTP `404/code=1002` 仅表示购买商品不存在，不等同于访问了不存在的接口。

- HTTP `400` / `code=1001`：`not enough gold`，金币不足，购买没有修改状态。
- HTTP `404` / `code=1002`：`product not found`，商品不存在，购买没有修改状态。
- HTTP `401` / `code=2001`：`invalid dev token`，缺少 token、格式不正确或玩家不存在；响应头包含 `WWW-Authenticate: Bearer`。客户端重新登录后再刷新状态。
- HTTP `422` / `code=422`：请求 JSON、字段类型或范围非法；`message` 描述验证问题。客户端修正请求，不应原样重试。
- HTTP `503` / `code=503`：`database unavailable`，请求处理期间发生数据库错误；客户端提示暂时不可用并稍后读取状态。

错误结构示例：

```json
{"code":2001,"message":"invalid dev token","data":null}
```

缺失请求字段或负分错误示例：

```json
{"code":422,"message":"body.score: Input should be greater than or equal to 0","data":null}
```

健康检查不执行数据库查询。其他接口遇到数据库错误时按上述结构返回 `503`；服务端启动时无法连接 MySQL，则服务本身无法启动。

连接超时、断网、握手失败或代理返回的错误可能没有上述 JSON，`NetworkManager` 还要处理空响应、非 JSON 响应和普通 HTTP 错误。规格里预留的 `1003` 目前没有对应 HTTP 接口，客户端不要依赖它。

## 3. 健康检查

**`GET /api/v1/health`，无需鉴权，无请求体。**

```json
{"status":"ok"}
```

用途：启动前确认 HTTP 地址可访问。此响应没有 `code/message/data`，需单独解析；成功只说明 HTTP 服务可响应。

## 4. 开发登录

**`POST /api/v1/auth/login`，无需鉴权。**

请求：

```json
{"username":"alice"}
```

`username` 必须为字符串，去除首尾空白后为 1～50 个字符。空白字符串、数字、`null`、缺失字段或超长用户名返回 `422`。玩家按数据库的用户名比较规则查找；不要依赖 MySQL 默认排序规则区分大小写。首次登录创建玩家，已有玩家登录不会重置资产、背包或最高分。

响应：

```json
{
  "code":0,
  "message":"ok",
  "data":{
    "token":"dev-1",
    "player":{
      "id":1,
      "username":"alice",
      "level":1,
      "gold":1000,
      "diamond":100,
      "high_score":0
    }
  }
}
```

`player.id`、`level`、`gold`、`diamond`、`high_score` 均为整数，`username` 为字符串。首次默认值为等级 1、金币 1000、钻石 100、最高分 0，背包为空。

客户端：`LoginController` 保存 `data.token`，用 `data.player` 初始化 `PlayerModel`，随后连接 WebSocket。HTTP 登录响应不包含 notice；欢迎通知由登录后建立的 WebSocket 主动发送。HTTP 登录可以在不启用 WebSocket 的情况下独立完成。

## 5. 读取当前玩家

**`GET /api/v1/player/me`，需要 Bearer token，无请求体。**

响应：

```json
{
  "code":0,
  "message":"ok",
  "data":{"id":1,"username":"alice","level":1,"gold":900,"diamond":100,"high_score":27}
}
```

`data` 直接是玩家对象，没有 `player` 外层。只读取 token 对应玩家。客户端用整个 `data` 刷新 `PlayerModel`；用于大厅刷新、购买结果不确定时核对余额，以及重连恢复。

## 6. 读取商品

**`GET /api/v1/shop/products`，需要 Bearer token，无请求体。**

响应：

```json
{
  "code":0,
  "message":"ok",
  "data":[
    {"id":1001,"name":"Potion","price":100,"item_id":2001},
    {"id":1002,"name":"Chest","price":300,"item_id":2002},
    {"id":1003,"name":"Skin A","price":500,"item_id":2003}
  ]
}
```

`id` 为商品 ID，购买时发送该值；`item_id` 为背包物品 ID，更新库存时使用该值。两者不能混用。`price` 是单件金币价格，`name` 是显示名称。商品为静态配置，客户端仍应读取接口返回值，避免写死名称、价格或列表顺序。

客户端：`ShopController` 用 `data` 生成列表。此接口需要登录，不能作为匿名启动请求。

## 7. 购买商品

**`POST /api/v1/shop/purchase`，需要 Bearer token。**

请求：

```json
{"product_id":1001}
```

`product_id` 必须为正整数，不接受字符串、小数或布尔值。每次请求仅购买一件，没有 `quantity` 参数。

成功响应：

```json
{
  "code":0,
  "message":"ok",
  "data":{"gold":900,"item":{"item_id":2001,"count":1}}
}
```

`gold` 是购买后的余额，`item.count` 是该物品购买后的总数量。客户端赋值这些结果，不能再对余额扣一次价格，或把 `count` 当作本次增量累加。响应的 `item` 没有 `name` 字段，名称从商品缓存或背包接口获取。

金币不足：HTTP `400`。

```json
{"code":1001,"message":"not enough gold","data":null}
```

商品不存在：HTTP `404`。

```json
{"code":1002,"message":"product not found","data":null}
```

服务端扣金币与增加库存一次提交，失败回滚；并发购买按同一玩家的 MySQL 行锁处理。重复购买会再次扣款并累加库存，Skin A 也按普通可累加物品处理，没有唯一拥有规则。

客户端：购买进行中禁用重复点击；成功后更新余额和库存，或刷新 `/player/me` 与 `/bag`。失败时不修改本地资产。**接口没有幂等键，网络超时后不要自动重发购买**：请求可能已提交但响应丢失，应先读取玩家和背包，核对结果后由用户决定是否再次购买。一次点击即使被重复发送，服务端也会按多次购买处理。

## 8. 读取背包

**`GET /api/v1/bag`，需要 Bearer token，无请求体。**

响应：

```json
{
  "code":0,
  "message":"ok",
  "data":[{"item_id":2001,"name":"Potion","count":2}]
}
```

空背包：

```json
{"code":0,"message":"ok","data":[]}
```

仅返回当前玩家库存，按 `item_id` 升序。`count` 为总数量，`name` 来自静态商品配置；数据库中配置未知的物品名称为 `Unknown`。没有使用、出售或删除物品接口。

客户端：`BagController` 用 `data` 完整替换背包缓存，空数组清空列表；购买或重连后可以再次读取。服务端不会通过 WebSocket 推送背包变化。

## 9. 提交本局成绩

**`POST /api/v1/game/result`，需要 Bearer token。**

请求：

```json
{"score":27}
```

`score` 必须为 0～2147483647 的整数，不接受字符串、小数或布尔值。负数、溢出或字段缺失返回 `422`。

玩家原最高分小于 27 时：

```json
{"code":0,"message":"ok","data":{"score":27,"high_score":27,"new_record":true}}
```

此后提交 10：

```json
{"code":0,"message":"ok","data":{"score":10,"high_score":27,"new_record":false}}
```

`score` 为本次分数，`high_score` 为持久化的最高分，`new_record` 为 JSON 布尔值。只有严格大于旧最高分时刷新纪录，相同分数不会再次刷新；新玩家提交 0 返回 `new_record=false`。并发提交时最高分保留最大值。

客户端：`ResultView` 在结算时提交分数，用 `high_score` 更新 `PlayerModel`，用 `new_record` 控制纪录提示，成功后按需刷新排行榜。接口不奖励资产、不修改等级或背包、不保存对局历史，也不校验反作弊。

成绩重试只会再比较最高分，不会重复发奖；但原请求若已提交，重试的 `new_record` 可能变为 `false`。丢失响应后不能仅凭重试结果判断第一次是否创造纪录，可读取 `/player/me` 核对最高分。

## 10. 读取排行榜

**`GET /api/v1/rankings?limit=20`，无需鉴权，无请求体。**

`limit` 为整数查询参数，默认 20，范围 1～100；`0`、`101`、小数、空字符串等返回 `422`。

响应：

```json
{
  "code":0,
  "message":"ok",
  "data":[
    {"rank":1,"username":"alice","score":100},
    {"rank":2,"username":"bob","score":80}
  ]
}
```

没有玩家时 `data=[]`。按照 `high_score DESC, id ASC` 返回前 `limit` 名，同分玩家仍占连续名次，ID 较小者在前；未提交成绩的玩家以 0 分参与排名。`score` 是最高分，`rank` 为从 1 开始的整数，没有玩家 ID、个人名次查询、赛季、分页或历史榜单。

客户端：`RankView` 按返回数组顺序显示，直接使用 `rank`；成绩提交完成后再请求，避免显示提交前的榜单。

## 11. WebSocket 建连与欢迎通知

**WebSocket `/api/v1/ws?token=<登录返回的 token>`，无 HTTP 请求体。**

仅使用 UTF-8 JSON **文本帧**；JSON 字符串 `"ping"` 和纯文本 `ping` 都不是合法的应用心跳。HTTP 的八个接口保持原契约，WebSocket 不出现在 Swagger/OpenAPI 的 HTTP 路径列表中。

推荐登录顺序：

1. HTTP 登录成功，保存 token 并初始化玩家数据。
2. 使用 token 建立 WebSocket，并先注册消息、错误和断开回调。
3. 服务端握手后查询玩家；成功时无需客户端发送任何消息，主动发送第一条 notice。
4. 收到 notice 才将应用连接标记为鉴权成功并启动心跳。WebSocket `onOpen` 只表示传输建立。

alice 的欢迎通知：

```json
{
  "type":"notice",
  "code":0,
  "message":"ok",
  "data":{"player_id":1,"text":"Welcome, alice!"}
}
```

`type` 用于消息分发，`data.player_id` 为当前账号的 ID，`data.text` 为可展示的欢迎文本。每个成功鉴权的连接只主动发送一次欢迎通知，重连会再次发送。HTTP 登录时若没有 WebSocket，则不会发送通知；也没有离线队列、历史补发或投递确认。

该通知不是玩家状态快照，客户端仍以 HTTP 数据恢复余额、最高分和背包。连接建立后不再查询数据库，不持续校验 token，也不会主动推送购买、成绩或排名变化。

## 12. WebSocket 心跳与错误

客户端发送：

```json
{"type":"ping"}
```

服务端逐条响应：

```json
{"type":"pong","code":0,"message":"ok","data":null}
```

ping 只接受 `type` 字段；附加时间戳、请求 ID、`data` 等字段会触发验证错误。服务端不主动发送应用 ping，也没有应用层空闲超时。协议层的 WebSocket Ping/Pong 控制帧由网络库处理，不能替代本节 JSON 心跳。

客户端建议每 10 秒发送一次 JSON ping，收到对应 pong 前不再发送下一次；5 秒没有收到 pong 则主动关闭旧连接并重连。这些时间是客户端建议值，服务端没有强制要求。建连后 5 秒未收到 notice 也可视为鉴权/网络等待超时。

非法 JSON、非对象消息、未知 `type`、缺失 `type` 或多余字段：

```json
{
  "type":"error",
  "code":422,
  "message":"invalid websocket message; expected {\"type\":\"ping\"}",
  "data":null
}
```

连接保持可用，后续合法 ping 仍能收到 pong。客户端修正序列化或消息类型，不要对格式错误无限重试。

token 缺失、非法或玩家不存在时，服务端在握手完成后发送：

```json
{"type":"error","code":2001,"message":"invalid dev token","data":null}
```

随后关闭，关闭码 `1008`，原因 `invalid dev token`；不会先发送 notice。客户端停止使用旧 token 重连，重新 HTTP 登录后建立新连接。

鉴权时数据库故障：

```json
{"type":"error","code":503,"message":"database unavailable","data":null}
```

随后关闭，关闭码 `1011`，原因 `database unavailable`。稍后可以使用原 token 重连。已鉴权连接的心跳不依赖数据库，因此数据库随后故障不必然中断该连接；HTTP 状态读取仍可能失败。

发送二进制帧时，即使内容是合法 JSON，也会收到：

```json
{"type":"error","code":422,"message":"binary websocket messages are not supported","data":null}
```

随后关闭，关闭码 `1003`，原因 `unsupported data`。客户端改用文本帧后再连接。

上述关闭码属于 WebSocket，不是 HTTP 状态码。正常退出时客户端可发送关闭码 `1000`。断网或进程停止时可能只收到断开事件，或者网络库报告 `1006`，不保证先收到 error 消息；客户端必须同时处理消息和断开回调。

## 13. 断线、重连与状态恢复

WebSocket 不影响 HTTP 接口的独立使用，断线也不会重置 MySQL 状态。服务端不保存连接会话、重连次数或历史心跳，客户端每次重连都是一次新的连接和鉴权。

客户端恢复步骤：

1. 旧连接断开或心跳超时：停止旧心跳，清理旧连接引用，确保只有一个重连任务。
2. 账号仍有效且未主动退出时，使用现有 token 重连；网络故障建议按 1、2、4、8 秒退避，之后最多每 10 秒重试。鉴权错误先登录，消息格式错误先修正。
3. 新连接收到 notice 后，通过 HTTP 并行读取 `GET /api/v1/player/me` 和 `GET /api/v1/bag`，两个请求均添加 Bearer token。
4. 用玩家对象和完整背包数组替换缓存，两个请求成功后再标记业务状态已恢复；失败的读取可以单独重试，不能因为收到 notice 就认为数据恢复完成。
5. 商店或排行榜正在显示时，再按需刷新商品和排行榜；服务端不会补发断线期间的变化。

账号切换或退出应使旧请求、旧连接的回调失效，避免迟到的响应写入新账号。刷新期间可暂时禁用购买和结算提交，避免状态读取与修改的响应交错；多个更新响应到达时也不要让更早的旧快照覆盖新的结果。

未知 `type` 的服务端消息可忽略并记录日志，便于以后兼容扩展。`data=null` 和 `data=[]` 含义不同，Lua JSON 解析时要按实际库的空值表示处理；不要将布尔 `false`、整数 0 或空数组当成请求失败。

## 14. 客户端模块接入清单

- `NetworkManager`：HTTP JSON、Bearer 头、健康检查特例、HTTP 状态及应用 code、网络超时、WebSocket JSON 文本帧和连接生命周期。
- `LoginController`：登录、保存 token、初始化 `PlayerModel`、登录后建连、鉴权失败重新登录、退出时清理旧账号任务。
- `PlayerModel`：登录和 `/player/me` 的完整玩家数据，购买后的金币，以及结算后的最高分。
- `ShopController`：商品列表、商品 ID 购买、进行中禁用重复点击、金币不足提示、超时后读取状态确认。
- `BagController`：用 `/bag` 数组替换缓存，用购买结果赋值对应物品总数量。
- `ResultView`：提交本局整数分数、展示最高分与新纪录标志、提交成功后刷新排行榜。
- `RankView`：公开榜单读取、按响应顺序展示、空数组空态。
- WebSocket 连接逻辑：notice 展示、单个心跳计时器、pong 超时、单个重连任务、重连后 HTTP 恢复玩家及背包。

## 15. 联调验收与命令

服务端启动：

```bash
uv sync --locked
cp .env.example .env
docker compose up -d --wait db
uv run uvicorn app.main:app --reload
```

已有 `.env` 时保留自己的配置，跳过复制步骤。另一个终端先登录，将 `TOKEN` 替换为返回的实际 token：

```bash
curl -i http://127.0.0.1:8000/api/v1/health
curl -i -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' -d '{"username":"client_contract_demo"}'

TOKEN=dev-1

curl -i http://127.0.0.1:8000/api/v1/player/me -H "Authorization: Bearer $TOKEN"
curl -i http://127.0.0.1:8000/api/v1/shop/products -H "Authorization: Bearer $TOKEN"
curl -i http://127.0.0.1:8000/api/v1/bag -H "Authorization: Bearer $TOKEN"
curl -i -X POST http://127.0.0.1:8000/api/v1/shop/purchase \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"product_id":1001}'
curl -i -X POST http://127.0.0.1:8000/api/v1/game/result \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"score":27}'
curl -i 'http://127.0.0.1:8000/api/v1/rankings?limit=20'
```

以下脚本使用现有 Uvicorn standard 依赖中的 `websockets`，读取上方 `TOKEN`，检查主动 notice、pong、正常断开、重连和 HTTP 状态恢复：

```bash
MINIGAME_DEV_TOKEN="$TOKEN" uv run python - <<'PY'
import asyncio
import json
import os

import httpx
from websockets.asyncio.client import connect

token = os.environ["MINIGAME_DEV_TOKEN"]

async def verify():
    url = f"ws://127.0.0.1:8000/api/v1/ws?token={token}"
    for attempt in range(2):
        async with connect(url) as ws:
            notice = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            assert notice["type"] == "notice", notice
            print("连接", attempt + 1, notice)
            await ws.send(json.dumps({"type": "ping"}))
            pong = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            assert pong == {"type": "pong", "code": 0, "message": "ok", "data": None}
            print(pong)
            if attempt == 1:
                async with httpx.AsyncClient() as client:
                    for path in ("player/me", "bag"):
                        response = await client.get(
                            f"http://127.0.0.1:8000/api/v1/{path}",
                            headers={"Authorization": f"Bearer {token}"},
                        )
                        response.raise_for_status()
                        print(path, response.json())

asyncio.run(verify())
PY
```

客户端验收应覆盖：首次和重复登录、空背包、重复购买、金币不足、未知商品、零分/新纪录/低分、榜单排序和数量边界、非法 token、主动 notice、连续心跳、格式错误、主动退出、网络断开、重连恢复。全新账号第一次购买 Potion 后应为 900 金币及物品 2001 数量 1；同名账号重复测试不会重置，需要使用新用户名或依据已有数据判断。

重启服务后，用同名账号重新登录并读取玩家、背包、排名，持久化数据应保持。客户端通过断网或暂停服务验证自己的超时、退避和恢复状态流程，TestClient 无法代替真机联调。

## 16. 范围与简化

服务端提供真实 HTTP/WebSocket、真实 FastAPI 进程和 MySQL 持久化，仅有 `players`、`inventory_items` 两张表。Phase 4 不新增数据库表或字段。

开发 token 可伪造，商品静态配置，购买无幂等键，成绩信任客户端，排名无分页/赛季。WebSocket 仅用于欢迎通知和心跳训练，没有实时对局、状态同步、连接管理中心、多端互斥、可靠消息投递或服务端自动重连。局域网接入不改变这些开发简化。
