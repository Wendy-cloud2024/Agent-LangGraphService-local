-- 服装电商数据库 Schema
-- 只做 4 张表: 商品、商品详情(含尺码)、客户、订单

-- 商品表
CREATE TABLE IF NOT EXISTS products (
    sku         TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    category    TEXT NOT NULL,       -- 上衣/裤子/连衣裙/外套/卫衣
    price       REAL NOT NULL,
    color       TEXT,
    material    TEXT,                 -- 纯棉/涤纶/羊毛/牛仔布/丝绸
    image_url   TEXT,
    status      TEXT DEFAULT 'active',
    created_at  TEXT DEFAULT (datetime('now'))
);

-- 商品详情 + 尺码表 (每个SKU每个尺码一行)
CREATE TABLE IF NOT EXISTS product_details (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sku             TEXT NOT NULL REFERENCES products(sku),
    size            TEXT NOT NULL,           -- S/M/L/XL/XXL
    height_range    TEXT,                     -- "160-165cm"
    weight_range    TEXT,                     -- "45-55kg"
    chest           REAL,                     -- 胸围(cm) - 上衣用
    shoulder        REAL,                     -- 肩宽(cm) - 上衣用
    length          REAL,                     -- 衣长(cm)
    sleeve          REAL,                     -- 袖长(cm) - 上衣用
    waist           REAL,                     -- 腰围(cm) - 裤子用
    hip             REAL,                     -- 臀围(cm) - 裤子用
    inseam          REAL,                     -- 内缝长(cm) - 裤子用
    description     TEXT,                     -- 版型描述: 修身/宽松/常规
    care_instructions TEXT,                   -- 洗涤说明
    UNIQUE(sku, size)
);

-- 客户表
CREATE TABLE IF NOT EXISTS customers (
    customer_id     TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    gender          TEXT,                     -- 男/女
    height          REAL,                     -- 身高(cm)
    weight          REAL,                     -- 体重(kg)
    phone           TEXT,
    address         TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

-- 订单表 (简化: 每条记录=一件衣服)
CREATE TABLE IF NOT EXISTS orders (
    order_id        TEXT PRIMARY KEY,
    customer_id     TEXT REFERENCES customers(customer_id),
    sku             TEXT REFERENCES products(sku),
    product_name    TEXT,
    size            TEXT,
    quantity        INTEGER DEFAULT 1,
    total_price     REAL,
    status          TEXT DEFAULT 'pending',   -- pending/paid/shipped/delivered/cancelled/refunded
    tracking_number TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_product_details_sku ON product_details(sku);
CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
