import logging

logger = logging.getLogger(__name__)


def normalize_channel_name(name: str) -> str:
    normalized = name.strip().lower()
    logger.info("normalize_channel_name called original=%r normalized=%r", name, normalized)
    return normalized
