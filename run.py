"""
魔鬼聊天 —— 交互式长期记忆对话系统

用法：
    python run.py          # 交互模式
    python run.py "今天好烦"  # 单条模式（兼容旧用法）
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timezone

import requests

from message_understanding import MessageUnderstanding, load_relationship_state
from need_recognition import NeedRecognizer
from goal_planner import GoalPlanner
from strategy_selector import StrategySelector
from reply_generator import ReplyGenerator
from expression_enhancer import ExpressionEnhancer
from conversation import ConversationManager
from context_builder import ContextBuilder
from memory_updater import MemoryUpdater
from summarizer import summarize

# ---- 配置 ----
ROOT = Path(__file__).parent
BASE_URL = "https://opencode.ai/zen/go/v1/chat/completions"
MODEL = "deepseek-v4-flash"
RS_PATH = ROOT / "relationship_state.json"

key_file = ROOT / "ds.txt"
if key_file.exists():
    API_KEY = key_file.read_text(encoding="utf-8").strip().split("=")[-1].strip()
else:
    print("[错误] 找不到 ds.txt，请创建并写入 api = your-key")
    sys.exit(1)


def llm_chat(system_prompt: str, user_prompt: str) -> str:
    resp = requests.post(
        BASE_URL,
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json={"model": MODEL, "max_tokens": 4096,
              "messages": [{"role": "system", "content": system_prompt},
                           {"role": "user", "content": user_prompt}]},
    )
    if resp.status_code != 200:
        raise RuntimeError(f"API 返回 {resp.status_code}: {resp.text}")
    return resp.json()["choices"][0]["message"]["content"]


# ---- 单条模式（兼容旧用法）----

def run_once(her_message: str):
    rs = load_relationship_state()
    _print_rs(rs)

    mu = MessageUnderstanding()
    ms = mu.parse_to_state(llm_chat(mu.system_prompt, mu.build_user_prompt([{"role": "她", "content": her_message}])))

    recognizer = NeedRecognizer(rs)
    need_result = recognizer.prioritize(ms)

    planner = GoalPlanner(rs)
    goal_result = planner.plan(ms, need_result["top_needs"])

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    conv_mgr = ConversationManager()
    conv, switched = conv_mgr.process_message(her_message, timestamp, goal_result["goal"])

    selector = StrategySelector(relationship_state=rs)
    strategy_result = selector.select(ms, goal_result, need_result)

    if not strategy_result["primary"]:
        print("[警告] 无可用策略卡")
        return

    generator = ReplyGenerator(relationship_state=rs)
    reply_result = generator.generate(
        llm_chat, ms, strategy_result["primary"], goal_result,
        chat_history=[{"role": "她", "content": her_message}],
    )

    enhancer = ExpressionEnhancer(relationship_state=rs)
    enhanced = enhancer.enhance(llm_chat, reply_result["reply"], ms, strategy_result["primary"])

    print(reply_result["reply"])
    print(f"\n(增强) {enhanced['enhanced_reply']}")


def _print_rs(rs: dict):
    print(f"[关系] stage={rs['stage']} trust={rs['trust_level']} intimacy={rs['intimacy_level']}")


# ---- 交互模式 ----

def run_interactive():
    # 首次启动 → 引导初始化
    if not RS_PATH.exists():
        from bootstrap import bootstrap
        bootstrap(llm_chat)

    rs = load_relationship_state()
    conv_mgr = ConversationManager()
    conv_messages: list[dict] = []       # 当前 Conversation 的消息

    print("\n魔鬼聊天已启动。输入 /quit 退出，/status 查看状态。")
    _print_rs(rs)

    while True:
        try:
            her_msg = input("\n她: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见。")
            break

        if her_msg == "/quit":
            break
        if her_msg == "/status":
            rs = load_relationship_state()  # 重新加载（MemoryUpdater 可能已更新）
            _print_rs(rs)
            print(f"  当前对话: topic={conv.topic if (conv := conv_mgr.get_active_conversation()) else '无'}")
            continue
        if her_msg == "/history":
            for c in conv_mgr.get_recent_conversations(5):
                print(f"  [{c.topic}] {c.start_time} outcome={c.outcome} {c.summary or '(无摘要)'}")
            continue
        if not her_msg:
            continue

        # 重新加载关系状态（获取最新值）
        rs = load_relationship_state()

        # ---- 消息理解 (LLM) ----
        mu = MessageUnderstanding()
        ms = mu.parse_to_state(llm_chat(mu.system_prompt, mu.build_user_prompt([{"role": "她", "content": her_msg}])))

        # ---- 需求识别 (规则) ----
        need_result = NeedRecognizer(rs).prioritize(ms)

        # ---- 目标确定 (规则) ----
        goal_result = GoalPlanner(rs).plan(ms, need_result["top_needs"])

        # ---- Conversation 引擎 ----
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        prev_conv = conv_mgr.get_active_conversation()
        conv, switched = conv_mgr.process_message(her_msg, timestamp, goal_result["goal"])

        # ---- Conversation 关闭钩子 ----
        if switched and prev_conv is not None:
            _on_conversation_closed(prev_conv, conv_messages, conv_mgr, llm_chat)
            conv_messages = []

        conv_messages.append({"role": "她", "content": her_msg})

        if switched:
            print(f"[新对话] topic={conv.topic}")

        # ---- 上下文构建 ----
        rs_raw = json.loads(RS_PATH.read_text(encoding="utf-8")).get("relationship_state", rs)
        cb = ContextBuilder(rs_raw, conv, conv_messages)
        ctx = cb.format_for_llm()

        # ---- 策略选择 (规则) ----
        strategy_result = StrategySelector(relationship_state=rs).select(ms, goal_result, need_result)

        if not strategy_result["primary"]:
            print("[警告] 无可用策略卡")
            continue

        # ---- 回复生成 (LLM) ----
        reply_result = ReplyGenerator(relationship_state=rs).generate(
            llm_chat, ms, strategy_result["primary"], goal_result,
            chat_history=list(conv_messages),
            conversation_context=ctx,
        )

        # ---- 表达增强 (LLM) ----
        enhanced = ExpressionEnhancer(relationship_state=rs).enhance(
            llm_chat, reply_result["reply"], ms, strategy_result["primary"],
        )

        card = strategy_result["primary"]
        print(f"\n回复: {enhanced['enhanced_reply']}")
        print(f"  [{card.name} | {goal_result['goal']}]")


def _on_conversation_closed(closed_conv, messages: list[dict], conv_mgr, llm_chat):
    """Conversation 关闭时：生成摘要 → 更新长期记忆。"""
    if not messages:
        return

    # 1. LLM 生成摘要
    result = summarize(llm_chat, messages, closed_conv.topic)
    closed_conv.summary = result["summary"]
    closed_conv.outcome = result["outcome"]
    closed_conv.key_points = result["key_points"]

    # 2. MemoryUpdater 更新
    updater = MemoryUpdater()
    updater.update(closed_conv)

    # 3. recurring_topics 检测
    for topic in ["work", "exam", "family", "relationship", "dating", "conflict"]:
        count = conv_mgr.count_topic_in_recent(topic, n=10)
        if count >= 3:
            updater.apply_recurring_topics({topic: count})

    updater.save()
    conv_mgr._save()

    print(f"[记忆] 对话已关闭: topic={closed_conv.topic}, outcome={closed_conv.outcome}")


# ---- 入口 ----

if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_once(sys.argv[1])
    else:
        run_interactive()
