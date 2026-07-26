"""POST /api/observe + GET /api/dashboard"""

from fastapi import APIRouter, Depends
from backend.dependencies import get_llm_service, get_state_service
from backend.schemas.chat import ChatRequest, ChatResponse
from backend.services.pipeline_service import PipelineService
from backend.services.message_buffer import MessageBuffer
from backend.services.urgency_scorer import UrgencyScorer

router = APIRouter(prefix="/api", tags=["observe"])

# Global singletons (per process)
_buffer: MessageBuffer | None = None
_scorer: UrgencyScorer | None = None


def _get_buffer() -> MessageBuffer:
    global _buffer
    if _buffer is None:
        _buffer = MessageBuffer()
    return _buffer


def _get_scorer() -> UrgencyScorer:
    global _scorer
    if _scorer is None:
        _scorer = UrgencyScorer()
    return _scorer


def _get_pipeline() -> PipelineService:
    from backend.dependencies import get_llm_service, get_state_service
    return PipelineService(get_llm_service(), get_state_service())


@router.post("/observe")
async def observe_message(req: ChatRequest):
    """观测端点：接收 WCF 消息流，持续记录但不生成策略。

    WCF 每捕获一条消息就 POST 一次。
    返回：当前会话状态 + 情绪 + 是否触发关闭。
    """
    pipeline = _get_pipeline()
    buf = _get_buffer()

    # Push to buffer
    buf.push(role="她", content=req.message)

    # Run observation pipeline
    messages = [{"role": "她", "content": req.message}]
    result = await pipeline.observe_messages(messages, trigger_evaluator=True)

    return {
        "buffer_stats": buf.get_stats(),
        **result,
    }


@router.get("/dashboard")
async def get_dashboard():
    """仪表盘数据：待处理消息 + 紧急度 + 活跃会话摘要。"""
    buf = _get_buffer()
    pipeline = _get_pipeline()
    scorer = _get_scorer()

    pending = buf.get_pending()
    stats = buf.get_stats()

    # Run observation on any new pending messages
    observe_result = None
    if pending:
        msgs = [m.to_dict() for m in pending]
        observe_result = await pipeline.observe_messages(msgs, trigger_evaluator=True)

    # Urgency assessment
    emotion = observe_result.get("emotion", "neutral") if observe_result else "neutral"
    rs = await pipeline.state.load_relationship_state()

    urgency = scorer.assess(
        pending_count=len(pending),
        time_since_last_her=stats["time_since_her"],
        time_since_last_me=stats["time_since_me"],
        emotion=emotion,
        conflict_level=rs.get("conflict_level", 0),
        has_unresolved_topics=bool(rs.get("unresolved_topics")),
        is_night_time=scorer.is_night_time(),
    )

    # Active conversation
    conv_mgr = await pipeline._get_conversation_manager()
    active = conv_mgr.get_active_conversation()

    # Strategy effectiveness
    effectiveness = rs.get("strategy_effectiveness", {})

    return {
        "urgency": urgency,
        "pending_messages": [m.to_dict() for m in pending],
        "stats": stats,
        "emotion": emotion,
        "topic": observe_result.get("topic", "") if observe_result else "",
        "active_conversation": active.to_dict() if active else None,
        "strategy_effectiveness": effectiveness,
        "had_closed": observe_result.get("had_closed", False) if observe_result else False,
        "closed_conv": observe_result.get("closed_conv") if observe_result else None,
        "evaluation": observe_result.get("evaluation") if observe_result else None,
    }


@router.post("/dashboard/mark-processed")
async def mark_processed():
    """标记所有待处理消息为已处理。用户查看仪表盘后调用。"""
    buf = _get_buffer()
    processed = buf.mark_processed()
    return {"processed_count": len(processed)}


@router.post("/dashboard/push-my-message")
async def push_my_message(req: ChatRequest):
    """推送「我」发送的消息（WCF 捕获到我的回复时调用）。"""
    buf = _get_buffer()
    msg = buf.push(role="我", content=req.message)
    return {"id": msg.id, "timestamp": msg.timestamp}
