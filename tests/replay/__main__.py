"""Serve a tape for ad hoc exploration: ``python -m tests.replay <tape.yaml>``.

Point ``curl`` or an ``slcli`` profile at the printed URL. Each recorded
response is served once.
"""

import argparse
import time
from pathlib import Path

from tests.replay.server import Deck, FakeServer


def main() -> None:
    """Serve one tape until interrupted, printing requests that miss."""
    parser = argparse.ArgumentParser(prog="python -m tests.replay")
    parser.add_argument("tape", type=Path)
    deck = Deck(parser.parse_args().tape)
    fake = FakeServer(deck).start()
    print(f"Serving {deck.path} at {fake.base_url}. Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
            for line in deck.misses:
                print(f"MISS {line}")
            deck.misses.clear()
    except KeyboardInterrupt:
        pass
    finally:
        fake.stop()


if __name__ == "__main__":
    main()
