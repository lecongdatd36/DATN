"""Compile the project's UTF-8 PO catalogs without a platform gettext install.

Supports contexts, plurals and multiline strings; fuzzy/incomplete entries fall
back to source text. The resulting MO files also work with standard gettext.
"""
import ast
from pathlib import Path
import re
import struct


def read_po(path):
    entries = {}
    for block in re.split(r"\n\s*\n", path.read_text(encoding="utf-8")):
        fields, current = {}, None
        if any(line.startswith("#, ") and "fuzzy" in line for line in block.splitlines()):
            continue
        for line in block.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith('"'):
                if current is None:
                    raise ValueError(f"Orphan PO continuation in {path}")
                fields[current] += ast.literal_eval(line)
            else:
                key, literal = line.split(None, 1)
                if key not in ("msgid", "msgid_plural", "msgctxt", "msgstr") and not re.fullmatch(r"msgstr\[\d+\]", key):
                    raise ValueError(f"Unknown PO field {key} in {path}")
                current = key
                fields[key] = ast.literal_eval(literal)
        if "msgid" not in fields:
            continue
        key = fields["msgid"]
        if "msgctxt" in fields:
            key = fields["msgctxt"] + "\x04" + key
        if "msgid_plural" in fields:
            key += "\x00" + fields["msgid_plural"]
            indices = sorted(int(k[7:-1]) for k in fields if k.startswith("msgstr["))
            value = "\x00".join(fields[f"msgstr[{i}]"] for i in indices)
        else:
            value = fields.get("msgstr", "")
        if value:
            entries[key] = value
    return entries


def compile_po(path):
    entries = read_po(path)
    keys = sorted(entries, key=lambda value: value.encode("utf-8"))
    originals, translations, original_table, translated_table = bytearray(), bytearray(), [], []
    start = 28 + 16 * len(keys)
    for key in keys:
        data = key.encode("utf-8")
        original_table.extend((len(data), start + len(originals)))
        originals.extend(data + b"\x00")
    for key in keys:
        data = entries[key].encode("utf-8")
        translated_table.extend((len(data), start + len(originals) + len(translations)))
        translations.extend(data + b"\x00")
    data = struct.pack("<7I", 0x950412DE, 0, len(keys), 28, 28 + 8 * len(keys), 0, 0)
    data += struct.pack(f"<{4*len(keys)}I", *(original_table + translated_table))
    path.with_suffix(".mo").write_bytes(data + originals + translations)
    return len(entries)


if __name__ == "__main__":
    for path in sorted((Path(__file__).resolve().parents[1] / "locale").glob("*/LC_MESSAGES/*.po")):
        print(f"Compiled {path.relative_to(path.parents[3])}: {compile_po(path)} entries")
