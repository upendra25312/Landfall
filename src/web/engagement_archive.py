"""Validate an entire engagement ZIP before any data is written to storage."""
import io
import json
import zipfile

import web_access


class InvalidArchive(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def unpack(data: bytes, limit: int):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > 10000 or sum(e.file_size for e in entries) > limit:
                raise InvalidArchive("expanded archive exceeds the import limit", 413)
            names = set()
            for entry in entries:
                name = entry.filename
                parts = name.rstrip("/").split("/")
                if (name in names or "\\" in name or ":" in name or
                        any(p in ("", ".", "..") for p in parts) or
                        (entry.external_attr >> 16) & 0o170000 == 0o120000 or
                        (name != "export.json" and (len(parts) < 2 or parts[0] not in ("raw", "answers", "sql")))):
                    raise InvalidArchive("unsafe or duplicate archive member")
                names.add(name)
            meta = json.loads(archive.read("export.json"))
            if not isinstance(meta, dict) or meta.get("format") != "landfall-engagement/1":
                raise InvalidArchive("unsupported engagement export format")
            eid = meta.get("engagement")
            parts = eid.split("/") if isinstance(eid, str) else []
            if len(parts) != 2 or not all(web_access._seg(p) == p for p in parts):
                raise InvalidArchive("bad engagement id in export")
            manifest = json.loads(archive.read("raw/_engagement.json"))
            if not isinstance(manifest, dict) or manifest.get("engagement") != eid:
                raise InvalidArchive("engagement manifest does not match export")
            # Reading everything also checks CRCs before any blob write occurs.
            members = {e.filename: archive.read(e) for e in entries if not e.is_dir()}
            return eid, manifest, members
    except InvalidArchive:
        raise
    except (ValueError, KeyError, zipfile.BadZipFile, RuntimeError, NotImplementedError, OSError) as exc:
        raise InvalidArchive("not a valid Landfall engagement export") from exc
