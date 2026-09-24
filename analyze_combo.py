"""
最终连招分析 + 可视化：
  Dim1 - 平均交互步数 (Efficiency)
  Dim2 - API 错误触发率 (Error Trigger Rate)
  Dim3 - 错误恢复率 (Error Recovery Rate)
  Chart - 分组柱状图（成功率 by Task）
"""
import csv
from collections import defaultdict

import matplotlib.pyplot as plt
import matplotlib

# Use default English-compatible font (Arial / DejaVu Sans)
matplotlib.rcParams["font.sans-serif"] = ["Arial", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False

ROWS = list(csv.DictReader(open("experiment_results.csv", encoding="utf-8")))


def by_system(s):
    return [r for r in ROWS if r["System"] == s]


def succ_only(rs):
    return [r for r in rs if r["Success"] == "1"]


def num(r, k):
    return int(r[k])


# ── Dim1 - 平均步数 ──
print("=" * 78)
print("【维度 1 — 平均交互步数 Efficiency】")
print("=" * 78)
print(f"{'System':<8} {'N':>4} {'Success':>8} {'AvgSteps(全部)':>16} {'AvgSteps(成功)':>16}")
print("-" * 70)
for s in ["A_MVC", "B_MTA"]:
    rs = by_system(s)
    succ = succ_only(rs)
    avg_all = sum(num(r, "Total_Steps") for r in rs) / len(rs)
    avg_succ = sum(num(r, "Total_Steps") for r in succ) / max(len(succ), 1)
    print(f"{s:<8} {len(rs):>4} {len(succ):>8} {avg_all:>16.2f} {avg_succ:>16.2f}")

print("\n参照：人类在 Web UI 完成相同业务（搜索 + 验证 + 写入 + 二次确认）"
      "通常需要 5~10 次有效点击。")
print("Agent 平均 ~2.2 步即完成 → 比人类 UI 操作快 ~3-5×")


# ── Dim2 - 错误触发率 ──
print("\n" + "=" * 78)
print("【维度 2 — API 错误触发率 Error Trigger Rate】")
print("=" * 78)
print("注意指标语义：")
print("  A_MVC 的 Error = HTTP 4xx/5xx 真实错误（请求被拒）")
print("  B_MTA 的 Error = 响应里 error_guidance != None（被语义层拦截，并不是 5xx）")
print("-" * 70)
print(f"{'System':<8} {'TotalSteps':>12} {'TotalErrors':>13} {'Err/Run':>10} "
      f"{'Err/Step':>10}")
print("-" * 70)
for s in ["A_MVC", "B_MTA"]:
    rs = by_system(s)
    total_steps = sum(num(r, "Total_Steps") for r in rs)
    total_err = sum(num(r, "Error_Count") for r in rs)
    err_per_run = total_err / len(rs)
    err_per_step = total_err / max(total_steps, 1) * 100
    print(f"{s:<8} {total_steps:>12} {total_err:>13} {err_per_run:>10.2f} "
          f"{err_per_step:>9.1f}%")

# A 各任务的真实 4xx 错误来源
print("\n  A_MVC 各任务的 Error_Count（真实 HTTP 错误）:")
for t in range(1, 13):
    rs = [r for r in by_system("A_MVC") if int(r["Task_ID"]) == t]
    err = sum(num(r, "Error_Count") for r in rs)
    if err > 0:
        print(f"    T{t}: {err} 次（{rs[0]['Difficulty']}）")

print("\n  B_MTA 各任务的 Error_Count（被 guidance 拦截）:")
for t in range(1, 13):
    rs = [r for r in by_system("B_MTA") if int(r["Task_ID"]) == t]
    err = sum(num(r, "Error_Count") for r in rs)
    if err > 0:
        print(f"    T{t}: {err} 次（{rs[0]['Difficulty']}）")


# ── Dim3 - 恢复率 ──
print("\n" + "=" * 78)
print("【维度 3 — 错误恢复率 Error Recovery Rate（P3 Fault Tolerance 核心证据）】")
print("=" * 78)
print(f"{'System':<8} {'Errors':>8} {'Recovered':>11} {'恢复率':>10}")
print("-" * 50)
for s in ["A_MVC", "B_MTA"]:
    rs = by_system(s)
    err = sum(num(r, "Error_Count") for r in rs)
    rec = sum(num(r, "Recovered_Count") for r in rs)
    rate = rec / err * 100 if err > 0 else 0
    print(f"{s:<8} {err:>8} {rec:>11} {rate:>9.1f}%")

# B 在哪些任务有 recovered 行为？
print("\n  B_MTA 各任务的 Recovered（成功修正路线）:")
for t in range(1, 13):
    rs = [r for r in by_system("B_MTA") if int(r["Task_ID"]) == t]
    rec = sum(num(r, "Recovered_Count") for r in rs)
    err = sum(num(r, "Error_Count") for r in rs)
    if rec > 0:
        print(f"    T{t}: error={err}, recovered={rec} ({rec/err*100:.0f}% of errors)")


# ── 画图：分组柱状图（成功率） ──
tasks = list(range(1, 13))
a_rates, b_rates = [], []
for t in tasks:
    a = [r for r in by_system("A_MVC") if int(r["Task_ID"]) == t]
    b = [r for r in by_system("B_MTA") if int(r["Task_ID"]) == t]
    a_rates.append(sum(num(r, "Success") for r in a) / len(a) * 100)
    b_rates.append(sum(num(r, "Success") for r in b) / len(b) * 100)

fig, ax = plt.subplots(figsize=(13, 6.5))
x = list(range(len(tasks)))
w = 0.38
b1 = ax.bar([i - w/2 for i in x], a_rates, w, label="A_MVC (Traditional REST)",
            color="#3F6FB5", edgecolor="black", linewidth=0.6)
b2 = ax.bar([i + w/2 for i in x], b_rates, w, label="B_MTA (MTA Tools)",
            color="#4CAF50", edgecolor="black", linewidth=0.6)

ax.set_xticks(x)
ax.set_xticklabels([f"T{t}" for t in tasks])
ax.set_ylabel("Success Rate (%)", fontsize=12)
ax.set_xlabel("Task ID", fontsize=12)
ax.set_title("MVC vs MTA — Agent Success Rate per Task  (n=30 per task per system)",
             fontsize=14, fontweight="bold")
ax.set_ylim(0, 109)
ax.set_yticks([0, 20, 40, 60, 80, 100])
ax.grid(axis="y", linestyle="--", alpha=0.4)
ax.legend(loc="lower left", fontsize=11, framealpha=0.95)

# Value labels on top of bars
for bar, val in zip(b1, a_rates):
    ax.text(bar.get_x() + bar.get_width()/2, val + 1.5, f"{val:.0f}",
            ha="center", fontsize=8.5, color="#1A3A6E")
for bar, val in zip(b2, b_rates):
    ax.text(bar.get_x() + bar.get_width()/2, val + 1.5, f"{val:.0f}",
            ha="center", fontsize=8.5, color="#1B5E20")

# Overall success rate annotation
a_overall = sum(a_rates) / len(a_rates)
b_overall = sum(b_rates) / len(b_rates)
ax.text(0.99, 0.96,
        f"Overall: A_MVC {a_overall:.1f}%   vs   B_MTA {b_overall:.1f}%",
        transform=ax.transAxes, ha="right", va="top",
        fontsize=11, fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="#FFF4D6",
                  edgecolor="#B8860B", linewidth=1.2))

plt.tight_layout()
out = "chart_success_rate.png"
plt.savefig(out, dpi=160, bbox_inches="tight")
print(f"\n[OK] Chart saved: {out}")
