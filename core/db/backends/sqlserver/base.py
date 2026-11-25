"""Microsoft backend with explicit support for this application's constraints."""
from django.db.models import Field
from mssql.base import DatabaseWrapper as MicrosoftDatabaseWrapper
from mssql.features import DatabaseFeatures as MicrosoftFeatures
from .lookups import PortableRegex
from .schema import DatabaseSchemaEditor

Field.register_lookup(PortableRegex)


class DatabaseFeatures(MicrosoftFeatures):
    # Materialized LOWER() expressions are handled by our schema editor.
    supports_expression_indexes = True


class DatabaseWrapper(MicrosoftDatabaseWrapper):
    SchemaEditorClass = DatabaseSchemaEditor
    features_class = DatabaseFeatures
