from __future__ import annotations

from typing import Any, Dict, List
import logging

from ml_metadata.metadata_store import metadata_store  # type: ignore
from ml_metadata.proto import metadata_store_pb2  # type: ignore

logger = logging.getLogger(__name__)


def connect_mlmd() -> "metadata_store.MetadataStore":
    cfg = metadata_store_pb2.ConnectionConfig()
    cfg.sqlite.filename_uri = "/mlmd-db/mlmd.db"
    store = metadata_store.MetadataStore(cfg)
    logger.info(f"connected to MLMD (sqlite file: {cfg.sqlite.filename_uri})")
    return store
