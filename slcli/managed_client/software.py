"""Resolve mock software transactions with libsolv without executing installers."""

from __future__ import annotations

import importlib
import gzip
import io
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit

import requests

from .models import ManagedClientError


class SoftwareResolutionError(ManagedClientError):
    """A package catalog or dependency request cannot be safely resolved."""


@dataclass(frozen=True)
class CatalogPackage:
    """One available package version and its feed control metadata."""

    name: str
    version: str
    architecture: str = "all"
    depends: str = ""
    recommends: str = ""
    provides: str = ""
    conflicts: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)


def load_feed_packages(repositories: Mapping[str, Mapping[str, Any]]) -> list[CatalogPackage]:
    """Load package control metadata from enabled feed URLs, never package archives.

    Args:
        repositories: Mock feed records with URI and enabled state.

    Returns:
        Available package versions with parsed control metadata.

    Raises:
        SoftwareResolutionError: A feed cannot be fetched or parsed within the limits.
    """
    try:
        parser = importlib.import_module("debian.deb822").Packages
    except ImportError as error:
        raise SoftwareResolutionError("Feed parsing requires python-debian.") from error
    catalog: list[CatalogPackage] = []
    seen: set[str] = set()
    for repository in repositories.values():
        if not repository.get("enabled", True):
            continue
        uri = repository["uri"].rstrip("/")
        if uri in seen:
            continue
        seen.add(uri)
        parsed = urlsplit(uri)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise SoftwareResolutionError("Feeds require HTTP(S) URLs without embedded credentials.")
        try:
            with requests.get(f"{uri}/Packages.gz", stream=True, timeout=(5, 15)) as response:
                if response.status_code == 404:
                    with requests.get(f"{uri}/Packages", stream=True, timeout=(5, 15)) as plain:
                        plain.raise_for_status()
                        content = _read_catalog_response(plain)
                else:
                    response.raise_for_status()
                    compressed = _read_catalog_response(response)
                    with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as archive:
                        content = archive.read(64 * 1024 * 1024 + 1)
                if len(content) > 64 * 1024 * 1024:
                    raise SoftwareResolutionError("Feed metadata exceeds the 64 MiB decoded limit.")
            for paragraph in parser.iter_paragraphs(io.StringIO(content.decode("utf-8")), use_apt_pkg=False):
                name, version = paragraph.get("Package"), paragraph.get("Version")
                if not name or not version:
                    raise SoftwareResolutionError("Feed package records require Package and Version.")
                metadata = {
                    key.lower(): str(paragraph[source])
                    for key, source in (
                        ("displayname", "DisplayName"), ("displayversion", "DisplayVersion"),
                        ("description", "Description"), ("group", "Group"), ("packager", "Packager"),
                        ("priority", "Priority"), ("releasenotes", "ReleaseNotes"), ("url", "Homepage"),
                        ("uservisible", "UserVisible"), ("wininsttype", "WinInstType"),
                        ("storeproduct", "StoreProduct"), ("size", "Size"),
                    )
                    if source in paragraph
                }
                catalog.append(CatalogPackage(
                    name=str(name), version=str(version), architecture=str(paragraph.get("Architecture", "all")),
                    depends=str(paragraph.get("Depends", "")), recommends=str(paragraph.get("Recommends", "")),
                    provides=str(paragraph.get("Provides", "")), conflicts=str(paragraph.get("Conflicts", "")),
                    metadata=metadata,
                ))
        except (requests.RequestException, OSError, EOFError, UnicodeError) as error:
            raise SoftwareResolutionError("Unable to load enabled feed package metadata.") from error
    return catalog


def _read_catalog_response(response: requests.Response) -> bytes:
    content = bytearray()
    for chunk in response.iter_content(chunk_size=65536):
        content.extend(chunk)
        if len(content) > 16 * 1024 * 1024:
            raise SoftwareResolutionError("Feed metadata exceeds the 16 MiB download limit.")
    return bytes(content)


def _solver_architecture(architecture: str) -> str:
    return {
        "windows_all": "all", "windows_x64": "amd64", "x64": "amd64", "AMD64": "amd64",
    }.get(architecture, architecture)


def _add_relations(pool: Any, package: Any, text: str, method: str) -> None:
    if not text:
        return
    try:
        relations = importlib.import_module("debian.deb822").PkgRelation.parse_relations(text)
    except ImportError as error:
        raise SoftwareResolutionError("Dependency solving requires python-debian.") from error
    solv = importlib.import_module("solv")
    operators = {
        "=": solv.REL_EQ,
        ">=": solv.REL_GT | solv.REL_EQ,
        "<=": solv.REL_LT | solv.REL_EQ,
        ">>": solv.REL_GT,
        "<<": solv.REL_LT,
    }
    for alternatives in relations:
        dependency = None
        for relation in alternatives:
            if relation.get("arch") or relation.get("restrictions"):
                raise SoftwareResolutionError("Architecture or build-profile dependency restrictions are unsupported.")
            candidate = pool.Dep(relation["name"])
            version = relation.get("version")
            if version:
                operator, required = version
                if operator not in operators:
                    raise SoftwareResolutionError("Unsupported dependency version operator.")
                candidate = candidate.Rel(operators[operator], pool.Dep(required).id)
            dependency = candidate if dependency is None else dependency.Rel(solv.REL_OR, candidate.id)
        if dependency is not None:
            getattr(package, method)(dependency)


def solve_package_install(
    requested: Mapping[str, str],
    installed: Mapping[str, Mapping[str, Any]],
    catalog: Sequence[CatalogPackage],
    install_recommends: bool = True,
) -> dict[str, dict[str, Any]]:
    """Resolve requested versions and dependency upgrades against mock inventory.

    Args:
        requested: Package names mapped to exact versions or ``latest``.
        installed: Current simulated installed package records.
        catalog: Available versions from enabled feeds.
        install_recommends: Whether to include recommended dependencies.

    Returns:
        The complete proposed inventory; no host or state changes are performed.

    Raises:
        SoftwareResolutionError: Bindings are missing or the request is unsatisfiable.
    """
    try:
        solv = importlib.import_module("solv")
    except ImportError as error:
        raise SoftwareResolutionError("Dependency solving requires the native solv bindings.") from error
    pool = solv.Pool()
    if pool.setdisttype(pool.DISTTYPE_DEB) == -1:
        raise SoftwareResolutionError("libsolv must support Debian version comparison.")
    pool.setarch("amd64")
    installed_repo = pool.add_repo("mock-installed")
    available_repo = pool.add_repo("mock-feeds")
    pool.installed = installed_repo
    records: dict[int, CatalogPackage] = {}
    known_packages = {
        (record.name, record.version): record for record in catalog
        if _solver_architecture(record.architecture) in {"all", "amd64"}
    }
    inventory: dict[str, dict[str, Any]] = {}
    for name, record in installed.items():
        known = known_packages.get((name, record["version"]))
        enriched = {**(known.metadata if known else {}), **record}
        if known:
            for key in ("depends", "recommends", "provides", "conflicts"):
                if key not in enriched and getattr(known, key):
                    enriched[key] = getattr(known, key)
        inventory[name] = enriched

    def add_package(repository: Any, record: CatalogPackage) -> None:
        package = repository.add_solvable()
        package.name = record.name
        package.evr = record.version
        package.arch = _solver_architecture(record.architecture)
        package.add_provides(pool.Dep(record.name).Rel(solv.REL_EQ, pool.Dep(record.version).id))
        for text, method in (
            (record.depends, "add_requires"),
            (record.recommends, "add_recommends"),
            (record.provides, "add_provides"),
            (record.conflicts, "add_conflicts"),
        ):
            _add_relations(pool, package, text, method)
        records[package.id] = record

    for name, record in inventory.items():
        add_package(installed_repo, CatalogPackage(
            name, record["version"], record["arch"],
            depends=record.get("depends", ""), recommends=record.get("recommends", ""),
            provides=record.get("provides", ""), conflicts=record.get("conflicts", ""), metadata=record,
        ))
    for record in catalog:
        add_package(available_repo, record)
    installed_repo.internalize()
    available_repo.internalize()
    pool.createwhatprovides()
    solver = pool.Solver()
    solver.set_flag(solv.Solver.SOLVER_FLAG_IGNORE_RECOMMENDED, not install_recommends)
    jobs = [pool.Job(solv.Job.SOLVER_VERIFY | solv.Job.SOLVER_SOLVABLE_ALL, 0)]
    for name, version in requested.items():
        dependency = pool.Dep(name)
        flags = solv.Job.SOLVER_INSTALL | solv.Job.SOLVER_FORCEBEST
        if version == "latest":
            flags |= solv.Job.SOLVER_SOLVABLE_NAME
        else:
            dependency = dependency.Rel(solv.REL_EQ, pool.Dep(version).id)
            flags |= solv.Job.SOLVER_SOLVABLE_PROVIDES
        jobs.append(pool.Job(flags, dependency.id))
    problems = solver.solve(jobs)
    if problems:
        raise SoftwareResolutionError("Unsatisfiable mock software request: " + "; ".join(str(problem) for problem in problems))
    for package in solver.transaction().newsolvables():
        record = records[package.id]
        inventory[record.name] = {
            **record.metadata, "version": record.version, "arch": record.architecture,
            **{key: value for key, value in (
                ("depends", record.depends), ("recommends", record.recommends),
                ("provides", record.provides), ("conflicts", record.conflicts),
            ) if value},
        }
    return inventory