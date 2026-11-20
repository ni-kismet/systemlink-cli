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
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, urlencode

import yaml  # type: ignore[import-untyped]

from slcli.migration.annotations import COMPLETED_AT, STARTED_AT

BASE_URL = "{{base_url}}"

# Migration timestamps record when a write happened and cannot be reproduced
# without freezing a clock Prefect depends on, so matching ignores them.
IGNORED_PROPERTIES = frozenset({STARTED_AT, COMPLETED_AT})


def _parse_body(data: bytes) -> Any:
    """Return a body as YAML-friendly data: parsed JSON when possible, else text."""
    if not data:
        return None
    text = data.decode("utf-8")
    try:
        return json.loads(text)
    except ValueError:
        return text


def _mask(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: None if k in IGNORED_PROPERTIES else _mask(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_mask(v) for v in value]
    return value


def request_key(method: str, target: str, body: Any) -> str:
    """Return the text that two matching requests have in common."""
    path, _, query = target.partition("?")
    canonical_query = urlencode(sorted(parse_qsl(query, keep_blank_values=True)))
    canonical_body = json.dumps(_mask(body), sort_keys=True)
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
    ) -> "Exchange":
        """Build an exchange from live traffic, hiding the upstream URL."""
        hidden = response_body.replace(upstream_url.encode(), BASE_URL.encode())
        return cls(
            request=f"{method} {path_and_query}",
            body=_parse_body(body),
            response_status=status,
            content_type=content_type,
            response_body=_parse_body(hidden),
        )


class _Dumper(yaml.SafeDumper):
    """Writes multi-line strings as literal blocks so they stay readable."""


def _represent_str(dumper: yaml.SafeDumper, value: str) -> Any:
    style = "|" if "\n" in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


_Dumper.add_representer(str, _represent_str)


@dataclass
class Tape:
    """One server's exchanges for one test module, and the client's generated values."""

    exchanges: List[Exchange] = field(default_factory=list)
    generated: Dict[str, List[str]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "Tape":
        """Read a tape file."""
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls(
            [Exchange.from_yaml(item) for item in data.get("exchanges", [])],
            {name: list(values) for name, values in data.get("generated", {}).items()},
        )

    def save(self, path: Path) -> None:
        """Write the tape, preserving exchange and key order."""
        path.parent.mkdir(parents=True, exist_ok=True)
        data: Dict[str, Any] = {}
        if self.generated:
            data["generated"] = self.generated
        data["exchanges"] = [e.to_yaml() for e in self.exchanges]
        text = yaml.dump(
            data,
            Dumper=_Dumper,
            sort_keys=False,
            allow_unicode=True,
            width=100,
        )
        path.write_text(text, encoding="utf-8", newline="\n")
