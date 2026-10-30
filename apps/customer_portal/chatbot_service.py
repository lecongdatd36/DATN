"""Select exactly one configured remote provider; never fall back automatically."""
from django.conf import settings

from . import chatbot_gemini, chatbot_groq
from .chatbot_contract import ChatUnavailable


def provider_name():
    return {"groq": "Groq", "gemini": "Gemini"}.get(settings.CHATBOT_PROVIDER, "AI")


def backend():
    providers = {"groq": chatbot_groq, "gemini": chatbot_gemini}
    provider = providers.get(settings.CHATBOT_PROVIDER)
    if provider is None:
        raise ChatUnavailable("not_configured", "Nhà cung cấp AI chưa được cấu hình.")
    return provider


def configured():
    try:
        return backend().configured()
    except ChatUnavailable:
        return False


def context_limit():
    # Keep the Groq request below a conservative input budget for its Free Plan.
    return min(settings.CHATBOT_CONTEXT_CHARS, 14000) if settings.CHATBOT_PROVIDER == "groq" else settings.CHATBOT_CONTEXT_CHARS


def generate_reply(context, history, message):
    return backend().generate_reply(context, history, message)
