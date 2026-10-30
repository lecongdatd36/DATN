"""Groq hosted API, one bounded HTTPS request; no local model or paid fallback."""
import json
import logging

import httpx
from django.conf import settings

from .chatbot_contract import SYSTEM_INSTRUCTION, RESPONSE_SCHEMA, ChatUnavailable, validate_reply

logger = logging.getLogger(__name__)
ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
# Listed under Groq Free Plan Limits and supports strict JSON Schema.
FREE_PLAN_MODELS = frozenset({"qwen/qwen3.8-27b", "openai/gpt-oss-20b"})


def configured():
    return bool(settings.GROQ_API_KEY and settings.GROQ_MODEL in FREE_PLAN_MODELS)


def generate_reply(context, history, message):
    if not configured():
        raise ChatUnavailable("not_configured", "Trợ lý đang chờ cấu hình Groq API. Bạn vẫn có thể xem thực đơn hoặc đặt bàn.")
    payload = {"public_data": context, "conversation": history, "question": message}
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(serialized) > min(settings.CHATBOT_CONTEXT_CHARS, 14000):
        raise ChatUnavailable("context_limit", "Nội dung trao đổi đã dài. Vui lòng bắt đầu cuộc trò chuyện mới.", 400)
    body = {
        "model": settings.GROQ_MODEL,
        "messages": [{"role": "system", "content": SYSTEM_INSTRUCTION}, {"role": "user", "content": serialized}],
        "max_completion_tokens": settings.CHATBOT_MAX_OUTPUT_TOKENS,
        "stream": False,
        "response_format": {"type": "json_schema", "json_schema": {
            "name": "restaurant_reply", "strict": True, "schema": RESPONSE_SCHEMA,
        }},
    }
    if settings.GROQ_MODEL == "qwen/qwen3.8-27b":
        body["reasoning_effort"] = "none"
    try:
        # Fixed endpoint, no redirects, no transport retries; key is only a header.
        with httpx.Client(timeout=settings.CHATBOT_TIMEOUT_SECONDS, follow_redirects=False,
                          transport=httpx.HTTPTransport(retries=0)) as client:
            response = client.post(ENDPOINT, headers={"Authorization": "Bearer " + settings.GROQ_API_KEY}, json=body)
        status = response.status_code
        if status != 200:
            logger.warning("Groq request failed; status=%s", status)
            if status == 429:
                raise ChatUnavailable("quota", "Groq đã đạt hạn mức miễn phí hoặc đang nhận nhiều yêu cầu. Vui lòng thử lại sau.", 429, "quota_exhausted")
            if status in (401, 403):
                raise ChatUnavailable("provider_config", "Groq đang từ chối quyền kết nối. Nhà hàng cần kiểm tra cấu hình API.", diagnostic="authentication_or_permission_rejected")
            if status in (400, 402, 404):
                raise ChatUnavailable("provider_config", "Groq chưa chấp nhận cấu hình hiện tại. Bạn vẫn có thể xem thực đơn và đặt bàn.", diagnostic="provider_configuration_rejected")
            raise ChatUnavailable("provider_unavailable", "Trợ lý AI tạm chưa trả lời được. Vui lòng thử lại sau.")
        if len(response.content) > 100000:
            raise ValueError("response_size")
        data = response.json()
        choice = data["choices"][0]
        if choice.get("finish_reason") != "stop":
            raise ValueError("incomplete_response")
        return validate_reply(choice["message"]["content"], settings.GROQ_API_KEY)
    except ChatUnavailable:
        raise
    except Exception:
        # Never log headers, response bodies, prompts, keys or raw exception text.
        logger.warning("Groq request unavailable; details suppressed")
        raise ChatUnavailable("provider_unavailable", "Trợ lý AI tạm chưa trả lời được. Vui lòng thử lại sau.") from None
