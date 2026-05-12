"""Structured logging for the pipeline."""

import logging
import sys
from datetime import datetime
from pathlib import Path


def setup_logging(config: dict) -> logging.Logger:
    """Configure logging from config.yaml."""
    level = getattr(logging, config.get("logging", {}).get("level", "INFO").upper())
    log_file_template = config.get("logging", {}).get("file", "./logs/pipeline_{timestamp}.log")
    log_file = log_file_template.format(timestamp=datetime.now().strftime("%Y%m%d_%H%M%S"))

    # Resolve relative to project root
    project_root = Path(__file__).parent.parent
    log_path = project_root / log_file
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("paper_collector")
    logger.setLevel(level)

    # File handler
    fh = logging.FileHandler(str(log_path))
    fh.setLevel(level)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(fh)

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(level)
    ch.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    logger.addHandler(ch)

    return logger
