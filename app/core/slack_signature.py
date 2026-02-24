import hashlib
import hmac
import logging
import time

logger = logging.getLogger(__name__)


def verify_slack_signature(
    *,
    signing_secret: str,
    timestamp: str | None,
    signature: str | None,
    body: bytes,
    tolerance_seconds: int = 300,
    current_timestamp: int | None = None,
) -> bool:
    if not signing_secret:
        logger.warning("slack_signature_verification_failed reason=missing_signing_secret")
        return False

    if not timestamp or not signature:
        logger.info("slack_signature_verification_failed reason=missing_headers")
        return False

    try:
        request_ts = int(timestamp)
    except ValueError:
        logger.info("slack_signature_verification_failed reason=invalid_timestamp")
        return False

    now = current_timestamp if current_timestamp is not None else int(time.time())
    if abs(now - request_ts) > tolerance_seconds:
        logger.info(
            "slack_signature_verification_failed reason=stale_request request_ts=%s now=%s tolerance_seconds=%s",
            request_ts,
            now,
            tolerance_seconds,
        )
        return False

    basestring = f"v0:{timestamp}:{body.decode('utf-8')}".encode("utf-8")
    expected = "v0=" + hmac.new(signing_secret.encode("utf-8"), basestring, hashlib.sha256).hexdigest()
    verified = hmac.compare_digest(expected, signature)
    logger.info("slack_signature_verified verified=%s", verified)
    return verified
