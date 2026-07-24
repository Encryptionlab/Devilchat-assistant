"""
全流水线运行 —— 一条消息进，分析 + 需求识别 + 目标确定 + 策略选择 + 回复生成。

用法：
    python run.py "今天好烦"
    python run.py "周末要搬家，累死了"
    python run.py "你是不是不爱我了"
"""

import json
import sys
from pathlib import Path

import requests

from message_understanding import MessageUnderstanding, load_relationship_state
from need_recognition import NeedRecognizer
from goal_planner import GoalPlanner
from strategy_selector import StrategySelector
from reply_generator import ReplyGenerator
from expression_enhancer import ExpressionEnhancer

# NEW: Conversation Engine (v2 MVP)
from conversation import ConversationManager
from context_builder import ContextBuilder
from datetime import datetime, timezone

# ---- 配置 ----
ROOT = Path(__file__).parent
BASE_URL = "https://opencode.ai/zen/go/v1/chat/completions"
MODEL = "deepseek-v4-flash"
HER_MESSAGE = sys.argv[1] if len(sys.argv) > 1 else "今天好烦"

# 从 ds.txt 读取密钥
key_file = ROOT / "ds.txt"
if key_file.exists():
    API_KEY = key_file.read_text(encoding="utf-8").strip().split("=")[-1].strip()
else:
    print("[错误] 找不到 ds.txt，请创建并写入 api = your-key")
    sys.exit(1)


def llm_chat(system_prompt: str, user_prompt: str) -> str:
    """封装 LLM 调用，供消息理解和回复生成共用。"""
    resp = requests.post(
        BASE_URL,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": MODEL,
            "max_tokens": 4096,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        },
    )
    if resp.status_code != 200:
        raise RuntimeError(f"API 返回 {resp.status_code}: {resp.text}")
    return resp.json()["choices"][0]["message"]["content"]

# ---- 1. 加载关系状态 ----
rs = load_relationship_state()
print(f"[关系状态] stage={rs['stage']} trust={rs['trust_level']} intimacy={rs['intimacy_level']} conflict={rs['conflict_status']}")
print()

# ---- 2. 消息理解 (LLM) ----
mu = MessageUnderstanding()
user_prompt = mu.build_user_prompt([{"role": "她", "content": HER_MESSAGE}])

llm_output = llm_chat(mu.system_prompt, user_prompt)

try:
    ms = mu.parse_to_state(llm_output)
except Exception as e:
    print(f"解析失败，LLM 原始输出:\n{llm_output}")
    sys.exit(1)

# ---- 显示消息理解 ----
print("=" * 60)
print("1. 消息理解 (Message Understanding)")
print("=" * 60)

print("surface_intent_scores:")
for intent, score in sorted(ms.surface_intent_scores.items(), key=lambda x: -x[1]):
    bar = "#" * int(score * 20)
    print(f"  {intent:25s} {score:.2f} {bar}")

print("need_scores:")
for need, score in sorted(ms.need_scores.items(), key=lambda x: -x[1]):
    bar = "#" * int(score * 20)
    print(f"  {need:25s} {score:.2f} {bar}")

print(f"emotion: {ms.emotion}  intensity: {ms.emotion_intensity}")
print(f"expression_mode: {ms.expression_mode}  state_type: {ms.state_type}")
print(f"conversation_stage: {ms.conversation_stage}")
print(f"conflict_signal: {ms.conflict_signal}")
print(f"has_metaphor: {ms.has_metaphor}")
print()

# ---- 3. 需求识别 (规则) ----
print("=" * 60)
print("2. 需求识别 (Need Recognition)")
print("=" * 60)

recognizer = NeedRecognizer(rs)
need_result = recognizer.prioritize(ms)

print("adjusted_scores (top 5):")
for need, score in need_result["adjusted_scores"].items():
    if score > 0.05:
        bar = "#" * int(score * 20)
        raw = need_result["raw_scores"].get(need, 0)
        print(f"  {need:25s} raw={raw:.2f} → adj={score:.2f} {bar}")
print(f"dominant: {need_result['dominant_need']}")
print(f"top_needs: {[(n, round(s, 2)) for n, s in need_result['top_needs']]}")

if need_result["applied_rules"]:
    print("applied_rules:")
    for r in need_result["applied_rules"]:
        print(f"  {r}")
print()

# ---- 4. 目标确定 (规则) ----
print("=" * 60)
print("3. 目标确定 (Goal Planning)")
print("=" * 60)

planner = GoalPlanner(rs)
goal_result = planner.plan(ms, need_result["top_needs"])

print(f"goal: {goal_result['goal']} ({goal_result['goal_zh']})")
print(f"reasoning: {goal_result['reasoning']}")
print(f"alternatives: {goal_result['alternatives']}")
print()

# ---- 5. Conversation 引擎 (NEW: v2 MVP) ----
print("=" * 60)
print("4. Conversation 引擎 (Conversation Engine)")
print("=" * 60)

timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
conv_mgr = ConversationManager()
conv, conv_switched = conv_mgr.process_message(HER_MESSAGE, timestamp, goal_result["goal"])

if conv_switched:
    print(f"[Conversation] 新对话: topic={conv.topic}, id={conv.id}")
else:
    print(f"[Conversation] 继续: topic={conv.topic}, goal={conv.current_goal}, msgs={len(conv.message_ids)}")

# 构建三层上下文
# 加载原始 relationship_state（含 recurring_topics 等新字段）
import json
rs_file = ROOT / "relationship_state.json"
if rs_file.exists():
    rs_raw = json.loads(rs_file.read_text(encoding="utf-8")).get("relationship_state", rs)
else:
    rs_raw = {}

cb = ContextBuilder(rs_raw, conv, [{"role": "她", "content": HER_MESSAGE}])
formatted_context = cb.format_for_llm()
print(f"[Context] 已构建三层上下文")
print()

# ---- 6. 策略选择 (规则) ----
print("=" * 60)
print("5. 策略选择 (Strategy Selection)")
print("=" * 60)

selector = StrategySelector(relationship_state=rs)
strategy_result = selector.select(ms, goal_result, need_result)

if strategy_result["primary"]:
    card = strategy_result["primary"]
    print(f"primary: {card.name} ({card.id})")
    print(f"  goal: {card.goal}")
    print(f"  risk: {card.risk_level}  target_need: {card.target_need}")

if strategy_result["filtered_out"]:
    print(f"filtered: {len(strategy_result['filtered_out'])} cards")
    for sid, reason in strategy_result["filtered_out"]:
        print(f"  x {sid}: {reason}")

print()
print("candidates:")
for i, (card, score, reasons) in enumerate(strategy_result["candidates"]):
    bar = "#" * int(score * 20)
    print(f"  {i+1}. {card.name:20s} ({card.id:30s}) score={score:.2f} {bar}")
    for r in reasons:
        print(f"     {r}")

print()

# ---- 7. 回复生成 (LLM) ----
print("=" * 60)
print("6. 回复生成 (Reply Generation)")
print("=" * 60)

if strategy_result["primary"]:
    generator = ReplyGenerator(relationship_state=rs)
    reply_result = generator.generate(
        llm_chat,
        ms,
        strategy_result["primary"],
        goal_result,
        chat_history=[{"role": "她", "content": HER_MESSAGE}],
        conversation_context=formatted_context,
    )
    print(reply_result["reply"])
    print()
    print(f"(strategy: {reply_result['strategy_used']}, goal: {reply_result['goal']})")

    # ---- 8. 表达增强 (LLM) ----
    print()
    print("=" * 60)
    print("7. 表达增强 (Expression Enhancement)")
    print("=" * 60)

    enhancer = ExpressionEnhancer(relationship_state=rs)
    enhanced = enhancer.enhance(
        llm_chat,
        reply_result["reply"],
        ms,
        strategy_result["primary"],
    )
    print(enhanced["enhanced_reply"])
else:
    print("[警告] 无可用策略卡，无法生成回复")

print()
print("=" * 60)
print("流水线完成")
