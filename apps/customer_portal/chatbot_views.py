import json
import logging
import uuid

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST

from .chatbot_data import navigation_links, normalized, policy_reply, public_context
from .chatbot_service import ChatUnavailable, configured, generate_reply, context_limit, provider_name
from .chatbot_storage import conversation_lock, enforce_rate, load_conversation, save_conversation

logger = logging.getLogger(__name__)


@never_cache
@require_POST
@csrf_protect
def customer_chat(request):
    links = navigation_links()
    try:
        if request.content_type != "application/json" or len(request.body) > 6000:
            raise ValueError
        payload = json.loads(request.body)
        if not isinstance(payload, dict):
            raise ValueError
        action = payload.get("action", "message")
        if action not in ("message", "state", "reset"):
            raise ValueError
        allowed = {"action", "message"} if action == "message" else {"action"}
        if set(payload) - allowed:
            raise ValueError  # Client history, roles and system instructions are rejected.
        message = payload.get("message", "")
        if action == "message" and (not isinstance(message, str) or not message.strip()
                                     or len(message) > 1000 or "\x00" in message):
            raise ValueError
    except (ValueError, TypeError, UnicodeDecodeError):
        return JsonResponse({"error": "Vui lòng gửi câu hỏi bằng văn bản, tối đa 1.000 ký tự.", "code": "invalid_input"}, status=400)
    try:
        identity = request.session.get("customer_chat_id")
        if not isinstance(identity, str) or len(identity) != 32:
            identity = uuid.uuid4().hex
            request.session["customer_chat_id"] = identity
        with conversation_lock(identity):
            enforce_rate(identity, request.META.get("REMOTE_ADDR", ""))
            conversation = load_conversation(identity)
            if action == "reset":
                conversation = {"history": [], "attempts": 0}
                save_conversation(identity, conversation)
            if action in ("state", "reset"):
                return JsonResponse({**conversation, "available": configured(), "links": links,
                                     "max_turns": settings.CHATBOT_MAX_TURNS, "provider": provider_name()})
            if conversation["attempts"] >= settings.CHATBOT_MAX_TURNS:
                raise ChatUnavailable("turn_limit", "Cuộc trò chuyện đã đạt giới hạn. Hãy bấm Trò chuyện mới để tiếp tục.", 429)
            local_reply = policy_reply(message)
            if not configured() and local_reply is None:
                raise ChatUnavailable("not_configured", "Trợ lý đang chờ cấu hình API. Bạn vẫn có thể xem thực đơn hoặc đặt bàn.")
            if local_reply is None:
                enforce_rate(identity, request.META.get("REMOTE_ADDR", ""), api=True)
            conversation["attempts"] += 1
            save_conversation(identity, conversation)  # Failed attempts also consume a turn.
            history = conversation["history"]
            if local_reply is not None:
                history += [{"role": "user", "text": message.strip()}, {"role": "assistant", "text": local_reply}]
                save_conversation(identity, conversation)
                return JsonResponse({"answer": local_reply, "dishes": [], "apriori": [], "links": links,
                                     "attempts": conversation["attempts"], "max_turns": settings.CHATBOT_MAX_TURNS})
            context, available = public_context(message, history)
            # Fit a bounded context, preserving complete conversation pairs.
            api_history = history[-12:]
            budget = context_limit()
            while api_history and len(json.dumps({"public_data": context, "conversation": api_history, "question": message}, ensure_ascii=False)) > budget:
                api_history = api_history[2:]
            while context["menu"] and len(json.dumps({"public_data": context, "conversation": api_history, "question": message}, ensure_ascii=False)) > budget:
                context["menu"].pop()
                context["menu_truncated"] = True
            answer = generate_reply(context, api_history, message.strip())
            # Re-query the public menu after the network call so changed price/status
            # cannot become an orderable recommendation from an obsolete snapshot.
            current_context, current_available = public_context("", [])
            current_menu = {item["id"]: item for item in current_context["menu"]}
            if any(current_menu.get(item["id"]) != item for item in context["menu"]):
                answer["answer"] = "Thực đơn vừa thay đổi trong lúc tư vấn. Mời bạn xem giá và trạng thái mới trên thực đơn; các thẻ món bên dưới đã được kiểm tra lại."
            sold_mentions = [item["name"] for item in current_context["menu"]
                             if item["status"] == "SOLD_OUT" and normalized(item["name"]) in normalized(answer["answer"])]
            if sold_mentions:
                answer["answer"] = ", ".join(sold_mentions) + " hiện tạm hết, nên chưa thể gọi. Bạn có thể chọn món đang bán trên thực đơn hoặc các thẻ món bên dưới."
            supplied_ids = {item["id"] for item in context["menu"]}
            dishes = [current_available[pk] for pk in answer["dish_ids"]
                      if pk in current_available and pk in supplied_ids]
            apriori = [current_available[item["id"]] for item in context["apriori"]
                       if item["id"] in current_available]
            history += [{"role": "user", "text": message.strip()}, {"role": "assistant", "text": answer["answer"]}]
            save_conversation(identity, conversation)
            return JsonResponse({"answer": answer["answer"], "dishes": dishes, "apriori": apriori,
                                 "links": links, "attempts": conversation["attempts"], "max_turns": settings.CHATBOT_MAX_TURNS})
    except ChatUnavailable as error:
        response = JsonResponse({"error": error.message, "code": error.code, "links": links}, status=error.status)
        if error.status == 429:
            response["Retry-After"] = "60"
        return response
    except Exception:
        logger.warning("Customer chat unavailable; internal failure (details suppressed)")
        return JsonResponse({"error": "Trợ lý tạm chưa sẵn sàng. Vui lòng xem thực đơn hoặc mở form đặt bàn.",
                             "code": "unavailable", "links": links}, status=503)
