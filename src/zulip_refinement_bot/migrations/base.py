from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class MigrationError(Exception):
    pass


class Migration(ABC):
    def __init__(self) -> None:
        self.applied_at: datetime | None = None

    @property
    @abstractmethod
    def version(self) -> str:
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        pass

    @property
    def dependencies(self) -> list[str]:
        if self.version == "001":
            return []
        return [f"{int(self.version) - 1:03d}"]

    @abstractmethod
    def up(self, conn: sqlite3.Connection) -> None:
        pass

    def down(self, conn: sqlite3.Connection) -> None:
        raise NotImplementedError(f"Rollback not implemented for migration {self.version}")

    def validate(self, conn: sqlite3.Connection) -> bool:
        return True

    def can_rollback(self) -> bool:
        try:
            return self.__class__.down is not Migration.down
        except AttributeError:
            return False

    def __str__(self) -> str:
        return f"Migration {self.version}: {self.description}"

    def __repr__(self) -> str:
        return f"<Migration(version='{self.version}', description='{self.description}')>"


class SchemaValidationMixin:
    def table_exists(self, conn: sqlite3.Connection, table_name: str) -> bool:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,)
        )
        return cursor.fetchone() is not None

    def column_exists(self, conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
        try:
            cursor = conn.execute(f"PRAGMA table_info({table_name})")
            columns = [row[1] for row in cursor.fetchall()]
            return column_name in columns
        except sqlite3.OperationalError:
            return False

    def index_exists(self, conn: sqlite3.Connection, index_name: str) -> bool:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name=?", (index_name,)
        )
        return cursor.fetchone() is not None

    def get_table_schema(self, conn: sqlite3.Connection, table_name: str) -> list[dict[str, Any]]:
        cursor = conn.execute(f"PRAGMA table_info({table_name})")
        return [
            {
                "cid": row[0],
                "name": row[1],
                "type": row[2],
                "notnull": bool(row[3]),
                "default_value": row[4],
                "pk": bool(row[5]),
            }
            for row in cursor.fetchall()
        ]

    def execute_sql(self, conn: sqlite3.Connection, sql: str, params: tuple = ()) -> None:
        try:
            logger.debug("Executing SQL", sql=sql, params=params)
            conn.execute(sql, params)
        except sqlite3.Error as e:
            logger.error("SQL execution failed", sql=sql, params=params, error=str(e))
            raise MigrationError(f"SQL execution failed: {e}") from e
