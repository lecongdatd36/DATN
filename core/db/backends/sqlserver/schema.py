"""Preserve case-insensitive unique names using persisted computed columns."""
import hashlib
import re
from django.db import NotSupportedError
from django.db.models.functions import Lower
from django.db.models.sql import Query
from mssql.schema import DatabaseSchemaEditor as MicrosoftSchemaEditor


class DatabaseSchemaEditor(MicrosoftSchemaEditor):
    def _create_unique_sql(self, model, fields, name=None, condition=None,
                           deferrable=None, include=None, opclasses=None,
                           expressions=None, nulls_distinct=None):
        if condition:
            # SQL Server filtered indexes accept <>, but reject NOT (x = y).
            condition = re.sub(r"NOT \((\[[^\]]+\]) = (N?'(?:''|[^'])*')\)",
                               r"\1 <> \2", condition)
        if not expressions:
            return super()._create_unique_sql(
                model, fields, name=name, condition=condition, deferrable=deferrable,
                include=include, opclasses=opclasses, expressions=expressions,
                nulls_distinct=nulls_distinct)
        sources = expressions.get_source_expressions()
        source = sources[0] if len(sources) == 1 else None
        while source is not None and source.__class__.__name__ in {"IndexExpression", "ExpressionWrapper"}:
            source = source.get_source_expressions()[0]
        if (source is not None and source.__class__.__name__ == "Func"
                and source.extra.get("template") == "(%(expressions)s)"):
            source = source.get_source_expressions()[0]
        if not isinstance(source, Lower) or condition or not name:
            raise NotSupportedError("SQL Server supports only named, unfiltered LOWER unique constraints here.")
        compiler = Query(model, alias_cols=False).get_compiler(connection=self.connection)
        expression_sql, params = compiler.compile(source)
        if params:
            raise NotSupportedError("Computed unique columns cannot contain query parameters.")
        table = self.quote_name(model._meta.db_table)
        column = self.quote_name("qlnh_unique_" + hashlib.sha256(name.encode()).hexdigest()[:16])
        return (f"ALTER TABLE {table} ADD {column} AS ({expression_sql}) PERSISTED; "
                f"CREATE UNIQUE INDEX {self.quote_name(name)} ON {table} ({column})")
