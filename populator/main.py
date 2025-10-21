
import argparse
import os
import logging
import json
from ml_metadata.metadata_store import metadata_store  # type: ignore
from ml_metadata.proto import metadata_store_pb2  # type: ignore
from scenario_loader import populate_mlmd_from_scenario


logger = logging.getLogger(__name__)


def setup_logging() -> None:
    """Configure root logging from environment variables.

    LOG_LEVEL: DEBUG, INFO, WARNING, ERROR, CRITICAL (default: INFO)
    LOG_FORMAT: 'plain' (default) or 'json' (lightweight JSON)
    """
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    fmt_choice = os.environ.get("LOG_FORMAT", "plain").lower()

    handler = logging.StreamHandler()
    if fmt_choice == "json":
        class JsonFormatter(logging.Formatter):
            # type: ignore[override]
            def format(self, record: logging.LogRecord) -> str:
                data = {
                    "ts": int(record.created * 1000),
                    "level": record.levelname,
                    "logger": record.name,
                    "msg": record.getMessage(),
                }
                std = {
                    'name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 'filename', 'module', 'exc_info',
                    'exc_text', 'stack_info', 'lineno', 'funcName', 'created', 'msecs', 'relativeCreated', 'thread',
                    'threadName', 'processName', 'process', 'asctime'
                }
                for k, v in record.__dict__.items():
                    if k not in std and not k.startswith('_'):
                        try:
                            json.dumps({k: v})
                            data[k] = v
                        except Exception:
                            data[k] = str(v)
                if record.exc_info:
                    data["exc_info"] = self.formatException(record.exc_info)
                return json.dumps(data)
        handler.setFormatter(JsonFormatter())
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s %(levelname)s %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
        handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        root.addHandler(handler)
    else:
        for h in root.handlers:
            if isinstance(h, logging.StreamHandler):
                h.setLevel(level)
                h.setFormatter(handler.formatter)


def connect_mlmd() -> "metadata_store.MetadataStore":
    cfg = metadata_store_pb2.ConnectionConfig()
    cfg.sqlite.filename_uri = "/mlmd-db/mlmd.db"
    store = metadata_store.MetadataStore(cfg)
    logger.info(f"connected to MLMD (sqlite file: {cfg.sqlite.filename_uri})")
    return store


def main():
    setup_logging()

    # Always clear the persistent sqlite DB before populating (clear contents, do not remove file because then we need to reconnect each time for debugging)
    db_path = "/mlmd-db/mlmd.db"
    try:
        import sqlite3
        if os.path.exists(db_path):
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("PRAGMA writable_schema = 1;")
                cursor.execute(
                    "DELETE FROM sqlite_master WHERE type IN ('table', 'index', 'trigger');")
                cursor.execute("PRAGMA writable_schema = 0;")
                conn.commit()
            logger.info("cleared existing MLMD sqlite DB contents",
                        extra={"db_path": db_path})
    except Exception as e:
        logger.warning("failed to clear existing DB", extra={
                       "db_path": db_path, "error": str(e)})

    store = connect_mlmd()

    # Default scenarios live under ./mlmd/scenarios in the repo
    scenario = os.environ.get(
        "SCENARIO_YAML", "scenarios/simple-scenario-1.yaml")
    logger.info("loading scenario file", extra={"scenario": scenario})

    populate_mlmd_from_scenario(store, scenario)


if __name__ == "__main__":
    main()
