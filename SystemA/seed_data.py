"""
陷阱数据初始化脚本
=====================
为 MVC vs MTA 对比实验植入精心设计的"陷阱数据"：
  • ID 101: Wireless Mouse (NORMAL) - 基础操作目标
  • ID 102: iPhone 15 Case (LOCKED) - 业务规则陷阱
  • ID 103: Mechanical Keyboard (NORMAL, stock=0) - 基础删除目标
  • ID 104: USB-C Cable (Black) (NORMAL) - 普通商品
  • ID 105-130: Generic USB Cable x26 (NORMAL) - 分页盲区陷阱(超过limit=20)
  • ID 201: Dell Monitor (NORMAL) - 重名陷阱A
  • ID 202: Dell Monitor (NORMAL) - 重名陷阱B

用法:
    cd SystemA
    python seed_data.py
"""
from database import engine, SessionLocal, Base
from models import Product


def seed():
    """清空并填充陷阱测试数据。"""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        db.query(Product).delete()
        db.commit()

        products = [
            Product(id=101, name="Wireless Mouse", description="A basic wireless mouse",
                    price=50.0, stock=10, status="NORMAL"),
            Product(id=102, name="iPhone 15 Case", description="Protective case for iPhone 15",
                    price=20.0, stock=100, status="LOCKED"),
            Product(id=103, name="Mechanical Keyboard", description="RGB mechanical keyboard",
                    price=150.0, stock=0, status="NORMAL"),
            Product(id=104, name="USB-C Cable (Black)", description="1m USB-C cable",
                    price=10.0, stock=500, status="NORMAL"),
        ]

        # ID 105-130: 26个 Generic USB Cable (超过 limit=20 的分页陷阱)
        for i in range(105, 131):
            products.append(Product(
                id=i, name="Generic USB Cable",
                description=f"Generic USB cable unit #{i - 104}",
                price=5.0, stock=10, status="NORMAL"
            ))

        # ID 201-202: 重名陷阱
        products.append(Product(
            id=201, name="Dell Monitor", description="Dell 24-inch FHD monitor",
            price=200.0, stock=5, status="NORMAL"
        ))
        products.append(Product(
            id=202, name="Dell Monitor", description="Dell 27-inch 4K monitor",
            price=300.0, stock=10, status="NORMAL"
        ))

        db.add_all(products)
        db.commit()

        print("=" * 50)
        print("  陷阱数据初始化完成!")
        print("=" * 50)
        print(f"  总商品数: {len(products)}")
        print(f"  ID 101: Wireless Mouse (NORMAL)")
        print(f"  ID 102: iPhone 15 Case (LOCKED)")
        print(f"  ID 103: Mechanical Keyboard (stock=0)")
        print(f"  ID 104: USB-C Cable (Black)")
        print(f"  ID 105-130: Generic USB Cable x26 (分页陷阱)")
        print(f"  ID 201-202: Dell Monitor x2 (重名陷阱)")
        print("=" * 50)

    except Exception as e:
        db.rollback()
        print(f"数据初始化失败: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
