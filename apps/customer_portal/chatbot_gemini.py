"""One bounded Gemini Developer API request. No tools, code execution or retries."""
import json
import logging

from django.conf import settings

logger = logging.getLogger(__name__)
FREE_TIER_MODELS = frozenset({"gemini-2.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.8-flash"})

from .chatbot_contract import SYSTEM_INSTRUCTION, RESPONSE_SCHEMA, ChatUnavailable, validate_reply


def provider_failure_reason(error):
    """Return an allowlisted category only; never expose raw provider messages."""
    message = getattr(error, "message", "")
    message = message.lower() if isinstance(message, str) else ""
    if "leaked" in message:
        return "credential_reported_leaked"
    if "api key not valid" in message or "api key expired" in message:
        return "credential_invalid_or_expired"
    if "project" in message and "free tier" in message and any(
        phrase in message for phrase in ("not available", "unavailable", "not eligible")
    ):
        return "project_free_tier_unavailable"
    if "location" in message and ("not supported" in message or "unsupported" in message):
        return "location_unsupported"
    if "project" in message and ("denied access" in message or "free tier unavailable" in message):
        return "project_access_restricted"
    details = getattr(error, "details", {})
    if isinstance(details, dict):
        nested = details.get("error", details)
        records = nested.get("details", []) if isinstance(nested, dict) else []
        reasons = {
            "API_KEY_INVALID": "credential_invalid_or_expired",
            "API_KEY_EXPIRED": "credential_invalid_or_expired",
            "API_KEY_SERVICE_BLOCKED": "credential_service_restricted",
            "API_KEY_HTTP_REFERRER_BLOCKED": "credential_referrer_restricted",
            "API_KEY_IP_ADDRESS_BLOCKED": "credential_ip_restricted",
            "SERVICE_DISABLED": "api_service_disabled",
            "CONSUMER_INVALID": "project_invalid",
            "BILLING_DISABLED": "project_billing_restriction",
        }
        if isinstance(records, list):
            for record in records:
                if isinstance(record, dict) and isinstance(record.get("reason"), str):
                    reason = reasons.get(record["reason"])
                    if reason:
                        return reason
    code = getattr(error, "code", 0)
    code = code if type(code) is int else 0
    return {401: "authentication_rejected", 403: "permission_denied", 404: "model_unavailable",
            429: "quota_exhausted"}.get(code, "request_failed")


def configured():
    return bool(settings.GEMINI_API_KEY and settings.GEMINI_MODEL in FREE_TIER_MODELS)


def generate_reply(context, history, message):
    if not configured():
        raise ChatUnavailable("not_configured", "Trợ lý đang chờ cấu hình. Bạn có thể xem thực đơn hoặc mở form đặt bàn.")
    try:
        from google import genai
        from google.genai import types
        # Fresh public context precedes trusted server-stored conversational turns.
        payload = {"public_data": context, "conversation": history, "question": message}
        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if len(serialized) > settings.CHATBOT_CONTEXT_CHARS:
            raise ChatUnavailable("context_limit", "Nội dung trao đổi đã dài. Vui lòng bắt đầu cuộc trò chuyện mới.", 400)
        with genai.Client(api_key=settings.GEMINI_API_KEY, vertexai=False,
                          http_options=types.HttpOptions(
                              timeout=settings.CHATBOT_TIMEOUT_SECONDS * 1000,
                              retry_options=types.HttpRetryOptions(attempts=1))) as client:
            response = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=[types.Content(role="user", parts=[types.Part.from_text(text=serialized)])],
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION, temperature=0.2,
                    max_output_tokens=settings.CHATBOT_MAX_OUTPUT_TOKENS,
                    response_mime_type="application/json", response_json_schema=RESPONSE_SCHEMA,
                ),
            )
        raw = response.text
        return validate_reply(raw, settings.GEMINI_API_KEY)
    except ChatUnavailable:
        raise
    except Exception as error:
        # Do not log str(error), response bodies, prompts or exception tracebacks.
        code = getattr(error, "code", 0)
        code = code if type(code) is int else 0
        reason = provider_failure_reason(error)
        logger.warning("Gemini request failed; status=%s reason=%s", code, reason)
        if code == 429:
            raise ChatUnavailable("quota", "Gemini đã hết hạn mức hoặc đang nhận quá nhiều yêu cầu. Vui lòng thử lại sau; bạn vẫn có thể xem thực đơn và đặt bàn.", 429) from None
        if code in (400, 401, 403, 404):
            message = "Trợ lý chưa kết nối được với Gemini. Vui lòng dùng thực đơn hoặc form đặt bàn trong lúc chờ cấu hình."
            if code in (401, 403):
                message = "Gemini đang từ chối quyền truy cập của trợ lý. Nhà hàng cần kiểm tra cấu hình kết nối; bạn vẫn có thể xem thực đơn hoặc đặt bàn."
            if reason == "project_free_tier_unavailable":
                message = "Gemini Free Tier chưa khả dụng với cấu hình của nhà hàng. Trợ lý AI đang tạm ngưng; bạn vẫn có thể xem thực đơn hoặc mở form đặt bàn."
            raise ChatUnavailable("provider_config", message, diagnostic=reason) from None
        raise ChatUnavailable("provider_unavailable", "Trợ lý tạm chưa trả lời được. Vui lòng thử lại sau hoặc dùng thực đơn và form đặt bàn.") from None
