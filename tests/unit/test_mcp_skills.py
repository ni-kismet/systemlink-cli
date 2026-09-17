"""Unit tests for the slcli MCP Skills extension."""

import asyncio
import base64
import hashlib
from pathlib import Path
from typing import Any, Dict, cast

import pytest
from mcp import Client
from mcp.server.context import ServerRequestContext
from mcp.shared.exceptions import MCPError
from mcp.types import ReadResourceResult, Request

from slcli.mcp_skills import (
    SKILL_ROOT_URI,
    SKILL_URI,
    SKILLS_CACHE_SCOPE,
    SKILLS_CACHE_TTL_MS,
    SKILLS_EXTENSION_IDENTIFIER,
    SKILLS_PROTOCOL_VERSION,
    GetSkillParams,
    ListSkillsParams,
    ListSkillsResult,
    ReadDirectoryParams,
    SlcliSkillsExtension,
    _find_skill_root,
    build_skill_catalog,
)


def test_catalog_matches_publish_policy() -> None:
    """The static catalog contains exactly the approved bundled skill files."""
    catalog = build_skill_catalog(_find_skill_root())

    assert len(catalog.files) == 31
    normalized_size = sum(
        len(file.content.replace(b"\r\n", b"\n")) for file in catalog.files.values()
    )
    assert normalized_size == 347451
    assert catalog.entry.uri == SKILL_URI
    assert catalog.entry.frontmatter["name"] == "slcli"
    assert catalog.entry.frontmatter["description"]
    assert len(catalog.entry.resources) == 31
    assert all("evals/" not in path for path in catalog.files)
    assert all("__pycache__" not in path and not path.endswith(".pyc") for path in catalog.files)

    for relative_path, file in catalog.files.items():
        assert file.manifest.uri == file.uri
        assert file.manifest.digest == f"sha256:{hashlib.sha256(file.content).hexdigest()}"
        assert file.manifest.size == len(file.content)


def test_catalog_directories_contain_sorted_unique_direct_children() -> None:
    """Directory reads expose files and nested directories exactly once."""
    catalog = build_skill_catalog(_find_skill_root())

    root_children = catalog.directory_children(SKILL_ROOT_URI)
    assert [child.name for child in root_children] == ["references", "scripts", "slcli"]
    assert len({child.uri for child in root_children}) == len(root_children)
    skill_child = next(child for child in root_children if child.uri == SKILL_URI)
    assert skill_child.name == catalog.entry.frontmatter["name"]
    assert skill_child.description == catalog.entry.frontmatter["description"]

    reference_children = catalog.directory_children("skill://slcli/references")
    assert [child.name for child in reference_children] == sorted(
        child.name for child in reference_children
    )
    assert any(
        child.uri == "skill://slcli/references/job-debugging" for child in reference_children
    )
    assert any(child.uri == "skill://slcli/references/commands.md" for child in reference_children)

    nested_children = catalog.directory_children("skill://slcli/references/job-debugging")
    assert [child.name for child in nested_children] == ["overview.md"]
    assert nested_children[0].mime_type == "text/markdown"


@pytest.mark.parametrize(
    "uri",
    [
        "skill://slcli/unknown.md",
        "skill://slcli/SKILL.md/",
        "skill://slcli/references/../SKILL.md",
        "skill://slcli/references/%2e%2e/SKILL.md",
        "skill://slcli/references\\commands.md",
        "skill://slcli/SKILL.md?query=1",
        "skill://slcli/SKILL.md#fragment",
        "SKILL://slcli",
        "skill://slcli?",
        "skill://slcli#",
        "skill://[invalid/SKILL.md",
    ],
)
def test_catalog_rejects_unknown_or_noncanonical_uris(uri: str) -> None:
    """Only indexed canonical virtual URIs can be resolved."""
    catalog = build_skill_catalog(_find_skill_root())

    with pytest.raises(MCPError):
        catalog.validate_file_uri(uri)
    with pytest.raises(MCPError):
        catalog.directory_children(uri)


def test_catalog_rejects_file_as_directory() -> None:
    """A published file cannot be used as a directory resource."""
    catalog = build_skill_catalog(_find_skill_root())

    with pytest.raises(MCPError, match="not a directory"):
        catalog.directory_children(SKILL_URI)


def test_extension_advertises_skills_and_cache_settings() -> None:
    """The extension exposes the expected identifier and optional directory support."""
    extension = SlcliSkillsExtension()

    assert extension.identifier == SKILLS_EXTENSION_IDENTIFIER
    assert extension.settings() == {"directoryRead": True}
    assert {binding.method for binding in extension.methods()} == {
        "skills/list",
        "skills/get",
        "resources/directory/read",
    }
    assert all(binding.protocol_versions is None for binding in extension.methods())


def test_extension_handlers_return_complete_cacheable_results() -> None:
    """Skills handlers return complete static results with cache metadata."""
    extension = SlcliSkillsExtension()
    context = cast(ServerRequestContext[Any, Any], None)

    async def call_handlers() -> Dict[str, Any]:
        listed = await extension._list_skills(context, ListSkillsParams())
        fetched = await extension._get_skill(context, GetSkillParams(uri=SKILL_URI))
        directory = await extension._read_directory(
            context, ReadDirectoryParams(uri=SKILL_ROOT_URI)
        )
        return {
            "list": listed.model_dump(by_alias=True),
            "get": fetched.model_dump(by_alias=True),
            "directory": directory.model_dump(by_alias=True),
        }

    results = asyncio.run(call_handlers())
    assert results["list"]["resultType"] == "complete"
    assert results["list"]["ttlMs"] == SKILLS_CACHE_TTL_MS
    assert results["list"]["cacheScope"] == SKILLS_CACHE_SCOPE
    assert results["get"]["skill"] == results["list"]["skills"][0]
    assert results["directory"]["resultType"] == "complete"


def test_server_lists_and_reads_all_skill_resources() -> None:
    """The MCP server serves exactly the catalog bytes through resources/read."""
    from slcli.mcp_server import server

    catalog = build_skill_catalog(_find_skill_root())

    async def read_skills() -> Dict[str, ReadResourceResult]:
        from mcp.client import advertise

        async with Client(
            server,
            mode=SKILLS_PROTOCOL_VERSION,
            extensions=[advertise(SKILLS_EXTENSION_IDENTIFIER)],
        ) as client:
            resources = await client.list_resources()
            assert {resource.uri for resource in resources.resources} == {
                file.uri for file in catalog.files.values()
            }
            skill_resource = next(
                resource for resource in resources.resources if resource.uri == SKILL_URI
            )
            assert skill_resource.name == catalog.entry.frontmatter["name"]
            assert skill_resource.description == catalog.entry.frontmatter["description"]
            return {
                relative_path: await client.read_resource(file.uri)
                for relative_path, file in catalog.files.items()
            }

    results = asyncio.run(read_skills())
    for relative_path, result in results.items():
        content = result.contents[0]
        text = getattr(content, "text", None)
        if text is not None:
            assert text.encode("utf-8") == catalog.files[relative_path].content
        else:
            blob = getattr(content, "blob", None)
            assert blob is not None
            assert base64.b64decode(blob) == catalog.files[relative_path].content


def test_modern_custom_request_requires_client_opt_in() -> None:
    """Skills methods require client opt-in on the target revision."""
    from mcp import Client
    from mcp.client import advertise

    async def call_modern() -> ListSkillsResult:
        async with Client(
            server,
            mode=SKILLS_PROTOCOL_VERSION,
            extensions=[advertise(SKILLS_EXTENSION_IDENTIFIER)],
        ) as client:
            request = Request(method="skills/list", params=ListSkillsParams())
            return await client.session.send_request(request, ListSkillsResult)

    async def call_without_opt_in() -> None:
        async with Client(server, mode=SKILLS_PROTOCOL_VERSION, raise_exceptions=True) as client:
            request = Request(method="skills/list", params=ListSkillsParams())
            await client.session.send_request(request, ListSkillsResult)

    async def call_legacy() -> None:
        async with Client(server, mode="legacy", raise_exceptions=True) as client:
            request = Request(method="skills/list", params=ListSkillsParams())
            await client.session.send_request(request, ListSkillsResult)

    from slcli.mcp_server import server

    result = asyncio.run(call_modern())
    assert result.skills[0].uri == SKILL_URI

    with pytest.raises(ExceptionGroup) as error:
        asyncio.run(call_without_opt_in())

    def contains_error_code(exception: BaseException, code: int) -> bool:
        if isinstance(exception, MCPError):
            return exception.code == code
        if isinstance(exception, BaseExceptionGroup):
            return any(contains_error_code(child, code) for child in exception.exceptions)
        return False

    assert contains_error_code(error.value, -32021)

    with pytest.raises(ExceptionGroup) as error:
        asyncio.run(call_legacy())

    def contains_method_not_found(exception: BaseException) -> bool:
        if isinstance(exception, MCPError):
            return exception.code == -32601 and "Method not found" in str(exception)
        if isinstance(exception, BaseExceptionGroup):
            return any(contains_method_not_found(child) for child in exception.exceptions)
        return False

    assert contains_method_not_found(error.value)


def test_catalog_fails_startup_for_invalid_skill(tmp_path: Path) -> None:
    """Malformed bundled content fails catalog construction instead of being hidden."""
    skill_root = tmp_path / "slcli"
    skill_root.mkdir()
    (skill_root / "SKILL.md").write_text("# missing frontmatter", encoding="utf-8")

    with pytest.raises(ValueError, match="frontmatter"):
        build_skill_catalog(skill_root)


def test_catalog_rejects_symlinked_published_content(tmp_path: Path) -> None:
    """Published files cannot escape the skill root through symlinks."""
    skill_root = tmp_path / "slcli"
    references = skill_root / "references"
    references.mkdir(parents=True)
    (skill_root / "SKILL.md").write_text(
        "---\nname: slcli\ndescription: test\n---\n", encoding="utf-8"
    )
    target = tmp_path / "outside.md"
    target.write_text("outside", encoding="utf-8")
    (references / "outside.md").symlink_to(target)

    with pytest.raises(ValueError, match="symlink"):
        build_skill_catalog(skill_root)


def test_catalog_rejects_dangling_published_directory_symlink(tmp_path: Path) -> None:
    """Dangling published directories fail catalog construction."""
    skill_root = tmp_path / "slcli"
    skill_root.mkdir()
    (skill_root / "SKILL.md").write_text(
        "---\nname: slcli\ndescription: test\n---\n", encoding="utf-8"
    )
    (skill_root / "references").symlink_to(tmp_path / "missing")

    with pytest.raises(ValueError, match="real directory"):
        build_skill_catalog(skill_root)
