"""Unit test configuration - runs before any test collection or imports.

Forces the keyring null backend to prevent macOS Keychain access on CI runners.
Without this, macOS GitHub Actions runners hang for minutes per keyring call
because the Keychain is locked and no user session exists.
"""

import keyring
from keyring.backends.null import Keyring as NullKeyring

# Force the null backend BEFORE any test or doctest-module collection
# triggers a real keyring call. This is critical for macOS CI where
# the default macOS Keychain backend blocks on a locked keychain.
keyring.set_keyring(NullKeyring())
