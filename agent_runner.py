"""
Agent Runner — 产品管理场景的 ReAct 实验循环。

System A: 传统 MVC REST 接口，工具定义干瘪、错误回参冷冰冰。
System B: MTA 工具，每个返回都带 current_state / allowed_next_tools / error_guidance。
"""
import json
import requests
from openai import OpenAI

client = OpenAI(
    api_key="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",
    base_url="https://integrate.api.nvidia.com/v1",
)
#client = OpenAI(
#    api_key="sk-f41e8f0c38094ac38492b91db80b7a9f",
#    base_url="https://api.deepseek.com",
#)

MODEL_NAME = "openai/gpt-oss-120b"
#MODEL_NAME = "deepseek-v4-pro"
#MODEL_NAME = "qwen/qwen3.5-122b-a10b"
TEMPERATURE = 0.0
MAX_STEPS = 10

SYSTEM_A_URL = "http://localhost:8000"
SYSTEM_B_URL = "http://localhost:8001"


# ================================================================
#  System A 工具定义 — 干瘪、面向人类、零业务边界提示
# ================================================================
tools_definition_A = [
    {
        "type": "function",
        "function": {
            "name": "api_v1_products_post",
            "description": "Create a product.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "price": {"type": "number"},
                    "stock": {"type": "integer"},
                },
                "required": ["name", "price"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "api_v1_products_get",
            "description": "List products.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "skip": {"type": "integer"},
                    "limit": {"type": "integer"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "api_v1_products_id_get",
            "description": "Get a product.",
            "parameters": {
                "type": "object",
                "properties": {"product_id": {"type": "integer"}},
                "required": ["product_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "api_v1_products_id_put",
            "description": "Update a product.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "integer"},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "price": {"type": "number"},
                    "stock": {"type": "integer"},
                    "status": {"type": "string"},
                },
                "required": ["product_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "api_v1_products_id_delete",
            "description": "Delete a product.",
            "parameters": {
                "type": "object",
                "properties": {"product_id": {"type": "integer"}},
                "required": ["product_id"],
            },
        },
    },
]


# ================================================================
#  System B 工具定义 — MTA 风格，每个 schema 详细描述业务语义
# ================================================================
tools_definition_B = [
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": (
                "Search and list products in the catalog by optional keyword. "
                "Returns a paginated list. If more records exist beyond the current "
                "page, the response will indicate has_more=true and provide a "
                "next_skip value plus error_guidance telling you how to fetch them. "
                "ALWAYS check has_more in the response before concluding the list is complete."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "Optional substring filter on product name. Leave empty/null for all products.",
                    },
                    "skip": {
                        "type": "integer",
                        "description": "Number of records to skip (pagination offset). Default 0.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max records per page. Default 20.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_product_details",
            "description": (
                "Get a single product's full record by ID. The response includes "
                "current_state ('NORMAL' or 'LOCKED'). LOCKED products cannot be deleted "
                "without first being updated to NORMAL."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "integer",
                        "description": "The integer product ID, e.g. obtained from search_products.",
                    },
                },
                "required": ["product_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_product",
            "description": (
                "Create a new product. Validates: price > 0, stock >= 0. Detects duplicate "
                "names and warns via error_guidance — DO NOT blindly retry on duplicate_name; "
                "first confirm with the user."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Product display name. Non-empty."},
                    "description": {"type": "string", "description": "Optional textual description."},
                    "price": {"type": "number", "description": "Unit price. Must be > 0."},
                    "stock": {"type": "integer", "description": "Initial stock. Must be >= 0."},
                    "idempotency_key": {
                        "type": "string",
                        "description": "A fresh UUID for this distinct creation intent. Generate a NEW UUID for each retry that should be a new attempt.",
                    },
                },
                "required": ["name", "price", "idempotency_key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_product",
            "description": (
                "PARTIAL update of an existing product. CRITICAL: To keep a field "
                "unchanged, OMIT it entirely from the JSON payload. Do NOT pass empty "
                "string '' or 0 — the server will reject those as destructive overwrites "
                "and return error_guidance asking you to retry without those fields."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "integer", "description": "Integer ID of the product to modify."},
                    "name": {"type": "string", "description": "OMIT entirely to keep current name. Do NOT pass ''."},
                    "description": {"type": "string", "description": "OMIT entirely to keep current description."},
                    "price": {"type": "number", "description": "OMIT entirely to keep current price. Must be > 0 if provided."},
                    "stock": {"type": "integer", "description": "OMIT entirely to keep current stock. Must be >= 0 if provided."},
                    "status": {"type": "string", "description": "OMIT entirely to keep current status. Allowed values: 'NORMAL' or 'LOCKED'."},
                    "idempotency_key": {"type": "string", "description": "Fresh UUID for this update."},
                },
                "required": ["product_id", "idempotency_key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_product",
            "description": (
                "Permanently delete a product. WARNING: irreversible. Business rule: "
                "products with status='LOCKED' cannot be deleted directly — you must "
                "first update_product to set status='NORMAL', then call delete_product "
                "with a NEW idempotency_key. The error_guidance will explain this."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "integer", "description": "Integer ID of the product to delete."},
                    "idempotency_key": {"type": "string", "description": "Fresh UUID for this deletion."},
                },
                "required": ["product_id", "idempotency_key"],
            },
        },
    },
]


KNOWN_TOOLS_A = {t["function"]["name"] for t in tools_definition_A}
KNOWN_TOOLS_B = {t["function"]["name"] for t in tools_definition_B}


# ================================================================
#  System A 路由分发 — REST 风格
# ================================================================
def dispatch_tool_A(function_name, arguments):
    """将 LLM 的工具调用路由到 System A 的 REST API。
    返回 (response_text, is_error)。"""
    base = SYSTEM_A_URL
    args = dict(arguments)
    try:
        if function_name == "api_v1_products_post":
            r = requests.post(f"{base}/products", json=args)
        elif function_name == "api_v1_products_get":
            r = requests.get(f"{base}/products", params=args)
        elif function_name == "api_v1_products_id_get":
            pid = args.pop("product_id")
            r = requests.get(f"{base}/products/{pid}")
        elif function_name == "api_v1_products_id_put":
            pid = args.pop("product_id")
            r = requests.put(f"{base}/products/{pid}", json=args)
        elif function_name == "api_v1_products_id_delete":
            pid = args.pop("product_id")
            r = requests.delete(f"{base}/products/{pid}")
        else:
            return json.dumps({"error": f"Unknown function: {function_name}"}), True
        return r.text, r.status_code >= 400
    except Exception as e:
        return json.dumps({"error": str(e)}), True


# ================================================================
#  System B 路由分发 — MTA 统一 POST /tools/{name}
# ================================================================
def dispatch_tool_B(function_name, arguments):
    """将 LLM 的工具调用路由到 System B 的 MTA Tool API。
    返回 (response_text, is_error)。"""
    try:
        r = requests.post(f"{SYSTEM_B_URL}/tools/{function_name}", json=arguments)
        try:
            data = r.json()
            is_error = data.get("error_guidance") is not None
        except Exception:
            is_error = r.status_code >= 400
        return r.text, is_error
    except Exception as e:
        return json.dumps({"error": str(e)}), True


# ================================================================
#  核心引擎 — 带指标记录的 Agent ReAct 循环
# ================================================================
def run_agent_task(task_instruction: str, system: str = "B",
                   max_steps: int = MAX_STEPS, verbose: bool = True):
    """运行单次 Agent 任务并记录所有实验指标。"""
    if system == "A":
        tools = tools_definition_A
        dispatch = dispatch_tool_A
        known_tools = KNOWN_TOOLS_A
    else:
        tools = tools_definition_B
        dispatch = dispatch_tool_B
        known_tools = KNOWN_TOOLS_B

    messages = [
        {"role": "system",
         "content": (
             "You are a careful product-catalog assistant. "
             "Use the provided tools to fulfill the user's request. "
             "If a tool returns an error or error_guidance, READ IT carefully "
             "and follow its instructions exactly. Never silently retry the "
             "same call after an error. When the task is complete or cannot "
             "be fulfilled (e.g. ambiguous user input), provide a final summary."
         )},
        {"role": "user", "content": task_instruction},
    ]

    step_count = 0
    error_count = 0
    recovered_count = 0
    hallucination_count = 0
    last_was_error = False
    agent_exited_normally = False
    final_answer = ""  # 最后一条 assistant content，给 validator 用

    while step_count < max_steps:
        step_count += 1
        if verbose:
            print(f"\n--- [Step {step_count}] Agent thinking (System {system})... ---")

        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=TEMPERATURE,
            )
        except Exception as e:
            if verbose:
                print(f"❌ LLM API Error: {e}")
            error_count += 1
            break

        assistant_message = response.choices[0].message

        if assistant_message.tool_calls:
            messages.append(assistant_message)
            for tool_call in assistant_message.tool_calls:
                fn_name = tool_call.function.name
                try:
                    arguments = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    hallucination_count += 1
                    if verbose:
                        print(f"⚠️  Hallucination: invalid JSON args for {fn_name}")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": fn_name,
                        "content": json.dumps({"error": "Invalid JSON in arguments"}),
                    })
                    last_was_error = True
                    continue

                if fn_name not in known_tools:
                    hallucination_count += 1
                    if verbose:
                        print(f"⚠️  Hallucination: unknown tool '{fn_name}'")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": fn_name,
                        "content": json.dumps({"error": f"Tool '{fn_name}' does not exist."}),
                    })
                    last_was_error = True
                    continue

                if verbose:
                    print(f"🤖 Call: {fn_name}({arguments})")

                result_text, is_error = dispatch(fn_name, arguments)

                if verbose:
                    preview = result_text[:200] + "..." if len(result_text) > 200 else result_text
                    symbol = "❌" if is_error else "✅"
                    print(f"   {symbol} Response: {preview}")

                if is_error:
                    error_count += 1
                    last_was_error = True
                else:
                    if last_was_error:
                        recovered_count += 1
                    last_was_error = False

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": fn_name,
                    "content": result_text,
                })
            continue

        elif assistant_message.content:
            if verbose:
                print(f"🤖 Final: {assistant_message.content[:200]}...")
            messages.append({"role": "assistant", "content": assistant_message.content})
            final_answer = assistant_message.content
            agent_exited_normally = True
            break

        else:
            if verbose:
                print("⚠️  Empty response from LLM")
            break

    if step_count >= max_steps and not agent_exited_normally:
        if verbose:
            print(f"\n❌ Max steps ({max_steps}) reached — possible infinite loop.")

    # 兜底：如果没有正常退出，从 messages 里捞最后一条带 content 的 assistant 消息
    if not final_answer:
        for msg in reversed(messages):
            content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", None)
            role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "role", None)
            if role == "assistant" and isinstance(content, str) and content.strip():
                final_answer = content
                break

    return {
        "agent_exited_normally": agent_exited_normally,
        "total_steps": step_count,
        "error_count": error_count,
        "recovered_count": recovered_count,
        "hallucination_count": hallucination_count,
        "final_answer": final_answer,
        "messages": messages,
    }


# ── 快速测试入口 ──
if __name__ == "__main__":
    print("=== Testing System A ===")
    result_a = run_agent_task("请帮我查询 ID 为 101 的商品的详细信息。", system="A")
    print(f"\nMetrics A: steps={result_a['total_steps']}, "
          f"errors={result_a['error_count']}, "
          f"hallucinations={result_a['hallucination_count']}")

    print("\n\n=== Testing System B ===")
    result_b = run_agent_task("请帮我查询 ID 为 101 的商品的详细信息。", system="B")
    print(f"\nMetrics B: steps={result_b['total_steps']}, "
          f"errors={result_b['error_count']}, "
          f"hallucinations={result_b['hallucination_count']}")