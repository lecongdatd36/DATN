"""Translate the project's three validation patterns without enabling CLR."""
from django.db import NotSupportedError
from django.db.models.lookups import Regex

WHITESPACE = tuple(value for value in range(0x3100) if chr(value).isspace())


class PortableRegex(Regex):
    def as_microsoft(self, compiler, connection):
        if not isinstance(self.rhs, str):
            raise NotSupportedError("SQL Server validation requires a literal regex pattern.")
        lhs, params = self.process_lhs(compiler, connection)
        binary = f"({lhs} COLLATE Latin1_General_100_BIN2)"
        if self.rhs == r"\S":
            cleaned = lhs
            # Unicode whitespace recognized by Python's validators, including
            # tabs/newlines and nonbreaking spaces; no weakening of CHECKs.
            for value in WHITESPACE:
                cleaned = f"REPLACE({cleaned}, NCHAR({value}), N'')"
            return f"(DATALENGTH({cleaned}) > 0)", params
        if self.rhs == r"^0[0-9]{9,10}$":
            return (f"(LEFT({lhs}, 1) = N'0' AND LEN({lhs}) BETWEEN 10 AND 11 "
                    f"AND {binary} NOT LIKE N'%%[^0-9]%%')"), params * 3
        if self.rhs == r"^[A-Z0-9][A-Z0-9_-]{0,19}$":
            return (f"(LEN({lhs}) BETWEEN 1 AND 20 AND LEFT({binary}, 1) LIKE N'[A-Z0-9]' "
                    f"AND {binary} NOT LIKE N'%%[^-A-Z0-9_]%%')"), params * 3
        raise NotSupportedError(f"SQL Server regex needs an explicit translation: {self.rhs!r}")
