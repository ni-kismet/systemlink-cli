"""Tapes: real SystemLink HTTP exchanges, stored as readable, editable YAML.

A tape holds one server's exchanges in recording order, and the values the
client generated during the recording, such as migration IDs::

    generated:
      migrationId:
      - 0b6f...
    exchanges:
    - request: POST /nitestmonitor/v2/products
      body:
        products:
        - partNumber: migration-e2e-fresh
      response:
        status: 200
        body:
          products:
          - id: 5f1c...

Requests keep only the method, path, query, and body; headers are never stored,
so credentials cannot reach a tape. The upstream URL is written as
``{{base_url}}``. Hand edits are allowed; add a ``note`` explaining any edit.

Binary bodies, such as downloaded packages and uploaded multipart file parts,
are saved as files in a directory named after the tape and referenced with a
``!file`` tag, relative to the tape's directory::

    - request: GET /nirepo/v1/files/packages/foo_1.0_x64.nipkg
      response:
        status: 200
        contentType: application/octet-stream
        body: !file 'test_module/3f2a9c1b7d4e-foo_1.0_x64.nipkg'
"""

import hashlib
import json
import re
import shutil
from dataclasses import dataclass, field
from email.message import Message
from email.parser import BytesHeaderParser
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, unquote, urlencode

import yaml  # type: ignore[import-untyped]

from slcli.migration.annotations import COMPLETED_AT, STARTED_AT

BASE_URL = "{{base_url}}"
FILE_TAG = "!file"

# Migration timestamps record when a write happened and cannot be reproduced
# without freezing a clock Prefect depends on, so matching ignores them.
IGNORED_PROPERTIES = frozenset({STARTED_AT, COMPLETED_AT})

_TEXT_CONTENT_TYPES = ("json", "text/", "xml", "x-www-form-urlencoded")


@dataclass(frozen=True)
class FileData:
    """Binary content that a tape stores in a file beside it, not in the YAML."""

    name: str
    data: bytes

    def digest(self) -> str:
        """Return the SHA-256 of the content, which is how requests match it."""
        return hashlib.sha256(self.data).hexdigest()

    def file_name(self) -> str:
        """Return a readable file name that is unique to the content."""
        safe = re.sub(r"[^A-Za-z0-9._+-]", "_", self.name).strip(".") or "body"
        return f"{self.digest()[:12]}-{safe}"


def _is_text(content_type: Optional[str]) -> bool:
    return not content_type or any(t in content_type.lower() for t in _TEXT_CONTENT_TYPES)


def _content_type_param(content_type: str, param: str) -> Optional[str]:
    message = Message()
    message["Content-Type"] = content_type
    value = message.get_param(param)
    return value if isinstance(value, str) else None


def _parse_multipart(data: bytes, boundary: str) -> List[Dict[str, Any]]:
    """Split a multipart form into its parts, without the random boundary."""
    parts: List[Dict[str, Any]] = []
    for section in data.split(b"--" + boundary.encode())[1:-1]:
        head, _, content = section.removeprefix(b"\r\n").partition(b"\r\n\r\n")
        headers = BytesHeaderParser().parsebytes(head + b"\r\n\r\n")
        content = content.removesuffix(b"\r\n")
        part: Dict[str, Any] = {"name": headers.get_param("name", header="content-disposition")}
        filename = headers.get_param("filename", header="content-disposition")
        if isinstance(filename, str):
            part["filename"] = filename
        if headers["Content-Type"]:
            part["contentType"] = headers["Content-Type"]
        part["body"] = (
            FileData(filename, content)
            if isinstance(filename, str)
            else _parse_body(content, headers["Content-Type"], str(part["name"]))
        )
        parts.append(part)
    return parts


def _parse_body(data: bytes, content_type: Optional[str] = None, name: str = "body") -> Any:
    """Return a body as YAML-friendly data.

    Multipart forms become a list of parts, JSON is parsed, other text stays text,
    and binary content becomes :class:`FileData` named ``name``.
    """
    if not data:
        return None
    if content_type and content_type.lower().startswith("multipart/"):
        boundary = _content_type_param(content_type, "boundary")
        if boundary:
            return {"multipart": _parse_multipart(data, boundary)}
    if not _is_text(content_type):
        return FileData(name, data)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return FileData(name, data)
    try:
        return json.loads(text)
    except ValueError:
        return text


def parse_request_body(target: str, body: bytes, content_type: Optional[str]) -> Any:
    """Return a request body in the form tapes store and match it."""
    return _parse_body(body, content_type, _last_segment(target))


def _last_segment(target: str) -> str:
    return unquote(target.partition("?")[0].rstrip("/").rsplit("/", 1)[-1])


def _mask(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: None if k in IGNORED_PROPERTIES else _mask(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_mask(v) for v in value]
    return value


def _json_default(value: Any) -> str:
    if isinstance(value, FileData):
        return f"sha256:{value.digest()}"
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


def request_key(method: str, target: str, body: Any) -> str:
    """Return the text that two matching requests have in common."""
    path, _, query = target.partition("?")
    canonical_query = urlencode(sorted(parse_qsl(query, keep_blank_values=True)))
    canonical_body = json.dumps(_mask(body), sort_keys=True, default=_json_default)
    return f"{method} {path}?{canonical_query} {canonical_body}"


@dataclass
class Exchange:
    """One recorded request and its response."""

    request: str
    response_status: int
    body: Any = None
    response_body: Any = None
    content_type: Optional[str] = None
    note: Optional[str] = None

    def key(self) -> str:
        """Return this exchange's request key; see :func:`request_key`."""
        method, _, target = self.request.partition(" ")
        return request_key(method, target, self.body)

    def response_bytes(self, base_url: str) -> bytes:
        """Return the response body, addressed to ``base_url``."""
        if self.response_body is None:
            return b""
        if isinstance(self.response_body, FileData):
            return self.response_body.data
        if isinstance(self.response_body, str) and not (self.content_type or "").count("json"):
            text = self.response_body
        else:
            text = json.dumps(self.response_body, ensure_ascii=False)
        return text.replace(BASE_URL, base_url).encode("utf-8")

    def to_yaml(self) -> Dict[str, Any]:
        """Return the exchange as it appears in a tape."""
        data: Dict[str, Any] = {"request": self.request}
        if self.note:
            data["note"] = self.note
        if self.body is not None:
            data["body"] = self.body
        response: Dict[str, Any] = {"status": self.response_status}
        if self.content_type:
            response["contentType"] = self.content_type
        if self.response_body is not None:
            response["body"] = self.response_body
        data["response"] = response
        return data

    @classmethod
    def from_yaml(cls, data: Dict[str, Any]) -> "Exchange":
        """Read an exchange from a tape."""
        response = data["response"]
        return cls(
            request=data["request"],
            body=data.get("body"),
            note=data.get("note"),
            response_status=response["status"],
            content_type=response.get("contentType"),
            response_body=response.get("body"),
        )

    @classmethod
    def recorded(
        cls,
        method: str,
        path_and_query: str,
        body: bytes,
        status: int,
        content_type: Optional[str],
        response_body: bytes,
        upstream_url: str,
        request_content_type: Optional[str] = None,
    ) -> "Exchange":
        """Build an exchange from live traffic, hiding the upstream URL in text responses."""
        name = _last_segment(path_and_query)
        parsed = _parse_body(response_body, content_type, name)
        if not isinstance(parsed, FileData):
            hidden = response_body.replace(upstream_url.encode(), BASE_URL.encode())
            parsed = _parse_body(hidden, content_type, name)
        return cls(
            request=f"{method} {path_and_query}",
            body=parse_request_body(path_and_query, body, request_content_type),
            response_status=status,
            content_type=content_type,
            response_body=parsed,
        )


class _FileRef(str):
    """A tape-relative path to a :class:`FileData` file, written with ``!file``."""


def _externalize(value: Any, directory: Path) -> Any:
    """Write each :class:`FileData` under ``directory`` and replace it with a reference."""
    if isinstance(value, FileData):
        directory.mkdir(parents=True, exist_ok=True)
        (directory / value.file_name()).write_bytes(value.data)
        return _FileRef(f"{directory.name}/{value.file_name()}")
    if isinstance(value, dict):
        return {k: _externalize(v, directory) for k, v in value.items()}
    if isinstance(value, list):
        return [_externalize(v, directory) for v in value]
    return value


class _Dumper(yaml.SafeDumper):
    """Writes multi-line strings as literal blocks so they stay readable."""


def _represent_str(dumper: yaml.SafeDumper, value: str) -> Any:
    style = "|" if "\n" in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


def _represent_file(dumper: yaml.SafeDumper, value: _FileRef) -> Any:
    return dumper.represent_scalar(FILE_TAG, str(value))


_Dumper.add_representer(str, _represent_str)
_Dumper.add_representer(_FileRef, _represent_file)


class _Loader(yaml.SafeLoader):
    """Reads ``!file`` references relative to the tape's directory."""

    directory: Path = Path(".")


def _construct_file(loader: _Loader, node: yaml.Node) -> FileData:
    relative = loader.construct_scalar(node)
    return FileData(Path(relative).name, (loader.directory / relative).read_bytes())


_Loader.add_constructor(FILE_TAG, _construct_file)


@dataclass
class Tape:
    """One server's exchanges for one test module, and the client's generated values."""

    exchanges: List[Exchange] = field(default_factory=list)
    generated: Dict[str, List[str]] = field(default_factory=dict)

    @staticmethod
    def files_dir(path: Path) -> Path:
        """Return the directory that holds a tape's binary bodies."""
        return path.with_suffix("")

    @classmethod
    def load(cls, path: Path) -> "Tape":
        """Read a tape file and the binary bodies it references."""
        loader = _Loader(path.read_text(encoding="utf-8"))
        loader.directory = path.parent
        try:
            data = loader.get_single_data() or {}
        finally:
            loader.dispose()
        return cls(
            [Exchange.from_yaml(item) for item in data.get("exchanges", [])],
            {name: list(values) for name, values in data.get("generated", {}).items()},
        )

    def save(self, path: Path) -> None:
        """Write the tape and its binary bodies, preserving exchange and key order."""
        path.parent.mkdir(parents=True, exist_ok=True)
        files_dir = self.files_dir(path)
        # Recording replaces a tape wholesale, so its old binary bodies go too.
        shutil.rmtree(files_dir, ignore_errors=True)
        data: Dict[str, Any] = {}
        if self.generated:
            data["generated"] = self.generated
        data["exchanges"] = [_externalize(e.to_yaml(), files_dir) for e in self.exchanges]
        text = yaml.dump(
            data,
            Dumper=_Dumper,
            sort_keys=False,
            allow_unicode=True,
            width=100,
        )
        path.write_text(text, encoding="utf-8", newline="\n")
