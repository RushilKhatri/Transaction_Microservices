"""
app/utils.py — Transaction Service
Sets up a structured JSON logger (ELK-ready).
Every log line is a JSON object with timestamp, level, service, message, and context.
"""

import logging
from pythonjsonlogger import jsonlogger


def setup_logger(service_name: str) -> logging.Logger:
    """
    Returns a logger that emits structured JSON to stdout.
    Compatible with Logstash / Filebeat / any ELK ingestion pipeline.
    """
    logger = logging.getLogger(service_name)

    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = jsonlogger.JsonFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            rename_fields={
                "asctime": "timestamp",
                "levelname": "level",
                "name": "service",
            },
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False

    return logger
