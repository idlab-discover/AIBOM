from __future__ import annotations

from typing import Any, Dict, List
import logging
import os

from ml_metadata.metadata_store import metadata_store  # type: ignore
from ml_metadata.proto import metadata_store_pb2  # type: ignore

logger = logging.getLogger(__name__)

#
# def connect_mlmd() -> "metadata_store.MetadataStore":
#     """Connect to MLMD using a MySQL backend (default).
#
#     Environment variables (with defaults):
#       - MLMD_HOST (default: "mysql")
#       - MLMD_PORT (default: "3306")
#       - MLMD_DATABASE (default: "mlmd")
#       - MLMD_USER (default: "mlmd")
#       - MLMD_PASSWORD (default: "mlmdpass")
#
#     If MLMD_BACKEND is set to "sqlite", falls back to the previous
#     SQLite-on-disk behavior for local/dev use and reads MLMD_SQLITE_PATH.
#     """
#     backend = os.environ.get("MLMD_BACKEND", "mysql").lower()
#     cfg = metadata_store_pb2.ConnectionConfig()
#
#     if backend == "sqlite":
#         sqlite_path = os.environ.get(
#             "MLMD_SQLITE_PATH", "/mlmd-sqlite/mlmd.db")
#         cfg.sqlite.filename_uri = sqlite_path
#         store = metadata_store.MetadataStore(
#             cfg, enable_upgrade_migration=True)
#         logger.info(
#             "connected to MLMD (sqlite file)",
#             extra={"sqlite_path": sqlite_path},
#         )
#         return store
#
#     # Default to MySQL
#     host = os.environ.get("MLMD_HOST", "mysql")
#     port = int(os.environ.get("MLMD_PORT", "3306"))
#     database = os.environ.get("MLMD_DATABASE", "metadb")
#     user = os.environ.get("MLMD_USER", "root")
#     password = os.environ.get("MLMD_PASSWORD", "")
#
#     logger.info(
#         "connecting to MLMD (mysql) backend=%s host=%s port=%s database=%s user=%s",
#         backend, host, port, database, user,
#     )
#
#     cfg.mysql.host = host
#     cfg.mysql.port = port
#     cfg.mysql.database = database
#     cfg.mysql.user = user
#     cfg.mysql.password = password
#
#     store = metadata_store.MetadataStore(cfg, enable_upgrade_migration=True)
#     logger.info(
#         "connected to MLMD (mysql)",
#         extra={"host": host, "port": port, "database": database, "user": user},
#     )
#     return store
#


def connect_mlmd():
    logger.info("connecting to MLMD via gRPC service")
    # Prefer env vars if provided, else default to Kubeflow service.
    host = os.environ.get("MLMD_GRPC_HOST", "metadata-grpc-service.kubeflow")
    port = int(os.environ.get("MLMD_GRPC_PORT", "8080"))

    client_config = metadata_store_pb2.MetadataStoreClientConfig()
    client_config.host = host
    client_config.port = port

    store = metadata_store.MetadataStore(client_config)
    logger.info("connected to MLMD via gRPC service",
                extra={"host": host, "port": port})
    return store
