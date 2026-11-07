"""Spare Parts module's own SQLAlchemy declarative base and DB access.

Per the user's explicit choice ("same database, same connection"), this
reuses the main app's live engine/session factory from app.db.session as
a generic shared DB-connection utility - the one exception independence
rule #1 (see spare_parts/__init__.py) allows, since it touches no table
or model from the rest of the app, only the connection object itself.

Reusing the *live* SessionLocal/engine objects (not a second engine
pointed at a snapshot of the same URL) also means that if the app's DB
settings are ever changed at runtime, this module's sessions pick up the
new connection automatically, the same way every other part of the app
does, since app.db.session.SessionLocal.configure() mutates that one
factory object in place.

SpareBase is a completely separate declarative base from app.db.models.Base.
Its metadata only ever contains sp_-prefixed tables, so
app.db.models.Base.metadata.create_all() elsewhere can never touch this
module's tables, and spare_parts/db/migrations.py (the only place that
calls SpareBase.metadata.create_all()) can never touch the main app's.
"""
from __future__ import annotations

from sqlalchemy.orm import declarative_base

# The one sanctioned cross-package import - see module docstring above and
# spare_parts/__init__.py rule #1.
from app.db.session import SessionLocal as _AppSessionLocal
from app.db.session import engine as _app_engine

SpareBase = declarative_base()


def get_engine():
    """The app's live SQLAlchemy engine (shared connection, not a table)."""
    return _app_engine


def get_spare_session():
    """A new session on the app's shared database connection.

    Callers own the session's lifecycle (commit/rollback/close) - the
    service layer takes a `db` argument rather than opening its own
    session per call, so a single caller-owned session can span an
    entire header+items+ledger save as one transaction (needed from
    Phase 2 onward for the "all succeed or all roll back" requirement).
    """
    return _AppSessionLocal()
