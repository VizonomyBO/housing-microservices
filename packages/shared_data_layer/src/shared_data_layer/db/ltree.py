"""
Compat helpers for PostgreSQL LTREE support.

We prefer to use sqlalchemy-utils when it is available, but the tests and
migrations should not fail if the dependency is missing from the environment.
"""

from __future__ import annotations

from typing import Any, Callable, Optional, cast

from sqlalchemy.dialects.postgresql import base as pg_base
from sqlalchemy.engine import Dialect
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.types import UserDefinedType

try:  # pragma: no cover - exercised indirectly in test suites
    from sqlalchemy_utils import Ltree as _SQLAUtilsLtree
    from sqlalchemy_utils import LtreeType as _SQLAUtilsLtreeType
except ModuleNotFoundError:  # pragma: no cover

    class Ltree(str):
        """Lightweight stand-in for sqlalchemy_utils.Ltree."""

        def __new__(cls, value: Any) -> "Ltree":
            if isinstance(value, cls):
                return value
            if not isinstance(value, str):
                raise TypeError("Ltree value must be a string")
            return cast("Ltree", super().__new__(cls, value))

        def __repr__(self) -> str:
            return f"Ltree({super().__repr__()})"

    class _LtreeType(UserDefinedType):
        cache_ok = True

        def get_col_spec(self, **kw):
            return "LTREE"

        def bind_processor(  # type: ignore[override]
            self, dialect: Dialect
        ) -> Optional[Callable[[Any], Any]]:
            def process(value: Any) -> Any:
                if value is None:
                    return None
                if isinstance(value, Ltree):
                    return str(value)
                if isinstance(value, str):
                    return value
                raise TypeError("Ltree values must be strings")

            return process

        def result_processor(  # type: ignore[override]
            self, dialect: Dialect, coltype: Any
        ) -> Optional[Callable[[Any], Any]]:
            def process(value: Any) -> Any:
                if value is None:
                    return None
                return Ltree(value)

            return process

        def python_type(self):
            return str

    LtreeType = _LtreeType

    # Ensure reflected schemas recognize the type
    pg_base.ischema_names["ltree"] = LtreeType

    @compiles(LtreeType, "postgresql")
    def _compile_ltree(_type, compiler, **kw):  # pragma: no cover - trivial
        return "LTREE"

    try:  # pragma: no cover - only used during autogenerate
        from alembic.autogenerate import renderers
    except ImportError:
        renderers = cast(Any, None)
    else:

        @renderers.dispatch_for(LtreeType)
        def _render_ltree(type_, autogen_context):
            return "shared_data_layer.db.ltree.LtreeType()"

    __all__ = ["Ltree", "LtreeType"]

else:  # pragma: no cover
    Ltree = _SQLAUtilsLtree
    LtreeType = _SQLAUtilsLtreeType

    __all__ = ["Ltree", "LtreeType"]
