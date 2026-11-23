"""Shared database cache and locks; never trust forwarded IP headers."""
from core.db_locks import transaction_lock, session_lock
from contextlib import contextmanager
import hashlib
import time

from django.conf import settings
from django.core.cache import caches
from django.db import transaction
from django.utils.crypto import salted_hmac

from .chatbot_contract import ChatUnavailable

TTL = 7200


def cache():
    return caches["chatbot"]


def lock_number(value):
    return int.from_bytes(hashlib.sha256(("qlnh-chat:" + value).encode()).digest()[:8], "big", signed=True)


@contextmanager
def conversation_lock(identity):
    key = lock_number("conversation:" + identity)
    with session_lock(key) as acquired:
        if not acquired:
            raise ChatUnavailable("busy", "Trợ lý đang xử lý tin nhắn trước. Vui lòng chờ trả lời rồi gửi tiếp.", 409)
        yield


def enforce_rate(identity, remote_address, *, api=False):
    ip_hash = salted_hmac("qlnh.chat.ip", remote_address or "unknown").hexdigest()
    now = int(time.time())
    budgets = [(f"session:{identity}:{now // 60}", settings.CHATBOT_SESSION_RPM if api else 60, 120),
               (f"source:{ip_hash}:{now // 60}", settings.CHATBOT_IP_RPM if api else 120, 120)]
    if api:
        budgets += [(f"global-minute:{now // 60}", settings.CHATBOT_GLOBAL_RPM, 120),
                    (f"global-day:{now // 86400}", settings.CHATBOT_GLOBAL_RPD, 172800)]
    # DatabaseCache.incr() is not atomic. Serialize counters across all workers
    # with a short database transaction; never hold this transaction during HTTP.
    with transaction.atomic():
        transaction_lock(lock_number("rate-budgets"))
        values = [("chat-rate:" + ("api:" if api else "ui:") + key, limit, ttl) for key, limit, ttl in budgets]
        current = [(key, int(cache().get(key, 0)), limit, ttl) for key, limit, ttl in values]
        if any(count >= limit for _, count, limit, _ in current):
            raise ChatUnavailable("rate_limit", "Bạn đã đạt giới hạn trò chuyện tạm thời. Vui lòng thử lại sau.", 429)
        for key, count, _, ttl in current:
            cache().set(key, count + 1, timeout=ttl)
            if cache().get(key) != count + 1:
                raise ChatUnavailable("storage", "Trợ lý tạm chưa sẵn sàng. Vui lòng thử lại sau.")


def load_conversation(identity):
    value = cache().get("chat-history:" + identity, {"history": [], "attempts": 0})
    if not isinstance(value, dict) or set(value) != {"history", "attempts"}:
        return {"history": [], "attempts": 0}
    history = value["history"]
    if (not isinstance(history, list) or len(history) > settings.CHATBOT_MAX_TURNS * 2
            or type(value["attempts"]) is not int or value["attempts"] < 0):
        return {"history": [], "attempts": 0}
    if any(not isinstance(item, dict) or set(item) != {"role", "text"}
           or item["role"] != ("user" if i % 2 == 0 else "assistant")
           or not isinstance(item["text"], str) or len(item["text"]) > 3000
           for i, item in enumerate(history)) or len(history) % 2:
        return {"history": [], "attempts": 0}
    return value


def save_conversation(identity, value):
    cache().set("chat-history:" + identity, value, timeout=TTL)
    if cache().get("chat-history:" + identity) != value:
        raise ChatUnavailable("storage", "Không lưu được cuộc trò chuyện. Vui lòng thử lại sau.")
