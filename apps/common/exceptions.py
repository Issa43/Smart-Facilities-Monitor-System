import logging

from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger("django")


def custom_exception_handler(exc, context):
    """
    Wraps DRF's default exception handler to produce a consistent
    error envelope across the whole API:

        {
            "success": false,
            "error": {
                "code": <http_status>,
                "message": <human readable>,
                "details": <original DRF error payload>
            }
        }
    """
    response = drf_exception_handler(exc, context)

    if response is None:
        # Unhandled exception - do not leak internals to the client.
        logger.exception("Unhandled exception in %s", context.get("view"))
        return None

    error_message = "Request failed."
    if isinstance(response.data, dict) and "detail" in response.data:
        error_message = str(response.data["detail"])

    response.data = {
        "success": False,
        "error": {
            "code": response.status_code,
            "message": error_message,
            "details": response.data,
        },
    }
    return response
