"""
自动化实验批处理引擎
====================
12 tasks × 2 systems × 30 iterations = 720 runs

用法:
    python run_experiments.py                          # 运行全部 720 次
    python run_experiments.py --system B               # 仅跑 System B (360 次)
    python run_experiments.py --tasks 1,5,9 --iters 3  # 指定任务和迭代次数
    python run_experiments.py --resume                  # 从上次中断处继续

前置条件:
    1. python setup_db.py             # 创建数据库快照
    2. cd SystemA && uvicorn main:app --port 8000  (另开终端)
    3. cd SystemB && uvicorn main:app --port 8001  (另开终端)
"""
import os
import sys
import csv
import time
import inspect
import argparse
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

# 将项目根目录加入 path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from setup_db import reset_db, get_db_path
from experiment_tasks import TASKS
from agent_runner import run_agent_task

# ── CSV 配置 ──────────────────────────────────
CSV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "experiment_results.csv")
CSV_HEADERS = [
    "Task_ID", "Difficulty", "System", "Iteration",
    "Success", "Total_Steps", "Error_Count",
    "Recovered_Count", "Hallucination_Count",
    "Final_Answer", "Timestamp",
]


def init_csv():
    """如果 CSV 文件不存在，创建并写入表头。"""
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_HEADERS)


def append_csv(row: dict):
    """追加一行数据到 CSV。"""
    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([row[h] for h in CSV_HEADERS])


def get_completed_runs():
    """读取已完成的 (Task_ID, System, Iteration) 集合，用于断点续跑。"""
    completed = set()
    if os.path.exists(CSV_FILE):
        with open(CSV_FILE, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                key = (int(row["Task_ID"]), row["System"], int(row["Iteration"]))
                completed.add(key)
    return completed


def check_servers():
    """检查 System A 和 System B 服务器是否在线。"""
    import requests
    for name, url in [("System A (8000)", "http://localhost:8000/"),
                      ("System B (8001)", "http://localhost:8001/")]:
        try:
            r = requests.get(url, timeout=3)
            if r.status_code == 200:
                print(f"  ✅ {name} — 在线")
            else:
                print(f"  ⚠️ {name} — 状态码 {r.status_code}")
        except Exception:
            print(f"  ❌ {name} — 无法连接！请先启动服务器。")
            return False
    return True


def _call_validator(validator, db_path, final_answer, error_count):
    """根据 validator 的形参名自适应传递 final_answer / error_count。

    支持的签名：
      • validator(db_path)
      • validator(db_path, final_answer)
      • validator(db_path, final_answer, error_count)
    """
    try:
        params = inspect.signature(validator).parameters
    except (TypeError, ValueError):
        return validator(db_path)

    kwargs = {}
    if "final_answer" in params:
        kwargs["final_answer"] = final_answer
    if "error_count" in params:
        kwargs["error_count"] = error_count
    return validator(db_path, **kwargs)


def run_single(task, system, iteration, db_path, verbose=False):
    """执行单次实验：重置DB → 跑Agent → 验证 → 返回结果行。"""

    # 1. 重置数据库
    reset_db()

    # 2. 运行 Agent
    result = run_agent_task(
        task_instruction=task["instruction"],
        system=system,
        verbose=verbose,
    )

    final_answer = result.get("final_answer", "") or ""
    error_count = result.get("error_count", 0)

    # 3. 三层验证（Agent 正常退出 + DB 状态 + Final Answer 关键词）
    agent_ok = result["agent_exited_normally"]
    db_correct = False
    try:
        db_correct = _call_validator(task["validator"], db_path,
                                     final_answer, error_count)
    except Exception as e:
        if verbose:
            print(f"  ⚠️ Validator error: {e}")

    success = 1 if (agent_ok and db_correct) else 0

    return {
        "Task_ID": task["task_id"],
        "Difficulty": task["difficulty"],
        "System": f"{'A_MVC' if system == 'A' else 'B_MTA'}",
        "Iteration": iteration,
        "Success": success,
        "Total_Steps": result["total_steps"],
        "Error_Count": result["error_count"],
        "Recovered_Count": result["recovered_count"],
        "Hallucination_Count": result["hallucination_count"],
        "Final_Answer": final_answer.replace("\n", " ").replace("\r", " ")[:500],
        "Timestamp": datetime.now().isoformat(),
    }


def main():
    parser = argparse.ArgumentParser(description="E-commerce Agent 实验批处理引擎")
    parser.add_argument("--system", choices=["A", "B", "both"], default="both",
                        help="测试哪个系统 (默认: both)")
    parser.add_argument("--tasks", type=str, default=None,
                        help="指定任务ID，逗号分隔 (例: 1,5,9)")
    parser.add_argument("--iters", type=int, default=30,
                        help="每个任务的迭代次数 (默认: 30)")
    parser.add_argument("--resume", action="store_true",
                        help="断点续跑：跳过已完成的 (Task_ID, System, Iteration)")
    parser.add_argument("--verbose", action="store_true",
                        help="打印详细 Agent 日志")
    args = parser.parse_args()

    # 解析参数
    systems = ["A", "B"] if args.system == "both" else [args.system]
    if args.tasks:
        task_ids = [int(x.strip()) for x in args.tasks.split(",")]
        tasks = [t for t in TASKS if t["task_id"] in task_ids]
    else:
        tasks = TASKS
    iterations = args.iters

    total_runs = len(tasks) * len(systems) * iterations
    print("=" * 60)
    print("  E-commerce Agent 实验批处理引擎")
    print("=" * 60)
    print(f"  任务数:   {len(tasks)}")
    print(f"  系统:     {', '.join(systems)}")
    print(f"  迭代次数: {iterations}")
    print(f"  总计:     {total_runs} 次运行")
    print(f"  CSV 输出: {CSV_FILE}")
    print("=" * 60)

    # 检查服务器
    print("\n🔍 检查服务器状态...")
    if not check_servers():
        print("\n❌ 服务器未就绪，请先启动后再运行。")
        sys.exit(1)

    # 检查快照
    from setup_db import SNAPSHOT_PATH
    if not os.path.exists(SNAPSHOT_PATH):
        print("\n❌ 数据库快照不存在，请先运行: python setup_db.py")
        sys.exit(1)

    # 初始化 CSV
    init_csv()

    # 断点续跑
    completed = get_completed_runs() if args.resume else set()
    if completed:
        print(f"\n📋 已完成 {len(completed)} 次，将跳过这些运行。")

    db_path = get_db_path()
    done = 0
    skipped = 0
    failed = 0

    start_time = time.time()

    for task in tasks:
        for system in systems:
            system_label = "A_MVC" if system == "A" else "B_MTA"
            for iteration in range(1, iterations + 1):
                run_key = (task["task_id"], system_label, iteration)

                # 跳过已完成
                if run_key in completed:
                    skipped += 1
                    continue

                done += 1
                progress = done + skipped
                elapsed = time.time() - start_time
                eta = (elapsed / done * (total_runs - skipped - done)) if done > 0 else 0

                print(f"\n[{progress}/{total_runs}] "
                      f"T{task['task_id']}({task['difficulty']}) "
                      f"× {system_label} "
                      f"× iter {iteration}  "
                      f"(ETA: {eta/60:.1f}min)")

                try:
                    row = run_single(task, system, iteration, db_path,
                                     verbose=args.verbose)
                    append_csv(row)

                    symbol = "✅" if row["Success"] else "❌"
                    print(f"   {symbol} Success={row['Success']} "
                          f"Steps={row['Total_Steps']} "
                          f"Errors={row['Error_Count']} "
                          f"Recovered={row['Recovered_Count']} "
                          f"Halluc={row['Hallucination_Count']}")

                    if not row["Success"]:
                        failed += 1

                except KeyboardInterrupt:
                    print("\n\n⏸️  用户中断。已保存的数据在 CSV 中。")
                    print(f"   使用 --resume 参数可从中断处继续。")
                    sys.exit(0)

                except Exception as e:
                    print(f"   💥 异常: {e}")
                    # 写入失败记录
                    append_csv({
                        "Task_ID": task["task_id"],
                        "Difficulty": task["difficulty"],
                        "System": system_label,
                        "Iteration": iteration,
                        "Success": 0,
                        "Total_Steps": 0,
                        "Error_Count": 1,
                        "Recovered_Count": 0,
                        "Hallucination_Count": 0,
                        "Final_Answer": f"EXCEPTION: {e}"[:500],
                        "Timestamp": datetime.now().isoformat(),
                    })
                    failed += 1

    # ── 汇总 ──
    total_time = time.time() - start_time
    print("\n" + "=" * 60)
    print("  实验完成!")
    print("=" * 60)
    print(f"  总运行: {done}")
    print(f"  跳过:   {skipped}")
    print(f"  失败:   {failed}")
    print(f"  耗时:   {total_time/60:.1f} 分钟")
    print(f"  结果:   {CSV_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()
