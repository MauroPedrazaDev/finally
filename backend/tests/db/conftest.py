"""Fixtures for database tests: a fresh SQLite file per test."""

import pytest

from app import db


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    path = tmp_path / "test.db"
    monkeypatch.setenv("DB_PATH", str(path))
    db.init_db()
    return path
