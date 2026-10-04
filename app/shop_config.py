# 商品配置保持静态，不创建商店数据库表。
SHOP_PRODUCTS = {
    1001: {"name": "Potion", "price": 100, "item_id": 2001},
    1002: {"name": "Chest", "price": 300, "item_id": 2002},
    1003: {"name": "Skin A", "price": 500, "item_id": 2003},
}

ITEM_NAMES = {
    product["item_id"]: product["name"] for product in SHOP_PRODUCTS.values()
}
