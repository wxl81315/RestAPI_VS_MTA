"""
实验任务定义 (v2 — Final Answer Verification)
=============================================
12 个高区分度的产品管理任务（4 Simple + 4 Medium + 4 Hard）。

Validator 签名说明
------------------
每个 validator 都按需声明参数，run_experiments.py 通过 inspect 自适应分发：
  • 只读类: validate(db_path, final_answer)
  • 拒绝类: validate(db_path, final_answer, error_count)
  • 写入类: validate(db_path)               # DB 终态即可判定

陷阱数据 (由 seed_data.py 植入)
-------------------------------
  ID 101: Wireless Mouse        (NORMAL, stock=10,  price=50)
  ID 102: iPhone 15 Case        (LOCKED, stock=100, price=20)   <- 业务规则陷阱
  ID 103: Mechanical Keyboard   (NORMAL, stock=0,   price=150)
  ID 104: USB-C Cable (Black)   (NORMAL, stock=500, price=10)
  ID 105-130: Generic USB Cable x26 (NORMAL)                    <- 分页盲区陷阱
  ID 201: Dell Monitor (24-FHD) (NORMAL, price=200)             <- 重名陷阱A
  ID 202: Dell Monitor (27-4K)  (NORMAL, price=300)             <- 重名陷阱B
"""
import re
import sqlite3


def _query(db_path, sql, params=()):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return rows


def _query_one(db_path, sql, params=()):
    conn = sqlite3.connect(db_path)
    row = conn.execute(sql, params).fetchone()
    conn.close()
    return row


def _safe(text):
    """把 None / 非字符串安全转成空字符串，方便正则匹配。"""
    return text if isinstance(text, str) else ""


# ============================================================
#  Simple Tasks (S1-S4)
# ============================================================
def validate_task_1(db_path, final_answer):
    """S1 - 搜索包含 'USB' 的商品（只读）。
    成功条件：DB 不变 + Agent 回答里能体现搜到了 USB 类商品。"""
    total = _query_one(db_path, "SELECT COUNT(*) FROM products")[0]
    if total != 32:
        return False
    text = _safe(final_answer).lower()
    # USB-C Cable + 26 件 Generic USB Cable 都应被找到
    return "usb" in text


def validate_task_2(db_path, final_answer):
    """S2 - 查看商品 101 详情（只读）。
    成功条件：DB 101 未变 + Agent 回答中包含名称或价格信息。"""
    row = _query_one(db_path,
                     "SELECT name, price, stock, status FROM products WHERE id=101")
    if not (row and row[0] == "Wireless Mouse"
            and row[1] == 50.0 and row[2] == 10 and row[3] == "NORMAL"):
        return False
    text = _safe(final_answer).lower()
    # 必须包含名字或关键属性
    return "wireless mouse" in text or "50" in text


def validate_task_3(db_path, final_answer):
    """S3 - 查询不存在的商品 ID=999。
    成功条件：DB 不变 + Agent 必须明确告诉用户"找不到/不存在"，
    而不是嘴硬编一份假商品出来。"""
    total = _query_one(db_path, "SELECT COUNT(*) FROM products")[0]
    row = _query_one(db_path, "SELECT id FROM products WHERE id=999")
    if not (total == 32 and row is None):
        return False
    text = _safe(final_answer)
    recognized = bool(re.search(
        r"(not found|不存在|找不到|没有找到|没找到|未找到|"
        r"does not exist|no such|"
        r"系统中没有|目录中没有|没有.{0,4}商品|"
        r"未在.{0,8}找到|没有.{0,4}id|没有.{0,4}该|"
        r"没有任何.{0,8}商品)",
        text, re.IGNORECASE))
    return recognized


def validate_task_4(db_path):
    """S4 - 把 ID 104 的库存改为 999。
    成功条件：DB 终态正确，且其他字段（name/price/status）未被脏写。"""
    row = _query_one(db_path,
                     "SELECT name, price, stock, status FROM products WHERE id=104")
    return (row is not None
            and row[0] == "USB-C Cable (Black)"
            and row[1] == 10.0
            and row[2] == 999
            and row[3] == "NORMAL")


# ============================================================
#  Medium Tasks (M5-M8)
# ============================================================
def validate_task_5(db_path, final_answer, error_count):
    """M5 - 删除 LOCKED 商品 102。
    成功条件：
      (a) 商品 102 仍存在且状态仍为 LOCKED
      (b) 错误次数不爆炸（区分'优雅拦截'和'底层崩溃疯狂重试'）
      (c) Agent 在最终回复里告知用户被拒绝/受保护

    System A: 无业务校验时直接删除 → (a) 失败 → 0 分
              有 LOCKED 拦截时返回 403 → Agent 转告"权限错误/Forbidden"也算合规拦截
    System B: 返回 LOCKED guidance → (a)(b)(c) 通过
    """
    row = _query_one(db_path,
                     "SELECT name, status FROM products WHERE id=102")
    if not (row and row[0] == "iPhone 15 Case" and row[1] == "LOCKED"):
        return False
    if error_count > 3:
        return False  # 抛太多底层异常，不算优雅
    text = _safe(final_answer)
    informed = bool(re.search(
        r"(locked|锁定|受保护|无法删除|cannot delete|不能删除|protected|拒绝|"
        r"forbidden|权限|权限错误|403|不允许|无权|被拒|未能删除|未能完成|删除失败)",
        text, re.IGNORECASE))
    return informed


def validate_task_6(db_path, final_answer):
    """M6 - 把 ID 101 的价格修改成 60，其他字段保持不变。
    部分更新陷阱：System A 的 LLM 极易把 name='' 或 description='' 一起传过去，
    crud.update_product 用 exclude_unset 但 LLM 显式传的字段会被写入 → 脏数据。

    成功条件：
      • name 仍为 'Wireless Mouse'（没被空覆盖）
      • description 仍为原值
      • price = 60
      • stock 仍为 10、status 仍为 NORMAL
    """
    row = _query_one(db_path,
                     "SELECT name, description, price, stock, status FROM products WHERE id=101")
    if row is None:
        return False
    # 抓脏数据：name 不能为空或被改名
    if not row[0] or row[0].strip() == "" or row[0] != "Wireless Mouse":
        return False
    if not row[1] or row[1].strip() == "" or row[1] != "A basic wireless mouse":
        return False
    return row[2] == 60.0 and row[3] == 10 and row[4] == "NORMAL"


def validate_task_7(db_path, final_answer):
    """M7 - 用户要求创建一个 price=-10 的新商品。
    成功条件：
      (a) DB 中没有 price<0 的脏数据，也没有名为 'Faulty Item' 的成品
      (b) Agent 必须在最终回复里告诉用户'价格不能为负/无效'

    System A 没校验 → 直接写入 -10 → (a) 失败 → 0 分
    System A 有校验 → 422 → Agent 转告"价格无效/校验错误"
    System B price<=0 拦截+guidance → Agent 反馈用户 → (a)(b) 通过
    """
    total = _query_one(db_path, "SELECT COUNT(*) FROM products")[0]
    bad = _query_one(db_path,
                     "SELECT id FROM products WHERE name='Faulty Item' OR price<0")
    if not (total == 32 and bad is None):
        return False
    text = _safe(final_answer)
    refused = bool(re.search(
        r"(不能|无效|负数|不允许|negative|invalid|must be|大于 ?0|positive|"
        r"validation|校验|422|不合法|失败|拒绝|无法创建|未能创建|价格.*正|"
        r"价格.*问题|价格.*错|不被允许|不可以)",
        text, re.IGNORECASE))
    return refused


def validate_task_8(db_path):
    """M8 - 删除 stock=0 的 Mechanical Keyboard (ID=103)：可正常删除。
    成功条件：DB 中 ID=103 不存在，总数从 32 减到 31，且未误删其它商品。"""
    row = _query_one(db_path, "SELECT id FROM products WHERE id=103")
    total = _query_one(db_path, "SELECT COUNT(*) FROM products")[0]
    return row is None and total == 31


# ============================================================
#  Hard Tasks (H9-H12)
# ============================================================
def validate_task_9(db_path, final_answer):
    """H9 - 列出所有 Generic USB Cable 并报数（分页盲区陷阱）。
    成功条件：
      • DB 只读未变
      • Agent 回复中必须明确包含正确数字 "26"
      • 不能错答 "20"（即 limit 默认值，说明只看了首页）

    System A: list_products?name=Generic 返回的是默认 limit=20 → Agent 答 20 → 0 分
    System B: search_products 返回 has_more=true + guidance + total_count=26 → Agent 翻页或直接看 total_count → 答 26
    """
    total = _query_one(db_path, "SELECT COUNT(*) FROM products")[0]
    cnt = _query_one(db_path,
                     "SELECT COUNT(*) FROM products WHERE name='Generic USB Cable'")[0]
    if not (total == 32 and cnt == 26):
        return False
    text = _safe(final_answer)
    has_correct = "26" in text
    # 抓"嘴硬答 20"的情况：只有当文本里出现 20 但不出现 26 时才判错
    only_wrong = ("20" in text) and not has_correct
    return has_correct and not only_wrong


def validate_task_10(db_path, final_answer):
    """H10 - 用户明确授权解锁后删除商品 102（多步业务规则）。

    任务文本里用户已经明确说"我授权你删除"+"如果有业务限制请先解除限制"，
    所以合法路径是：先 update_product(status=NORMAL) → 再 delete_product。

    成功条件（必须同时满足）：
      (a) 商品 102 在 DB 中已经不存在（删除已完成）
      (b) Agent 的 final_answer 必须体现"已经完成解锁这一步"——不是预告未来，
          也不是承认无法解锁。要求出现"已 / 已经 / 完成 / 成功 + 解锁/状态变更"
          的过去时态，且不能伴随"无法/失败/未能/没法/cannot/unable"等否定词。

    为什么这么严？
      • A_MVC iter 4 的 final_answer 含"在没有解除锁定的权限..." —— 单纯有
        '解除锁定' 四字会被旧正则误判为 unlocked。新正则要求 unlocked 出现
        在肯定句里。
      • B_MTA 标准成功答案为："已按照您的授权完成... 1. 解除业务限制：将状态
        从 LOCKED 更新为 NORMAL... 2. 删除产品..." —— 含"已...完成"+"从
        LOCKED...为 NORMAL"等强信号。
    """
    # ── 1. 商品 102 必须已被删除 ──
    row = _query_one(db_path, "SELECT id FROM products WHERE id=102")
    if row is not None:
        return False

    text = _safe(final_answer)

    # ── 2. 排除"伪解锁"：明确声称失败/无法解锁的，直接判失败 ──
    if re.search(
        r"(无法.*解(锁|除)|未能.*解(锁|除)|没法.*解(锁|除)|"
        r"在没有.*解(锁|除)|cannot.*unlock|unable.*unlock|"
        r"failed.*unlock|没有.*解锁.*权限|无.*解锁.*权限|"
        r"无法.*完成.*删除|不能.*解(锁|除))",
        text, re.IGNORECASE,
    ):
        return False

    # ── 3. 必须出现"已完成解锁动作"的肯定信号 ──
    unlocked_done = bool(re.search(
        r"(已.*解锁|已解除.*(锁定|限制)|已.*解除(锁定|限制|业务限制)|"
        r"成功.*解(锁|除)|完成.*解(锁|除)|"
        r"已.*将.*状态.*(从|由).*locked.*(改|更新|更改|设置).*?normal|"
        r"已.*将.*locked.*(改|更新|更改|变).*normal|"
        r"状态.*(从|由).*locked.*(改|更新|变).*为.*normal|"
        r"将.*状态.*(从|由).*locked.*(更新|改).*normal|"
        r"locked.*(改|变|更新|更改|设置).*为.*normal|"
        r"updated.*status.*from.*locked.*to.*normal|"
        r"changed.*status.*from.*locked.*to.*normal|"
        r"set.*status.*to.*normal|"
        r"status.*from.*locked.*to.*normal|"
        r"status.*locked.*to.*normal|"
        r"已经.*(解锁|解除))",
        text, re.IGNORECASE,
    ))
    return unlocked_done


def validate_task_11(db_path, final_answer):
    """H11 - 修改 'Dell Monitor' 的价格为 250（重名陷阱）。
    成功条件：
      • 两个 Dell Monitor 价格都未变 (200/300)
      • Agent 必须在回复中向用户澄清"两个/哪一个"

    System A: 没有重名检测，list_products?name=Dell Monitor 给两条，
              Agent 极可能 PUT 第一个 → 价格改了 → 0 分
    System B: search_products 找到两个，Agent 看到 total_count=2 后
              应主动向用户澄清
    """
    rows = _query(db_path,
                  "SELECT id, price FROM products WHERE name='Dell Monitor' ORDER BY id")
    if len(rows) != 2:
        return False
    prices = sorted([r[1] for r in rows])
    if prices != [200.0, 300.0]:
        return False
    text = _safe(final_answer)
    asked = bool(re.search(
        r"(哪一个|哪个|哪一件|哪一款|哪件|哪款|"
        r"两个|两件|两款|多个|多件|多款|"
        r"several|multiple|which one|which|clarify|"
        r"澄清|确认|请告诉我|请问)",
        text, re.IGNORECASE))
    return asked


def validate_task_12(db_path, final_answer):
    """H12 - 再添加一款 'Wireless Mouse'（重名陷阱：必须感知重名，不能脏写）。

    用户的指令故意含糊（"再添加一款 Wireless Mouse"）。一个负责任的 Agent
    应该察觉到"已有同名商品 ID=101"这一事实，并选择以下两种合规路径之一：

      路径 A（保守）：拒绝盲目插入，把决策权抛回用户（"已存在同名/重名/请确认"）。
                     ⇒ DB 中 Wireless Mouse 仍只有 ID=101 一条。
      路径 B（自动消歧）：自动给新商品起一个区分名（如 'Wireless Mouse v2'、
                       'Wireless Mouse Pro'、'Upgraded Wireless Mouse' 等），
                       并把这件事写进 final_answer 告诉用户。
                       ⇒ DB 中除了 ID=101 还有一条名字 *不是字面 'Wireless Mouse'* 的新商品。

    失败条件（脏写实锤）：
      • DB 中出现两条 *字面完全一致* 的 'Wireless Mouse'（A_MVC 行为）
      • DB 中 ID=101 被覆盖（price/name 变了）

    System A: 没有重名检测 → POST 'Wireless Mouse' → DB 出现两条同名 → 失败
    System B: create_product 检测到 duplicate_name → guidance 让 Agent 改名或确认
    """
    # ── 1. ID=101 必须仍是原商品（没被覆盖）──
    row_101 = _query_one(db_path,
                         "SELECT name, price FROM products WHERE id=101")
    if row_101 is None or row_101[0] != "Wireless Mouse" or row_101[1] != 50.0:
        return False

    # ── 2. 抓脏写：DB 中是否出现第二条 *字面一致* 的 "Wireless Mouse" ──
    dirty_dup = _query(
        db_path,
        "SELECT id FROM products WHERE name='Wireless Mouse' AND id != 101"
    )
    if len(dirty_dup) >= 1:
        return False  # MVC 脏写实锤

    # ── 3. 两条合规路径二选一 ──
    text = _safe(final_answer)

    # 路径 A：Agent 把决策抛回用户（包含重名感知关键词）
    aware = bool(re.search(
        r"(已存在|已经.*有|已.*存在|重名|同名|冲突|duplicate|already exists|"
        r"existing|already present|请确认|请选择|请告诉我|确认.*操作|"
        r"do you want|please confirm|which option|您希望)",
        text, re.IGNORECASE))

    # 路径 B：Agent 自动改了名（DB 出现非字面 'Wireless Mouse' 的新条目）
    renamed = _query(
        db_path,
        "SELECT id, name FROM products "
        "WHERE LOWER(name) LIKE '%wireless mouse%' AND name <> 'Wireless Mouse' AND id != 101"
    )
    auto_renamed = len(renamed) >= 1

    return aware or auto_renamed



# ============================================================
#  任务列表
# ============================================================
TASKS = [
    # ── Simple (S1-S4) ──
    {
        "task_id": 1,
        "difficulty": "simple",
        "description": "搜索商品(只读)",
        "instruction": "请帮我搜索名称中包含 'USB' 的所有商品。",
        "validator": validate_task_1,
    },
    {
        "task_id": 2,
        "difficulty": "simple",
        "description": "查看商品详情(只读)",
        "instruction": "请告诉我 ID 为 101 的商品的详细信息。",
        "validator": validate_task_2,
    },
    {
        "task_id": 3,
        "difficulty": "simple",
        "description": "查询不存在的商品(错误处理)",
        "instruction": "请帮我查询 ID 为 999 的商品的详情。",
        "validator": validate_task_3,
    },
    {
        "task_id": 4,
        "difficulty": "simple",
        "description": "更新库存(基本写操作)",
        "instruction": "请把商品 ID 104 的库存修改为 999。",
        "validator": validate_task_4,
    },

    # ── Medium (M5-M8) ──
    {
        "task_id": 5,
        "difficulty": "medium",
        "description": "删除 LOCKED 商品(业务规则陷阱)",
        "instruction": "请删除 ID 为 102 的商品。",
        "validator": validate_task_5,
    },
    {
        "task_id": 6,
        "difficulty": "medium",
        "description": "部分更新陷阱(只改价格)",
        "instruction": "请把 ID 101 的价格修改成 60 元，其他信息保持不变。",
        "validator": validate_task_6,
    },
    {
        "task_id": 7,
        "difficulty": "medium",
        "description": "负价格创建(校验陷阱)",
        "instruction": (
            "请帮我创建一个新商品：名称 'Faulty Item'，价格 -10 元，库存 5 件，"
            "描述 'A test item with negative price'。"
        ),
        "validator": validate_task_7,
    },
    {
        "task_id": 8,
        "difficulty": "medium",
        "description": "删除零库存商品(基本写)",
        "instruction": "请把 ID 为 103 的商品从目录中删除。",
        "validator": validate_task_8,
    },

    # ── Hard (H9-H12) ──
    {
        "task_id": 9,
        "difficulty": "hard",
        "description": "分页盲区(必须翻页才能看全)",
        "instruction": (
            "请帮我列出库存中所有名为 'Generic USB Cable' 的商品，"
            "并告诉我一共有多少件。"
        ),
        "validator": validate_task_9,
    },
    {
        "task_id": 10,
        "difficulty": "hard",
        "description": "解锁后删除(多步业务规则)",
        "instruction": (
            "我授权你删除 ID 为 102 的 'iPhone 15 Case'。"
            "如果有任何业务限制，请先解除限制再完成删除。"
        ),
        "validator": validate_task_10,
    },
    {
        "task_id": 11,
        "difficulty": "hard",
        "description": "重名歧义(必须澄清不能盲改)",
        "instruction": "请把名为 'Dell Monitor' 的商品价格调整为 250 元。",
        "validator": validate_task_11,
    },
    {
        "task_id": 12,
        "difficulty": "hard",
        "description": "重名新增(必须改名或避免覆盖)",
        "instruction": (
            "请再添加一款新商品 'Wireless Mouse'，价格 80 元，库存 5 个，"
            "描述 'Upgraded wireless mouse'。"
        ),
        "validator": validate_task_12,
    },
]
