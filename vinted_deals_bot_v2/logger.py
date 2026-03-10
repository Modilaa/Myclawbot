"""
Logging structuré — JSON pour production, lisible pour dev.
"""

import logging
import json
import sys
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """Formatte les logs en JSON pour ingestion par des outils de monitoring."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.module,
            "msg": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0]:
            entry["exception"] = self.formatException(record.exc_info)
        # Champs extra ajoutés via logger.info("msg", extra={...})
        for key in ("keyword", "item_id", "price", "margin", "deals_found",
                     "items_scraped", "cycle", "duration_sec", "error_type"):
            if hasattr(record, key):
                entry[key] = getattr(record, key)
        return json.dumps(entry, ensure_ascii=False)


def setup_logger(name: str = "vinted_bot", level: str = "INFO",
                 json_output: bool = True) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    if logger.handlers:
        return logger

    handler = logging.StreamHandler(sys.stdout)
    if json_output:
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(module)s: %(message)s",
            datefmt="%H:%M:%S"
        ))
    logger.addHandler(handler)
    return logger
