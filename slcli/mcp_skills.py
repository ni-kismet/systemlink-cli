"""MCP Skills extension support for the bundled slcli Agent Skill."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Optional, Tuple
from urllib.parse import unquote, urlsplit

import yaml  # type: ignore[import-untyped]
from mcp.server.context import ServerRequestContext
from mcp.server.extension import Extension, MethodBinding, ResourceBinding
from mcp.server.mcpserver.resources import BinaryResource, Resource, TextResource
from mcp.shared.exceptions import MCPError
from mcp.types import (
    INVALID_PARAMS,
    METHOD_NOT_FOUND,
    PaginatedRequestParams,
    RequestParams,
    Resource as MCPResource,
)
from mcp.types.version import is_version_at_least
from pydantic import BaseModel, ConfigDict, Field

SKILLS_EXTENSION_IDENTIFIER = "io.modelcontextprotocol/skills"
SKILLS_PROTOCOL_VERSION = "2026-07-28"
SKILL_URI = "skill://slcli/SKILL.md"
SKILL_ROOT_URI = "skill://slcli"
DIRECTORY_MIME_TYPE = "inode/directory"
SKILLS_CACHE_TTL_MS = 300_000
SKILLS_CACHE_SCOPE = "public"
MAX_RESOURCES_PER_SKILL = 512
MAX_SKILL_SIZE = 16 * 1024 * 1024

_SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_FRONTMATTER_PATTERN = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)
_MIME_TYPES = {
    ".html": "text/html",
    ".json": "application/json",
    ".md": "text/markdown",
    ".py": "text/x-python",
    ".svg": "image/svg+xml",
}


class GetSkillParams(RequestParams):
    """Parameters for the skills/get request."""

    uri: str


class ListSkillsParams(PaginatedRequestParams):
    """Parameters for the skills/list request."""


class ReadDirectoryParams(PaginatedRequestParams):
    """Parameters for the resources/directory/read request."""

    uri: str


class SkillResourceManifest(BaseModel):
    """Digest and size metadata for one skill resource."""

    uri: str
    digest: str
    size: int = Field(ge=0)


class SkillEntry(BaseModel):
    """A complete MCP Skills entry for one Agent Skill."""

    uri: str
    frontmatter: Dict[str, Any]
    resources: List[SkillResourceManifest]


class ListSkillsResult(BaseModel):
    """Result returned by skills/list."""

    result_type: str = Field(default="complete", alias="resultType")
    skills: List[SkillEntry]
    ttl_ms: int = Field(default=SKILLS_CACHE_TTL_MS, alias="ttlMs", ge=0)
    cache_scope: str = Field(default=SKILLS_CACHE_SCOPE, alias="cacheScope")

    model_config = ConfigDict(populate_by_name=True)


class GetSkillResult(BaseModel):
    """Result returned by skills/get."""

    result_type: str = Field(default="complete", alias="resultType")
    skill: SkillEntry
    ttl_ms: int = Field(default=SKILLS_CACHE_TTL_MS, alias="ttlMs", ge=0)
    cache_scope: str = Field(default=SKILLS_CACHE_SCOPE, alias="cacheScope")

    model_config = ConfigDict(populate_by_name=True)


class ReadDirectoryResult(BaseModel):
    """Result returned by resources/directory/read."""

    result_type: str = Field(default="complete", alias="resultType")
    resources: List[MCPResource]

    model_config = ConfigDict(populate_by_name=True)


@dataclass(frozen=True)
class SkillFile:
    """One immutable file in the published skill namespace."""

    relative_path: str
    uri: str
    content: bytes
    mime_type: str
    resource: Resource
    manifest: SkillResourceManifest


@dataclass(frozen=True)
class SkillCatalog:
    """The validated, immutable view of one published skill."""

    entry: SkillEntry
    files: Mapping[str, SkillFile]
    directories: Mapping[str, Tuple[MCPResource, ...]]

    def resources(self) -> List[ResourceBinding]:
        """Return all file resources contributed to the MCP server."""
        return [ResourceBinding(resource=file.resource) for file in self.files.values()]

    def validate_file_uri(self, uri: str) -> SkillFile:
        """Return a file for a canonical skill URI or raise Invalid params."""
        relative_path = _relative_path_for_uri(uri)
        file = self.files.get(relative_path)
        if file is None:
            raise _invalid_params(f"No skill resource is served at {uri}")
        return file

    def directory_children(self, uri: str) -> Tuple[MCPResource, ...]:
        """Return direct children for a canonical directory URI."""
        relative_path = _relative_path_for_uri(uri)
        try:
            return self.directories[uri]
        except KeyError as exc:
            if relative_path in self.files:
                raise _invalid_params(f"{uri} is not a directory resource") from exc
            raise _invalid_params(f"No directory resource is served at {uri}") from exc


def _invalid_params(message: str) -> MCPError:
    """Create the standard error for an invalid Skills request."""
    return MCPError(code=INVALID_PARAMS, message=message)


def _modern_only(
    handler: Callable[[ServerRequestContext[Any, Any], Any], Awaitable[Any]],
) -> Callable[[ServerRequestContext[Any, Any], Any], Awaitable[Any]]:
    """Restrict an extension method to the target revision and later known revisions."""

    async def gated(context: ServerRequestContext[Any, Any], params: Any) -> Any:
        if not is_version_at_least(context.protocol_version, SKILLS_PROTOCOL_VERSION):
            raise MCPError(code=METHOD_NOT_FOUND, message="Method not found")
        return await handler(context, params)

    return gated


def _skill_root_candidates() -> List[Path]:
    """Return source and frozen bundled-skill roots."""
    candidates: List[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "skills" / "slcli")
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / "skills" / "slcli")
    candidates.append(Path(__file__).resolve().parent / "skills" / "slcli")
    return candidates


def _find_skill_root() -> Path:
    """Locate the bundled skill directory."""
    for candidate in _skill_root_candidates():
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError("Bundled slcli skill not found.")


def _ensure_regular_file(path: Path) -> None:
    """Reject symlinks and non-regular files in published content."""
    if path.is_symlink():
        raise ValueError(f"Published skill path must not be a symlink: {path}")
    if not path.is_file():
        raise ValueError(f"Published skill path must be a regular file: {path}")


def _published_paths(root: Path) -> List[Path]:
    """Return files allowed by the explicit MCP publication policy."""
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f"Skill root must be a real directory: {root}")

    skill_file = root / "SKILL.md"
    _ensure_regular_file(skill_file)
    paths = [skill_file]

    references = root / "references"
    if references.is_symlink() or references.exists():
        if references.is_symlink() or not references.is_dir():
            raise ValueError(f"Skill references must be a real directory: {references}")
        for path in sorted(references.rglob("*")):
            if path.is_symlink():
                raise ValueError(f"Published skill path must not be a symlink: {path}")
            relative_parts = path.relative_to(root).parts
            if any(part.startswith(".") or part == "__pycache__" for part in relative_parts):
                continue
            if path.is_dir():
                continue
            if not path.is_file():
                raise ValueError(f"Published skill path must be a regular file: {path}")
            if path.suffix != ".pyc":
                paths.append(path)

    scripts = root / "scripts"
    if scripts.is_symlink() or scripts.exists():
        if scripts.is_symlink() or not scripts.is_dir():
            raise ValueError(f"Skill scripts must be a real directory: {scripts}")
        for path in sorted(scripts.iterdir()):
            if path.is_symlink():
                raise ValueError(f"Published skill path must not be a symlink: {path}")
            if path.name.startswith(".") or path.name == "__pycache__":
                continue
            if not path.is_file():
                raise ValueError(f"Published skill path must be a regular file: {path}")
            if path.suffix == ".py":
                paths.append(path)

    return sorted(paths, key=lambda path: path.relative_to(root).as_posix())


def _frontmatter(content: bytes, path: Path) -> Dict[str, Any]:
    """Parse and validate the complete YAML frontmatter object."""
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"SKILL.md must be UTF-8: {path}") from exc
    match = _FRONTMATTER_PATTERN.match(text)
    if match is None:
        raise ValueError(f"SKILL.md must begin with YAML frontmatter: {path}")
    parsed = yaml.safe_load(match.group(1))
    if not isinstance(parsed, dict) or not all(isinstance(key, str) for key in parsed):
        raise ValueError(f"SKILL.md frontmatter must be a JSON object: {path}")
    try:
        json.dumps(parsed)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"SKILL.md frontmatter must contain JSON values: {path}") from exc
    name = parsed.get("name")
    description = parsed.get("description")
    if not isinstance(name, str) or not _SKILL_NAME_PATTERN.fullmatch(name) or len(name) > 64:
        raise ValueError(f"SKILL.md has an invalid name: {path}")
    if not isinstance(description, str) or not description.strip():
        raise ValueError(f"SKILL.md must have a non-empty description: {path}")
    return parsed


def _mime_type(path: Path) -> str:
    """Return the explicit MIME type for a published skill file."""
    try:
        return _MIME_TYPES[path.suffix.lower()]
    except KeyError as exc:
        raise ValueError(f"Unsupported published skill file type: {path}") from exc


def _resource(uri: str, name: str, mime_type: str, content: bytes) -> Resource:
    """Build a resource whose served content matches the indexed bytes."""
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return BinaryResource(uri=uri, name=name, mime_type=mime_type, data=content)
    return TextResource(uri=uri, name=name, mime_type=mime_type, text=text)


def _uri_for(relative_path: str) -> str:
    """Return the canonical URI for a skill-relative POSIX path."""
    return f"{SKILL_ROOT_URI}/{relative_path}"


def _relative_path_for_uri(uri: str) -> str:
    """Validate a skill URI and return its canonical relative path."""
    try:
        parsed = urlsplit(uri)
    except ValueError as exc:
        raise _invalid_params(f"Invalid skill URI: {uri}") from exc
    decoded_path = unquote(parsed.path)
    if (
        parsed.scheme == "skill"
        and parsed.netloc == "slcli"
        and not parsed.query
        and not parsed.fragment
        and decoded_path == ""
    ):
        return ""
    if (
        parsed.scheme != "skill"
        or parsed.netloc != "slcli"
        or parsed.query
        or parsed.fragment
        or "\\" in decoded_path
        or "\x00" in decoded_path
        or any(part in {"", ".", ".."} for part in decoded_path.lstrip("/").split("/"))
        or not decoded_path.startswith("/")
    ):
        raise _invalid_params(f"Invalid skill URI: {uri}")
    relative_path = decoded_path.lstrip("/")
    canonical = _uri_for(relative_path) if relative_path else SKILL_ROOT_URI
    if uri != canonical:
        raise _invalid_params(f"Invalid skill URI: {uri}")
    return relative_path


def build_skill_catalog(root: Path) -> SkillCatalog:
    """Build and fully validate the static catalog for the bundled skill."""
    paths = _published_paths(root)
    if len(paths) > MAX_RESOURCES_PER_SKILL:
        raise ValueError("Bundled slcli skill exceeds the resource limit")

    contents = {path: path.read_bytes() for path in paths}
    skill_content = contents[root / "SKILL.md"]
    frontmatter = _frontmatter(skill_content, root / "SKILL.md")
    if frontmatter["name"] != root.name:
        raise ValueError("SKILL.md name must match its skill directory")

    total_size = sum(len(content) for content in contents.values())
    if total_size > MAX_SKILL_SIZE:
        raise ValueError("Bundled slcli skill exceeds the total size limit")

    files: Dict[str, SkillFile] = {}
    for path, content in contents.items():
        relative_path = path.relative_to(root).as_posix()
        uri = _uri_for(relative_path)
        mime_type = _mime_type(path)
        manifest = SkillResourceManifest(
            uri=uri,
            digest=f"sha256:{hashlib.sha256(content).hexdigest()}",
            size=len(content),
        )
        files[relative_path] = SkillFile(
            relative_path=relative_path,
            uri=uri,
            content=content,
            mime_type=mime_type,
            resource=_resource(uri, path.name, mime_type, content),
            manifest=manifest,
        )

    directories: Dict[str, List[MCPResource]] = {SKILL_ROOT_URI: []}
    for relative_path in files:
        parts = relative_path.split("/")
        for index in range(1, len(parts)):
            directory_path = "/".join(parts[:index])
            directories.setdefault(_uri_for(directory_path), [])

    for directory_uri in list(directories):
        relative_directory = _relative_path_for_uri(directory_uri)
        children: Dict[str, MCPResource] = {}
        for relative_path, file in files.items():
            path = Path(relative_path)
            parent = (
                SKILL_ROOT_URI if path.parent == Path(".") else _uri_for(path.parent.as_posix())
            )
            if parent == directory_uri:
                children[path.name] = MCPResource(
                    uri=file.uri, name=path.name, mime_type=file.mime_type
                )
            elif relative_directory and relative_path.startswith(f"{relative_directory}/"):
                child_name = relative_path[len(relative_directory) + 1 :].split("/", 1)[0]
                child_path = f"{relative_directory}/{child_name}"
                children.setdefault(
                    child_name,
                    MCPResource(
                        uri=_uri_for(child_path), name=child_name, mime_type=DIRECTORY_MIME_TYPE
                    ),
                )
            elif not relative_directory and "/" in relative_path:
                child_name = relative_path.split("/", 1)[0]
                children.setdefault(
                    child_name,
                    MCPResource(
                        uri=_uri_for(child_name), name=child_name, mime_type=DIRECTORY_MIME_TYPE
                    ),
                )
        directories[directory_uri] = list(children.values())
        directories[directory_uri].sort(key=lambda resource: resource.name or "")

    manifests = [files[path].manifest for path in sorted(files)]
    entry = SkillEntry(uri=SKILL_URI, frontmatter=frontmatter, resources=manifests)
    return SkillCatalog(
        entry=entry,
        files=files,
        directories={key: tuple(value) for key, value in directories.items()},
    )


class SlcliSkillsExtension(Extension):
    """Serve the packaged slcli Agent Skill through the MCP Skills extension."""

    identifier = SKILLS_EXTENSION_IDENTIFIER

    def __init__(self, root: Optional[Path] = None) -> None:
        """Build and validate the static catalog from the bundled skill root."""
        self.catalog = build_skill_catalog(root or _find_skill_root())

    def settings(self) -> Dict[str, Any]:
        """Advertise optional directory reads."""
        return {"directoryRead": True}

    def resources(self) -> List[ResourceBinding]:
        """Contribute every published skill file as a normal MCP resource."""
        return self.catalog.resources()

    def methods(self) -> List[MethodBinding]:
        """Return the Skills extension request handlers."""
        return [
            MethodBinding("skills/list", ListSkillsParams, _modern_only(self._list_skills)),
            MethodBinding("skills/get", GetSkillParams, _modern_only(self._get_skill)),
            MethodBinding(
                "resources/directory/read", ReadDirectoryParams, _modern_only(self._read_directory)
            ),
        ]

    async def _list_skills(
        self, _: ServerRequestContext[Any, Any], params: ListSkillsParams
    ) -> ListSkillsResult:
        """Return the complete static skill catalog."""
        if params.cursor is not None:
            raise _invalid_params("The static slcli skill catalog does not support pagination")
        return ListSkillsResult(skills=[self.catalog.entry])

    async def _get_skill(
        self, _: ServerRequestContext[Any, Any], params: GetSkillParams
    ) -> GetSkillResult:
        """Return the catalog entry for the requested skill URI."""
        if params.uri != SKILL_URI:
            raise _invalid_params(f"No skill is served at {params.uri}")
        return GetSkillResult(skill=self.catalog.entry)

    async def _read_directory(
        self, _: ServerRequestContext[Any, Any], params: ReadDirectoryParams
    ) -> ReadDirectoryResult:
        """Return direct children of a published skill directory."""
        if params.cursor is not None:
            raise _invalid_params("The static slcli skill directories do not support pagination")
        return ReadDirectoryResult(resources=list(self.catalog.directory_children(params.uri)))
