"""
Structured logging for ArchDocAI.

Single setup call (setup_logging) configures:
  - Console handler: human-readable colored output
  - File handler:    JSON-lines format for easy parsing/grep

Every module gets its logger via:
    from src.logger import get_logger
    log = get_logger(__name__)

Log records include: timestamp, level, logger name, message,
and optionally job_id when passed as extra={"job_id": "..."}.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# JSON formatter for file output
# ---------------------------------------------------------------------------

class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # Attach any extra fields (e.g. job_id, ip)
        for key in ("job_id", "ip", "git_url", "provider", "model"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(payload, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Console formatter - readable, minimal
# ---------------------------------------------------------------------------

LEVEL_COLORS = {
    "DEBUG":    "\033[37m",
    "INFO":     "\033[36m",
    "WARNING":  "\033[33m",
    "ERROR":    "\033[31m",
    "CRITICAL": "\033[35m",
}
RESET = "\033[0m"


class ConsoleFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        color = LEVEL_COLORS.get(record.levelname, "")
        ts = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        job = f" [{record.job_id}]" if hasattr(record, "job_id") else ""
        return f"{color}{ts} {record.levelname:<8}{RESET} {record.name}{job} - {record.getMessage()}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_configured = False


def setup_logging(log_dir: str = "./logs", level: str = "INFO") -> None:
    global _configured
    if _configured:
        return
    _configured = True

    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Console
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(ConsoleFormatter())
    root.addHandler(ch)

    # File (JSON lines, one log per day)
    today = datetime.now().strftime("%Y-%m-%d")
    fh = logging.FileHandler(log_path / f"archdoc_{today}.log", encoding="utf-8")
    fh.setFormatter(JsonFormatter())
    root.addHandler(fh)

    # Silence noisy third-party loggers
    for noisy in ("httpx", "httpcore", "openai", "anthropic", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
