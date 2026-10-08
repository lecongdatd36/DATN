import logging
from time import perf_counter

from django.conf import settings


performance_logger = logging.getLogger("qlnh.performance")


class RequestTimingMiddleware:
    """Expose server duration and log requests that exceed the operating SLA."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        started_at = perf_counter()
        response = self.get_response(request)
        duration_ms = (perf_counter() - started_at) * 1000
        response["Server-Timing"] = f"app;dur={duration_ms:.1f}"

        threshold_ms = settings.SLOW_REQUEST_THRESHOLD_MS
        if duration_ms >= threshold_ms:
            performance_logger.warning(
                "slow_request method=%s path=%s status=%s duration_ms=%.1f threshold_ms=%s",
                request.method,
                request.path,
                response.status_code,
                duration_ms,
                threshold_ms,
            )
        return response
