
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
    backend = os.environ.get("MLMD_BACKEND", "mysql").lower()
    cfg = metadata_store_pb2.ConnectionConfig()

    if backend == "sqlite":
        sqlite_path = os.environ.get("MLMD_SQLITE_PATH", "/mlmd-db/mlmd.db")
        cfg.sqlite.filename_uri = sqlite_path
        store = metadata_store.MetadataStore(
            cfg, enable_upgrade_migration=True)
        logger.info("connected to MLMD (sqlite)",
                    extra={"sqlite_path": sqlite_path})
        return store

    host = os.environ.get("MLMD_HOST", "mysql")
    port = int(os.environ.get("MLMD_PORT", "3306"))
    database = os.environ.get("MLMD_DATABASE", "mlmd")
    user = os.environ.get("MLMD_USER", "mlmd")
    password = os.environ.get("MLMD_PASSWORD", "mlmdpass")

    cfg.mysql.host = host
    cfg.mysql.port = port
    cfg.mysql.database = database
    cfg.mysql.user = user
    cfg.mysql.password = password

    store = metadata_store.MetadataStore(cfg, enable_upgrade_migration=True)
    logger.info(
        "connected to MLMD (mysql)",
        extra={"host": host, "port": port, "database": database, "user": user},
    )
    return store


def main():
    setup_logging()

    backend = os.environ.get("MLMD_BACKEND", "mysql").lower()
    if os.environ.get("MLMD_RESET_DB", "no").lower() in {"1", "true", "yes"}:
        if backend == "mysql":
            try:
                import mysql.connector  # type: ignore
                host = os.environ.get("MLMD_HOST", "mysql")
                port = int(os.environ.get("MLMD_PORT", "3306"))
                database = os.environ.get("MLMD_DATABASE", "mlmd")
                # Prefer root creds if provided for DROP/CREATE DATABASE
                root_password = os.environ.get(
                    "MLMD_ROOT_PASSWORD") or os.environ.get("MYSQL_ROOT_PASSWORD")
                if root_password:
                    user = "root"
                    password = root_password
                else:
                    user = os.environ.get("MLMD_USER", "mlmd")
                    password = os.environ.get("MLMD_PASSWORD", "mlmdpass")

                conn = mysql.connector.connect(
                    host=host, port=port, user=user, password=password)
                conn.autocommit = True
                cur = conn.cursor()
                # Ensure user exists with native password (for MLMD compatibility with libmysqlclient)
                cur.execute(
                    "CREATE USER IF NOT EXISTS 'mlmd'@'%' IDENTIFIED WITH mysql_native_password BY 'mlmdpass';")
                cur.execute(
                    "ALTER USER 'mlmd'@'%' IDENTIFIED WITH mysql_native_password BY 'mlmdpass';")
                cur.execute("FLUSH PRIVILEGES;")
                cur.execute(f"DROP DATABASE IF EXISTS `{database}`;")
                cur.execute(
                    f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
                cur.execute(
                    "GRANT ALL PRIVILEGES ON `{db}`.* TO 'mlmd'@'%';".format(db=database))
                cur.execute("FLUSH PRIVILEGES;")
                cur.close()
                conn.close()
                logger.info("reset MySQL database for MLMD", extra={
                            "database": database, "host": host, "port": port})
            except Exception as e:
                logger.warning(f"failed to reset MySQL database: {e}")
        elif backend == "sqlite":
            sqlite_path = os.environ.get(
                "MLMD_SQLITE_PATH", "/mlmd-sqlite/mlmd.db")
            try:
                import sqlite3
                if os.path.exists(sqlite_path):
                    with sqlite3.connect(sqlite_path) as conn:
                        cursor = conn.cursor()
                        cursor.execute("PRAGMA writable_schema = 1;")
                        cursor.execute(
                            "DELETE FROM sqlite_master WHERE type IN ('table', 'index', 'trigger');")
                        cursor.execute("PRAGMA writable_schema = 0;")
                        conn.commit()
                    logger.info("cleared existing SQLite DB contents",
                                extra={"sqlite_path": sqlite_path})
            except Exception as e:
                logger.warning(f"failed to clear SQLite DB file: {e}")

    store = connect_mlmd()

    # Default scenarios live under ./mlmd/scenarios in the repo
    scenario = os.environ.get(
        "SCENARIO_YAML", "scenarios/simple-scenario-1.yaml")
    logger.info("loading scenario file", extra={"scenario": scenario})

    populate_mlmd_from_scenario(store, scenario)


if __name__ == "__main__":
    main()
