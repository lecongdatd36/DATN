"""Django fixtures that preserve all six datetime/time microsecond digits."""
from datetime import datetime, time
from django.core.serializers.json import DjangoJSONEncoder, Serializer as JsonSerializer, Deserializer


class PreciseEncoder(DjangoJSONEncoder):
    def default(self, value):
        if isinstance(value, datetime):
            result = value.isoformat()
            return result[:-6] + "Z" if result.endswith("+00:00") else result
        if isinstance(value, time) and value.tzinfo is None:
            return value.isoformat()
        return super().default(value)


class Serializer(JsonSerializer):
    def _init_options(self):
        super()._init_options()
        self.json_kwargs["cls"] = PreciseEncoder
