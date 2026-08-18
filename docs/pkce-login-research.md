# PKCE Login Research and Prototype

Status: opt-in PKCE login implemented. The `azemr-pre` public client and scope
contract are confirmed from first-party source and runtime metadata; live
resource validation still requires the user's SSO session and a deployed API
gateway. The implementation deliberately uses the in-process native-app path
and does not depend on Desktop Login Service.

## Recommendation

The implementation uses an in-process native-app client. `slcli login --auth
pkce` opens the configured Web UI Token Service authorization route, receives
one loopback callback on `127.0.0.1:9876`, exchanges the code with PKCE `S256`,
and sends the returned access token directly to the configured API URL as an
`Authorization: Bearer <token>` header. The access and refresh tokens are stored
in the operating-system keyring; the API URL remains the target for service
probes and resource requests.

When the access token is near expiry, the CLI uses the stored refresh token to
request a new access token and replaces the rotated refresh token in the
keyring. If refresh is unavailable or rejected, rerun the PKCE login.

The Desktop Login Service is intentionally not a CLI dependency. Existing
API-key login remains the default and is selected explicitly with
`--auth api-key` when needed.

The prototype does not guess a public client ID or rely on an undocumented
capability endpoint. Supply the registered value with `--client-id`; for
`azemr-pre`, use `stratus-client-auth`. Scopes default to
`openid profile email offline_access` and may be repeated with `--scope`.

## Implemented Flow

- `slcli login --auth pkce` in [slcli/main.py](../slcli/main.py) collects the
  API URL, Web UI URL, registered public client ID, and optional scopes. The
  existing `--auth api-key` path remains the default.
- [slcli/pkce.py](../slcli/pkce.py) opens the Web UI Token Service authorization
  route in the external browser, listens on the registered
  `127.0.0.1:9876` loopback callback, validates `state`, exchanges the
  authorization code with PKCE `S256`, and returns the access token for direct
  bearer requests.
- Access and refresh credentials are stored in the operating-system keyring.
  Profile JSON stores only `auth-mode`, `pkce-client-id`, and `pkce-scopes` for
  PKCE profiles. Refresh uses the rotated refresh token and creates a fresh
  access token when the stored token expires.
- Runtime requests use `Authorization: Bearer <token>` for PKCE profiles and
  retain `x-ni-api-key` for API-key profiles.
- `slcli logout` removes profile-scoped PKCE credentials from the keyring.
- Focused coverage is in [tests/unit/test_pkce.py](../tests/unit/test_pkce.py)
  alongside the existing API-key login tests.

## First-Party Design Evidence

[Desktop-login-service.md](../Desktop-login-service.md) is the most specific
local design source available. It describes a separate service with these
responsibilities:

- `SystemLink:Url` and `SystemLink:OidcAuthorityUrl` are separate, so the API
  server and OIDC authority may be different origins.
- `Login` starts an authorization-code + PKCE flow in the user's default
  browser, receives a loopback redirect, exchanges the code, and caches identity
  and access tokens.
- Only the refresh token is persisted in an OS credential store, keyed by the
  OIDC `sub` claim. Access tokens remain in memory.
- `GetToken` refreshes near-expiry access tokens and serializes refreshes to
  handle refresh-token rotation.
- The POC client API is `Login`, `Logout`, `GetToken`, `GetIdentity`,
  `GetPolicies`, and `Health`. The documented Windows transport is a
  per-user Named Pipe discovered through
  `%LocalAppData%/NationalInstruments/DesktopLoginService/discovery.json`.
- The SystemLink policy request is documented as
  `GET <systemlink-instance>/niauth/v1/auth` with a bearer access token.
- The design explicitly leaves OIDC configuration auto-discovery open. Today it
  requires an authority URL and client ID; deriving both from only the
  SystemLink hostname would require a server-side endpoint and contract.

The authenticated Azure DevOps wiki page,
[Stratus desktop login support](https://dev.azure.com/ni/DevCentral/_wiki/wikis/Stratus/165478/Stratus-desktop-login-support),
specifies the following Stratus server-side POC contract:

- Stratus publishes a minimal OAuth 2.0 authorization-code flow with PKCE. The
  Web Server proxies access to a Token Service implemented with OpenIddict.
- The documented routes are `GET /nitoken/v1/authorize`,
  `POST /nitoken/v1/authorize`, `POST /nitoken/v1/token`,
  `POST /nitoken/v1/revoke`, `POST /nitoken/v1/revoke-all`, and the token
  redemption route.
- The authorization route honors `x-ni-api-key` to associate the token with a
  user. The wiki also says user authorization is managed through the normal
  Stratus UI login, so the exact way a browser-based CLI flow supplies or
  replaces that API-key association still needs confirmation.
- Access tokens are accepted as bearer tokens by the Web Server. The Desktop
  Login Service POC calls `GET /niauth/v1/auth` with the access token in an
  `Authorization: Bearer` header, and the CLI follows that direct bearer
  contract rather than adding a session-key exchange.
- The separate API hostname still depends on the API gateway deployment tracked
  by work item 4018441. Until that gateway is deployed, successful browser
  token acquisition does not imply that API resource probes will succeed.
- Access tokens last one day in the POC. Refresh tokens last one year, are
  single-use, and rotate: each refresh revokes the old refresh token and returns
  a new one.
- The page explicitly rejects having each desktop application integrate with an
  external identity provider as the long-term direction because provider
  configuration and behavioral differences would leak into every application.

The page does **not** document an RFC 8414 metadata endpoint, a capability
endpoint, public client ID, scopes, loopback redirect registration, token
response schema, or the exact browser authorization URL construction. Those
details still require confirmation from the SystemLink team or implementation
artifacts. The page is marked as a POC and says its architecture and selected
dependencies are not final.

## Confirmed azemr-pre Contract

Authenticated Azure DevOps source from the Skyline Token Service prototype
defines:

- `stratus-client-auth` as the desktop login client ID.
- A public client with the fixed redirect URI
  `http://127.0.0.1:9876/callback`.
- Authorization-code, refresh-token, token, revocation, and end-session
  permissions, with PKCE required.
- Client scopes `profile` and `email`; the server registers `profile`, `email`,
  and `offline_access` in addition to the standard `openid` scope.

The first-party Token Service test client requests
`openid profile email offline_access`. The deployed web host's RFC 8414
discovery document advertises the same four scopes and the authorization-code,
refresh-token, and `S256` PKCE capabilities. Non-interactive `prompt=none`
probes against `azemr-pre` accepted both the profile/email request and the
request including `offline_access` while using the existing browser SSO
session. No SSO credentials were entered during those probes.

The discovery document identifies the web host as the issuer and as the host
for the authorization and token endpoints. The separate API hostname returned
Cloudflare `502 Bad Gateway` during this investigation, so the final session
exchange and API service probe remain pending.

## Protocol Constraints

These are standards requirements, not SystemLink-specific assumptions:

- [RFC 7636](https://www.rfc-editor.org/rfc/rfc7636), sections 4.1-4.6:
  generate a fresh high-entropy `code_verifier`, send its `S256`
  `code_challenge` in the authorization request, and send the verifier only at
  the token endpoint. A 32-byte random value encoded base64url is the reference
  shape. Do not downgrade to `plain`.
- [RFC 8252](https://www.rfc-editor.org/rfc/rfc8252), sections 4-7 and 8.1:
  native applications should use the external browser, and desktop clients
  should use a loopback redirect such as
  `http://127.0.0.1:<ephemeral-port>/callback`. The listener should bind only
  to loopback, accept one callback, and close promptly.
- RFC 8252 section 8.9: generate a high-entropy `state` value and reject a
  callback whose state does not match the pending request.
- [RFC 8414](https://www.rfc-editor.org/rfc/rfc8414), sections 2-3:
  authorization-server metadata can advertise `authorization_endpoint`,
  `token_endpoint`, and `code_challenge_methods_supported` at a well-known URL.
  If metadata is used, validate that its `issuer` exactly matches the issuer
  used to construct the request. Validate endpoint origins before opening the
  browser.
- RFC 7636 section 5 says a PKCE-capable client does not need to know whether a
  server supports PKCE before sending the extension. Capability discovery is
  useful for selecting the flow and giving a clear fallback message, but it is
  not a reason to send a weaker request.

## Discovery Recommendation

The phrase "request the Web UI URL and detect PKCE" needs a concrete server
contract. A generic GET of an HTML Web UI is not a reliable or safe capability
probe, and parsing JavaScript bundles would couple the CLI to the UI build.

The authenticated wiki confirms the Token Service routes but does not define a
capability-discovery route. Use one of these explicit contracts, in this order
of preference:

1. The Web UI or API returns a documented JSON login-capabilities document that
  identifies whether the Token Service routes and PKCE are enabled and
  supplies the public client ID, scopes, token authentication method, and
  supported redirect mode.
2. The server exposes RFC 8414 metadata for the Token Service. The CLI retrieves
  it and checks for the authorization-code grant and `S256` support.
3. The CLI uses the documented `/nitoken/v1/authorize` and
  `/nitoken/v1/token` routes based on a configured server capability/version,
  with the client ID, scopes, and redirect registration supplied out of band.

The CLI should not probe `/nitoken/v1/authorize` by blindly opening a browser or
guessing query parameters. A failed authorization request is user-visible and
could create a confusing partial login. The current prototype uses the
explicit `--auth pkce` opt-in and retains API-key login as the default.

The exact URL, status code, content type, JSON fields, client ID, scopes, and
relationship among API URL, Web UI URL, and OIDC authority are open questions.
Do not invent a path such as `/client-info` or assume all three URLs share an
origin.

## Validation Flow

For the current prototype, validation against a compatible Stratus deployment
is:

1. Obtain a public client registration from the SystemLink service owner. The
   registration must allow the loopback redirect URI generated by the CLI and
   the requested scopes.
2. Ensure local port `9876` is available and run `slcli login --auth pkce` with
  separate API and Web UI URLs, the confirmed client ID, and the default
  scopes:

  ```bash
  slcli login --auth pkce \
     --profile azemr-pre \
     --url https://azemr-pre-api.lifecyclesolutions.ni.com \
     --web-url https://azemr-pre.lifecyclesolutions.ni.com \
     --client-id stratus-client-auth
  ```

  The command opens the browser. Complete SSO there; do not send credentials
  through the terminal or CLI arguments.
3. Complete the normal Stratus login in the browser and confirm that the CLI
   receives a callback, exchanges the code, and successfully probes the API
   URL with an `Authorization: Bearer` header once the API gateway is deployed.
4. Run a normal resource command, then repeat it after the access-token
   lifetime is reached to exercise refresh-token rotation. Use `slcli logout`
   to verify keyring cleanup.

The repository does not contain usable test credentials, so live `azemr-pre`
validation remains pending. The CLI does not silently fall back from an
explicitly requested PKCE login to an API key.

## Remaining Contract Work

- Confirm that the API hostname is restored and accepts bearer access tokens for
  service probes and resource requests.
- Decide whether a later production implementation needs inter-process
  serialization around single-use refresh-token rotation. The CLI does
  not currently coordinate concurrent refreshes across CLI processes.