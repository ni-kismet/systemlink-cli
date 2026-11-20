"""Pytest wiring: put fake SystemLink servers behind the migration E2E profiles.

Each side of a migration has its own mode, so a side can be replayed while the
other talks to a real server:

==============================  ==========  =====================================
Variable                        Default     Values
==============================  ==========  =====================================
``SLCLI_E2E_SOURCE_MODE``       ``replay``  ``live``, ``record``, or ``replay``
``SLCLI_E2E_DESTINATION_MODE``  ``live``    ``live``, ``record``, or ``replay``
==============================  ==========  =====================================

* ``live``: tests use the server named by the side's ``SLCLI_E2E_*_PROFILE``.
* ``record``: tests use a local fake that forwards to that server and writes
  every exchange to ``tests/e2e/tapes/<side>/<module>.yaml``.
* ``replay``: tests use a local fake that answers from that tape. No server,
  profile, or credential is needed.
"""

import json
import os
import tempfile
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Generator, Optional

import pytest

from slcli.migration import state
from tests.replay.server import Deck, FakeServer, Upstream

TAPES_DIR = Path(__file__).resolve().parent.parent / "e2e" / "tapes"
MODES = ("live", "record", "replay")


@dataclass(frozen=True)
class Side:
    """One server of a migration and how tests reach it."""

    profile_env: str
    mode_env: str
    default_mode: str
    platform: str

    def mode(self) -> str:
        """Return the configured mode."""
        mode = os.getenv(self.mode_env, "").strip().lower() or self.default_mode
        if mode not in MODES:
            raise pytest.UsageError(f"{self.mode_env} must be one of {', '.join(MODES)}")
        return mode


SIDES: Dict[str, Side] = {
    "source": Side("SLCLI_E2E_SOURCE_PROFILE", "SLCLI_E2E_SOURCE_MODE", "replay", "SLS"),
    "destination": Side(
        "SLCLI_E2E_DESTINATION_PROFILE", "SLCLI_E2E_DESTINATION_MODE", "live", "SLE"
    ),
}


@dataclass
class FakedSide:
    """A side served by a local fake, and the real server it records from."""

    fake: FakeServer
    upstream: Optional[Upstream]


@dataclass
class Fakes:
    """Fakes for the sides that are not live, and the config that points at them."""

    sides: Dict[str, FakedSide]
    config: Path


def _upstream(side: Side) -> Upstream:
    """Resolve the real server to record from, before profiles are redirected."""
    # Imported lazily: replay must not depend on profiles or credentials.
    from slcli.migration.connection import resolve_migration_connection
    from slcli.ssl_trust import inject_os_trust

    profile = os.getenv(side.profile_env)
    if not profile:
        raise pytest.UsageError(f"Recording needs {side.profile_env}")
    inject_os_trust()
    connection = resolve_migration_connection(profile)
    return Upstream(connection.base_url, connection.create_session())


def _live_profiles() -> Dict[str, object]:
    """Copy the real profiles that live sides use, keeping their credential IDs."""
    from slcli.profiles import ProfileConfig

    real = ProfileConfig.load().profiles
    names = [os.getenv(side.profile_env) for side in SIDES.values() if side.mode() == "live"]
    return {name: real[name].to_dict() for name in names if name and name in real}


@pytest.fixture(scope="session")
def replay_fakes() -> Generator[Fakes, None, None]:
    """Start a fake for each side that is not live, and write profiles for them."""
    sides = {
        name: FakedSide(FakeServer().start(), _upstream(side) if mode == "record" else None)
        for name, side in SIDES.items()
        if (mode := side.mode()) != "live"
    }
    profiles = _live_profiles()
    for name, faked in sides.items():
        profiles[f"replay-{name}"] = {
            "server": faked.fake.base_url,
            "api-key": "replay",
            "credential-store": "file",
            "platform": SIDES[name].platform,
        }
    with tempfile.TemporaryDirectory(prefix="slcli-replay-") as directory:
        config = Path(directory) / "config.json"
        config.write_text(json.dumps({"profiles": profiles}), encoding="utf-8")
        try:
            yield Fakes(sides, config)
        finally:
            for faked in sides.values():
                faked.fake.stop()


@pytest.fixture(scope="module", autouse=True)
def replay_decks(request: pytest.FixtureRequest) -> Generator[Dict[str, Deck], None, None]:
    """Point a migration module's profiles at the fakes, with that module's tapes.

    Other E2E modules configure their own servers and are left alone.
    """
    if request.node.get_closest_marker("e2e_migration") is None or all(
        side.mode() == "live" for side in SIDES.values()
    ):
        yield {}
        return
    fakes: Fakes = request.getfixturevalue("replay_fakes")
    module = request.module.__name__.rsplit(".", 1)[-1]
    decks = {
        name: Deck(TAPES_DIR / name / f"{module}.yaml", faked.upstream)
        for name, faked in fakes.sides.items()
    }
    failures_before = request.session.testsfailed
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("SLCLI_CONFIG", str(fakes.config))
        for name, deck in decks.items():
            patch.setenv(SIDES[name].profile_env, f"replay-{name}")
            fakes.sides[name].fake.deck = deck
        try:
            yield decks
        finally:
            for faked in fakes.sides.values():
                faked.fake.deck = None
    for deck in decks.values():
        if request.session.testsfailed == failures_before:
            deck.save()
        elif deck.recording:
            warnings.warn(f"Kept the previous {deck.path}: a test failed while recording.")


@pytest.fixture(autouse=True)
def replay_misses(replay_decks: Dict[str, Deck]) -> Generator[None, None, None]:
    """Fail a test that sent a request with no recorded counterpart."""
    yield
    misses = [f"[{name}] {miss}" for name, deck in replay_decks.items() for miss in deck.misses]
    for deck in replay_decks.values():
        deck.misses.clear()
    if misses:
        pytest.fail("Replay misses:\n" + "\n".join(misses), pytrace=False)


@pytest.fixture(scope="module", autouse=True)
def recorded_migration_ids(replay_decks: Dict[str, Deck]) -> Generator[None, None, None]:
    """Record migration IDs on the destination tape, and reuse them on replay.

    Migration writes its ID to the destination. A live destination needs no tape,
    so it gets fresh IDs.
    """
    deck = replay_decks.get("destination")
    if deck is None:
        yield
        return
    generate = state.new_migration_id
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(state, "new_migration_id", lambda: deck.generated("migrationId", generate))
        yield
