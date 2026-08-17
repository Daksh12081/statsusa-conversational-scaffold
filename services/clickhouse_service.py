import logging
import os
from typing import Any

from dotenv import load_dotenv


load_dotenv()

logger = logging.getLogger(__name__)


class ClickHouseQueryError(RuntimeError):
    """Raised when a ClickHouse query fails."""


class ClickHouseService:
    """Thin wrapper around the ClickHouse HTTP client.

    Reuses a single lazily-created client across calls instead of
    reconnecting on every query.
    """

    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is None:
            # Imported lazily so importing this module (and anything that
            # transitively imports it, e.g. nodes/execute_tasks.py) doesn't
            # pay clickhouse_connect's import cost until a query actually runs.
            import clickhouse_connect

            self._client = clickhouse_connect.get_client(
                host=os.getenv("CLICKHOUSE_HOST"),
                port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
                username=os.getenv("CLICKHOUSE_USER"),
                password=os.getenv("CLICKHOUSE_PASSWORD"),
                database=os.getenv("CLICKHOUSE_DATABASE"),
            )
        return self._client

    def query(
        self,
        sql: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        try:
            result = self._get_client().query(sql, parameters=parameters or {})
        except Exception as exc:
            logger.error("ClickHouse query failed: %s", exc)
            raise ClickHouseQueryError(f"ClickHouse query failed: {exc}") from exc

        return [
            dict(zip(result.column_names, row))
            for row in result.result_rows
        ]


# Singleton instance reused across the application.
clickhouse_service = ClickHouseService()
