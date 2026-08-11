import os
from typing import Any

import clickhouse_connect
from dotenv import load_dotenv


load_dotenv()


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
            raise ClickHouseQueryError(f"ClickHouse query failed: {exc}") from exc

        return [
            dict(zip(result.column_names, row))
            for row in result.result_rows
        ]


# Singleton instance reused across the application.
clickhouse_service = ClickHouseService()
