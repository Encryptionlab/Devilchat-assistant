"""Test batch MessageUnderstanding with mock WCF data (v2 sequence format)."""
import json
import sys
import io
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from backend.services.llm_service import LlmService
from backend.config import load_api_key
from src.message_understanding import MessageUnderstanding

DATA_FILE = Path(__file__).parent / "data" / "mock_wcf_story_3000.jsonl"

# Shared LLM callable (sync)
llm_call = LlmService(api_key=load_api_key()).as_callable()
mu = MessageUnderstanding()


def analyze(msgs: list[dict], label: str = ""):
    """Run batch analysis and print results."""
    prompt = mu.build_user_prompt_for_sequence(msgs)
    start = time.time()
    result = llm_call(mu.system_prompt, prompt)
    elapsed = time.time() - start

    ms = mu.parse_to_state(result)
    print(f"  [{label}] Latency: {elapsed:.1f}s")
    print(f"  Emotion: {ms.emotion} (intensity: {ms.emotion_intensity})")
    print(f"  Topic: {ms.topic}")
    print(f"  Dominant need: {ms.dominant_need}")
    print(f"  Dominant intent: {ms.dominant_intent}")
    print(f"  Burst pattern: {ms.burst_pattern}")
    print(f"  Emotional peak: {ms.emotional_peak}")
    print(f"  Trajectory note: {ms.trajectory_note}")
    top = ms.needs_above(0.3)
    if top:
        print(f"  Top needs: {', '.join(top)}")
    print()
    return ms


def load_messages(n: int = 200) -> list[dict]:
    """Load first N messages from mock data and convert to pipeline format."""
    messages = []
    with open(DATA_FILE, encoding='utf-8') as f:
        for i, line in enumerate(f):
            if i >= n:
                break
            raw = json.loads(line)
            role = "她" if raw["sender"] == "wxid_gf001" else "我"
            messages.append({
                "role": role,
                "content": raw["content"],
                "timestamp": raw.get("ts", ""),
            })
    return messages


def simulate_wcf_batches(messages: list[dict]) -> list[list[dict]]:
    """Split into simulated WCF batches (3-8 messages per batch, burst-like)."""
    batches = []
    i = 0
    while i < len(messages):
        batch = []
        her_count = 0
        while i < len(messages) and len(batch) < 8:
            msg = messages[i]
            batch.append(msg)
            if msg["role"] == "她":
                her_count += 1
            i += 1
            # Natural break after "me" message ends a burst
            if msg["role"] == "我" and her_count >= 2:
                break
        if batch:
            batches.append(batch)
    return batches


def main():
    print("=" * 60)
    print("Batch MessageUnderstanding v2 Test Suite")
    print("=" * 60)

    # Test 1: Format verification (no LLM)
    print("\n--- Test 1: Prompt Format ---")
    test_msgs = [
        {"role": "她", "content": "今天好累啊"},
        {"role": "我", "content": "怎么了宝宝"},
        {"role": "她", "content": "复习了一整天"},
        {"role": "她", "content": "头都晕了"},
    ]
    print(mu.build_user_prompt_for_sequence(test_msgs))

    # Test 2: Single message
    print("\n--- Test 2: Single Message ---")
    analyze([{"role": "她", "content": "你在干嘛呢"}], "single")

    # Test 3: Burst of 3 her messages
    print("--- Test 3: Burst (3 her) ---")
    analyze([
        {"role": "她", "content": "今天好累啊"},
        {"role": "她", "content": "复习了一整天"},
        {"role": "她", "content": "头都晕了"},
    ], "burst3")

    # Test 4: Mixed (her + me interleaved)
    print("--- Test 4: Mixed (her + me) ---")
    analyze([
        {"role": "她", "content": "今天好累啊"},
        {"role": "我", "content": "怎么了宝宝"},
        {"role": "她", "content": "复习了一整天"},
        {"role": "她", "content": "头都晕了"},
        {"role": "我", "content": "这么辛苦"},
    ], "mixed")

    # Test 5: Mock data — pick 3 batches with 2+ her messages each
    print("--- Test 5: Mock Data Samples ---")
    all_msgs = load_messages(150)
    batches = simulate_wcf_batches(all_msgs)

    tested = 0
    for i, batch in enumerate(batches):
        her_count = sum(1 for m in batch if m["role"] == "她")
        if her_count < 2:
            continue
        print(f"\n  Batch {tested + 1} ({len(batch)} msgs, {her_count} her):")
        for m in batch:
            tag = "[她]" if m["role"] == "她" else "[我]"
            print(f"    {tag} {m['content']}")
        analyze(batch, f"mock-{tested + 1}")
        tested += 1
        if tested >= 3:
            break

    print("=" * 60)
    print("All tests completed.")


if __name__ == "__main__":
    main()
