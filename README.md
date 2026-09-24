# AI Agent API 设计对比实验

本项目是一个用于评估不同 API 设计模式对 AI Agent 任务完成能力影响的实证研究平台。通过对比传统 REST API 与增强型工具 API 在产品管理场景下的表现，量化分析 API 设计对 Agent 效率、错误率和恢复能力的影响。

## 🎯 研究目标

评估两种 API 设计模式对 LLM Agent 的影响：

- **System A (MVC)**：传统 REST API
  - 简洁的工具描述
  - 基础的错误响应（HTTP 状态码 + 错误消息）
  - 面向人类开发者的设计

- **System B (MTA)**：Multi-Tool Agent 增强型 API
  - 工具响应包含状态机信息（`current_state`）
  - 明确的下一步工具建议（`allowed_next_tools`）
  - 上下文相关的错误引导（`error_guidance`）

## 📊 实验设计

### 任务集合
12 个产品管理任务，覆盖三个难度级别：
- **简单任务 (S1-S4)**：搜索商品、查看详情、库存更新
- **中等任务 (M5-M8)**：批量创建、分页查询、状态管理
- **困难任务 (H9-H12)**：边界条件处理、并发控制、幂等性保证

### 数据陷阱
为提高任务区分度，数据库包含多种业务陷阱：
- **业务规则陷阱**：ID 102 为 LOCKED 状态商品，禁止修改
- **分页盲区陷阱**：26 个相似商品（ID 105-130）测试分页处理能力
- **重名陷阱**：Dell Monitor 有两个不同规格（ID 201/202）

### 实验规模
- **12 tasks** × **2 systems** × **30 iterations** = **720 runs**
- 每次运行记录：成功率、交互步数、错误数、恢复次数、幻觉次数

### 评估维度
1. **任务成功率**：Agent 能否正确完成任务
2. **交互效率**：完成任务所需的 API 调用步数
3. **错误触发率**：Agent 触发 API 错误的频率
4. **错误恢复率**：触发错误后成功恢复的比例
5. **幻觉抑制**：Agent 编造不存在信息的频率

## 🚀 快速开始

### 环境要求

- Python 3.8+
- OpenAI API Key 或兼容的 LLM API（支持 DeepSeek、Nvidia NIM 等）

### 1. 安装依赖

```bash
# 安装 System A 依赖
cd SystemA
pip install -r requirements.txt
cd ..

# 安装 System B 依赖
cd SystemB
pip install -r requirements.txt
cd ..

# 安装实验框架依赖
pip install openai matplotlib
```

### 2. 配置 API Key

编辑 `agent_runner.py`，配置您的 LLM API：

```python
# 方案 1: OpenAI GPT
client = OpenAI(
    api_key="your-api-key-here",
    base_url="https://api.openai.com/v1"
)
MODEL_NAME = "gpt-4o"

# 方案 2: DeepSeek
client = OpenAI(
    api_key="your-deepseek-key",
    base_url="https://api.deepseek.com"
)
MODEL_NAME = "deepseek-chat"

# 方案 3: Nvidia NIM
client = OpenAI(
    api_key="your-nvidia-key",
    base_url="https://integrate.api.nvidia.com/v1"
)
MODEL_NAME = "meta/llama-3.1-405b-instruct"
```

### 3. 初始化数据库

```bash
python setup_db.py
```

此步骤会创建包含 32 条陷阱数据的数据库快照，用于每次实验前的重置。

### 4. 启动系统服务

在**三个独立终端**中分别运行：

```bash
# 终端 1 - System A
cd SystemA
uvicorn main:app --port 8000

# 终端 2 - System B
cd SystemB
uvicorn main:app --port 8001

# 终端 3 - 实验运行器（等待服务启动后）
python run_experiments.py
```

## 📝 实验运行选项

```bash
# 运行全部 720 次实验（默认）
python run_experiments.py

# 仅测试 System B（360 次）
python run_experiments.py --system B

# 指定任务和迭代次数（快速测试）
python run_experiments.py --tasks 1,5,9 --iters 3

# 从上次中断处继续
python run_experiments.py --resume
```

实验结果将保存到 `experiment_results.csv`。

## 📈 结果分析

运行完成后，使用分析脚本生成可视化报告：

```bash
# 综合分析（成功率、效率、错误率、恢复率）
python analyze_combo.py

# 生成坡度图（对比两系统的成功率）
python plot_slopegraph.py

# 生成多维度对比图
python plot_three_figs.py
```

## 📂 项目结构

```
experience/
├── SystemA/              # 传统 REST API 实现
│   ├── main.py          # FastAPI 应用入口
│   ├── models.py        # SQLAlchemy ORM 模型
│   ├── crud.py          # 数据库操作层
│   └── routers/         # API 路由定义
├── SystemB/              # 增强型 MTA API 实现
│   ├── main.py
│   ├── state_machine.py # 状态机逻辑
│   ├── idempotency.py   # 幂等性控制
│   └── tools/           # 工具定义
├── agent_runner.py       # ReAct Agent 执行引擎
├── experiment_tasks.py   # 12 个任务定义与验证器
├── run_experiments.py    # 自动化批处理框架
├── setup_db.py           # 数据库初始化脚本
├── analyze_combo.py      # 结果分析脚本
└── experiment_results.csv # 实验数据输出
```

## 🔬 任务示例

**任务 S1** - 搜索包含 "USB" 的商品（简单）
- 验证条件：数据库未修改 + Agent 返回 USB 相关商品信息

**任务 M6** - 分页遍历所有 Generic USB Cable（中等）
- 验证条件：Agent 回答包含 26 个商品，而非只返回第一页

**任务 H10** - 尝试修改 LOCKED 状态商品（困难）
- 验证条件：系统拒绝操作 + Agent 向用户解释无法修改的原因

## 📄 许可证

本项目仅供学术研究使用。

## 🙏 致谢

本实验框架基于 FastAPI、SQLAlchemy 和 OpenAI API 构建。
