[[_TOC_]]

# Problem statement

NI Applications Software teams have a growing need to implement IAM frameworks
to satisfy cybersecurity requirements in customer markets. The EU Cyber
Resilience Act
([EU 2024/2847](https://eur-lex.europa.eu/eli/reg/2024/2847/oj/eng)) and US
federal contract standards ([CMMC](https://dodcio.defense.gov/CMMC/About/),
[NIAP CC](https://www.niap-ccevs.org/)) require that applications employ
identity-based access controls for privileged operations. Currently, NI desktop
applications have no common mechanism for coordinating user identity or
enforcing authorization policies.

This document describes the **desktop login service**: a local service that acts
as a centralized identity broker for NI desktop applications, enabling single
sign-on across NI software using a SystemLink OIDC provider. The service is
responsible for managing OAuth/OIDC tokens on behalf of the user and providing
an API that applications use to perform login, logout, and policy retrieval
operations.

> **Naming note**: The desktop login service is the same component referred to
> as the "SystemLink Client (SL Client) daemon" and "SystemLink Client
> Configuration daemon" in the
> [desktop SSO research design](../Requirements/.staging/desktop-sso-research-design.md).
> The C# library surface through which applications call into this service is
> referred to as the "SL Client API" or "SL Client Application API" in that
> document.

> **POC status**: This HLD describes a proof of concept intended to validate the
> technical approach — in particular the OS credential store integration and
> PKCE OAuth flow — before full planning and productization. The initial
> implementation is a CLI application to enable rapid iteration. The graduation
> path to a Windows service is tracked as an open issue.

# Links to relevant work items and reference material

- [Desktop SSO research design](../Requirements/.staging/desktop-sso-research-design.md)
  — primary source for requirements and design justification
- [EU Cyber Resilience Act EU 2024/2847](https://eur-lex.europa.eu/eli/reg/2024/2847/oj/eng)
- [Cybersecurity Maturity Model Certification (CMMC)](https://dodcio.defense.gov/CMMC/About/)
- [PKCE OAuth 2.0 specification](https://oauth.net/2/pkce/)

# Implementation and design

## Architecture overview

The desktop login service is an ASP.NET Core application
(`Microsoft.NET.Sdk.Web`) that exposes its API primarily over a Named Pipe
transport using a JSON request/response protocol. It follows the architectural
patterns established by the MeasurementLink Discovery Service, which serves as
the reference implementation for the service host, DI configuration, and Serilog
setup. A gRPC transport over Kestrel is also supported but disabled by default.

**POC implementation path:**

1. **CLI application** (current scope) — the service starts as a .NET CLI tool
   that is launched from the command line. This enables rapid development and
   debugging without the overhead of Windows service registration.
1. **User-session background process** (future) — once the core design is
   validated, the CLI is promoted to a user-session startup application that
   auto-starts at login via Task Scheduler ("at logon" trigger), running in the
   user's interactive session under the user's identity. See the Process model
   row in [Service runtime](#service-runtime) and the Production process model
   graduation open issue in [Open issues](#open-issues).

## Service runtime

| Aspect            | Value                                                                                                                                                                                                                                 |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| SDK               | `Microsoft.NET.Sdk.Web`                                                                                                                                                                                                               |
| IPC transports    | Named Pipe (Windows) — preferred (POC); gRPC over Kestrel (HTTP/2) — supported; UDS (Linux) — designed but not implemented in POC                                                                                                     |
| Logging           | Serilog → `%ProgramData%\National Instruments\Desktop Login Service\Logs\`                                                                                                                                                            |
| Health endpoints  | HTTP `/livez`, `/readyz`, `/healthz` at the Kestrel port when gRPC transport is enabled; Named Pipe `Health` gRPC method always available                                                                                             |
| Service discovery | POC: writes transport address to `%LocalAppData%\NationalInstruments\DesktopLoginService\discovery.json` on startup; file is ACL'd to the current user's SID. Production: replaced by MeasurementLink Discovery Service registration. |
| Packaging (POC)   | .NET CLI tool (`PackAsTool = true`)                                                                                                                                                                                                   |
| Packaging (prod)  | NIPKG or Linux distribution packages, as appropriate.                                                                                                                                                                                 |
| Process model     | User-session startup application; one instance per logged-in user; auto-started at login via Task Scheduler ("at logon" trigger); not a Windows SCM service                                                                           |

**`discovery.json` schema:**

```json
{
  "namedPipe": "NationalInstruments.DesktopLoginService.<SID>",
  "grpcHttp2Port": 0,
  "grpcHttp1Port": 0
}
```

`namedPipe` is omitted when Named Pipe is disabled. `grpcHttp2Port` and
`grpcHttp1Port` are `0` when gRPC is disabled. The client library reads this
file to determine which transport to use; it prefers `namedPipe` when present.

## Service configuration

The service reads configuration from `appsettings.json` located in the same
directory as the executable, following the standard ASP.NET Core configuration
convention. Service-specific settings live under the `DesktopLoginService`
section. When the gRPC transport is enabled, Kestrel port bindings are read from
the `NI.Measurements` section via `ConfigureKestrelForMeasurementServices`,
consistent with the Discovery Service pattern. Serilog is configured via the
`Serilog` section using
`logger.ReadFrom.Configuration(hostContext.Configuration)`.

**Configuration is read once at startup.** The service does not watch the file
for changes. Any edit to `appsettings.json` requires a service restart to take
effect. This is an intentional constraint: security-relevant settings (IPC
transport, approved callers, SystemLink connection) must not change while the
service is running without an explicit restart that re-validates the full
configuration.

**Interface.** The `DesktopLoginService` section is bound to an
`IServiceConfiguration` interface injected via DI. This keeps the configuration
model testable and decoupled from the JSON file format.

```csharp
public interface IServiceConfiguration
{
    TransportConfiguration Transport { get; }
    SystemLinkConfiguration SystemLink { get; }
    SecurityConfiguration Security { get; }
    LimitsConfiguration Limits { get; }
}

public record TransportConfiguration(
    bool NamedPipeEnabled,
    bool UdsEnabled,
    bool GrpcEnabled);

public record SystemLinkConfiguration(
    Uri? Url,
    Uri? OidcAuthorityUrl,
    string ClientId,
    IReadOnlyList<string> Scopes);
```

> **Deployment patterns for `SystemLink:Url` and
> `SystemLink:OidcAuthorityUrl`:** The two URL fields accommodate both OIDC
> deployment patterns used in the POC and production:
>
> - **SystemLink-as-OIDC-provider** (POC default): SystemLink implements the
>   server-side PKCE flow itself and issues OAuth tokens directly. In this case
>   set both fields to the same value — the SystemLink server URL.
> - **External OIDC provider**: An external identity provider (e.g., a
>   customer-managed OIDC server) issues tokens. In this case `OidcAuthorityUrl`
>   points to the external provider and `Url` points to the SystemLink
>   application server, which are typically different hostnames.
>
> Keeping the fields separate avoids locking the design into either pattern and
> lets the POC validate both approaches through configuration alone.

public record SecurityConfiguration( bool VerifyCallerSignature, int
CallerPromptCooldownSeconds);

public record LimitsConfiguration( int PkceTimeoutSeconds, int
TokenRefreshTimeoutSeconds, int TokenRefreshDeadbandSeconds, int
PolicyCacheDurationSeconds);

**Example `appsettings.json`:**

```json
{
  "NI.Measurements": {
    "ListenLocalHttp2Port": 0,
    "ListenLocalHttp1Port": 0
  },
  "DesktopLoginService": {
    "Transport": {
      "NamedPipe": { "Enabled": true },
      "Uds": { "Enabled": false },
      "Grpc": { "Enabled": false }
    },
    "SystemLink": {
      "Url": "",
      "OidcAuthorityUrl": "",
      "ClientId": "",
      "Scopes": ["openid", "profile", "email"]
    },
    "Security": {
      "VerifyCallerSignature": false,
      "CallerPromptCooldownSeconds": 60
    },
    "Limits": {
      "PkceTimeoutSeconds": 300,
      "TokenRefreshTimeoutSeconds": 30,
      "TokenRefreshDeadbandSeconds": 60,
      "PolicyCacheDurationSeconds": 300
    }
  },
  "Serilog": {
    "WriteTo": [
      {
        "Name": "Async",
        "Args": {
          "configure:File": {
            "Name": "File",
            "Args": {
              "path": "%ProgramData%\\National Instruments\\Desktop Login Service\\Logs\\DesktopLoginService.txt",
              "outputTemplate": "===== {Timestamp:G} ===== {Level}: {Message}{NewLine}",
              "restrictedToMinimumLevel": "Information",
              "rollOnFileSizeLimit": true,
              "fileSizeLimitBytes": 2097152,
              "retainedFileCountLimit": 5
            }
          }
        }
      }
    ]
  }
}
```

> **POC default**: `VerifyCallerSignature` is `false` to allow unsigned
> applications to call the service during rapid development and testing. This
> flag will be **removed** before production release; signature verification
> will be unconditionally enforced in the production build.

**SystemLink startup validation.** On startup the service checks that
`SystemLink:Url`, `SystemLink:OidcAuthorityUrl`, and `SystemLink:ClientId` are
non-empty and that `SystemLink:Scopes` includes `openid`, `profile`, and
`email`. If any condition fails the service exits with a non-zero code and a
descriptive message directing the user to run `setup`:

```text
Desktop Login Service is not configured. Run: dls setup
```

**First-run self-initialization.** On every startup the service creates any
missing runtime artifacts without requiring admin privileges:

- `%LocalAppData%\NationalInstruments\DesktopLoginService\` — created if absent;
  hosts `discovery.json` and `desktoploginservice.callers.json`.
- `%ProgramData%\National Instruments\Desktop Login Service\Logs\` — created if
  absent, assuming `%ProgramData%\National Instruments\` already exists (created
  by NI installer infrastructure).
- HMAC signing key — generated on first startup and stored in the OS credential
  store; reused on subsequent startups.

**Approved callers** (the list of NI application identities confirmed by the
user via the [confirmation prompt](#user-confirmation-for-new-callers)) are
stored in
`%LocalAppData%\NationalInstruments\DesktopLoginService\desktoploginservice.callers.json`.
This location is separate from the executable directory (which the NIPKG
installer controls) and is ACL'd to the current user. Each approval entry is
HMAC-SHA256 signed by the service at the time the user grants approval; the
signing key is held in the OS credential store and never written to disk in
plaintext. On startup, entries with invalid signatures are silently discarded
and the corresponding callers are re-prompted at next contact. See
[Approved callers file integrity](#approved-callers-file-integrity) for full
details. Unlike the main configuration, this file is updated at runtime and does
not require a service restart.

## OS credential store integration

The desktop login service is responsible for securely persisting OAuth refresh
tokens between user sessions. There is no existing NI abstraction for OS-level
secret storage — implementing this layer is a primary technical goal of the POC.

**Platform targets:**

- **Windows**: Windows Credential Manager (via
  `Windows.Security.Credentials.PasswordVault` or DPAPI-backed storage) —
  implemented in the POC.
- **Linux**: libsecret / GNOME Keyring — designed but not implemented in the
  POC. The `ITokenStore` abstraction is intended to support this platform in a
  future release.

**What is stored:**

Only **refresh tokens** are persisted to the OS credential store, written under
a service-specific namespace keyed by the current user's SID, e.g.
`NationalInstruments/DesktopLoginService/S-1-5-21-...`. Using the SID ensures
tokens for different users on the same machine do not collide.

**Credential store abstraction:**

The service defines an `ITokenStore` interface backed by the OS credential
store. The interface is mockable for unit testing. The POC implements the
Windows backend; the Linux backend is designed but deferred.

The `identity` parameter is the user's `sub` claim from the OIDC ID token. This
is the stable, unique identifier assigned by the SystemLink OIDC provider and is
used as the key when reading and writing refresh tokens in the credential store.

```csharp
public interface ITokenStore
{
    Task<string?> GetRefreshTokenAsync(string identity);
    Task SetRefreshTokenAsync(string identity, string refreshToken);
    Task DeleteRefreshTokenAsync(string identity);
}
```

## Login workflow

When an NI application calls the desktop login service's `Login` method, one of
three paths is taken:

1. **Session token already cached** — if a valid token exists from a prior login
   in this session (including from a different application), the service returns
   it immediately without prompting the user.
1. **SystemLink instance configured** — the service initiates a PKCE OAuth/OIDC
   flow:
   1. The service opens the user's default browser to the SystemLink OIDC
      provider's authorization endpoint.
   1. A local HTTP listener on a loopback address receives the authorization
      code redirect.
   1. The service exchanges the authorization code and PKCE verifier for access
      and refresh tokens. The token endpoint response also includes an ID token.
   1. The refresh token is persisted to the OS credential store.
   1. The user's identity is decoded from the ID token claims (`sub`, `name`,
      `email`, etc.) and cached in memory for the session.
   1. The service calls `GET <systemlink-instance>/niauth/v1/auth` with the
      access token as a bearer token to retrieve the user's authorization policy
      document, which is cached in memory.
   1. The access token, identity, and policies are held in memory and made
      available to callers.
1. **No SystemLink instance configured, or login fails** — the service derives
   an identity from the local OS account. See
   [Fallback behavior](#fallback-behavior).

### PKCE callback URL registration

The following mechanics are handled by `Duende.IdentityModel.OidcClient` (see
[Reuse](#reuse)) and are documented here for reference.

**Loopback listener.** Before opening the browser, the service binds a temporary
HTTP listener on a loopback address (`127.0.0.1`) at an OS-assigned ephemeral
port (port 0). The resulting address — e.g., `http://127.0.0.1:52741/callback` —
is used as the redirect URI for that specific login request. Using an ephemeral
port avoids conflicts with other services and requires no pre-configuration.

**OIDC client registration.** The SystemLink OIDC provider must be configured to
allow redirect URIs matching the loopback pattern `http://127.0.0.1:*/callback`.
This is consistent with
[RFC 8252 §8.3](https://datatracker.ietf.org/doc/html/rfc8252#section-8.3),
which specifically permits loopback redirect URIs for native applications and
allows any port on the loopback address. The OIDC provider must not restrict to
a single fixed port, because the port is ephemeral.

**Callback handling.** The listener accepts exactly one request on the
`/callback` path, extracts the `code` and `state` query parameters, validates
the `state` against the value generated at the start of the flow to prevent
CSRF, then closes the listener. The browser is redirected to a local completion
page confirming that login is complete and the browser tab may be closed.

**Concurrent flow limit.** The service permits only one pending PKCE flow at a
time. If `Login` is called while a flow is already in progress, the service
returns an error with the message "login flow already in progress". The caller
may retry when the current flow completes or times out.

**Timeout.** If the user does not complete authentication within a configurable
timeout (`Limits:PkceTimeoutSeconds`, default: 300 s), the listener is closed
and the `Login` call returns an error. The caller may retry.

**Authorization endpoint origin validation.** Before opening the browser, the
service validates that the authorization endpoint URL returned by the OIDC
discovery document shares the same origin (scheme, host, and port) as
`SystemLink:OidcAuthorityUrl`. If the origin does not match, the `Login` call
fails with a configuration error without opening the browser. This prevents a
compromised or spoofed discovery document from redirecting the user to a
different host. `SystemLink:OidcAuthorityUrl` and `SystemLink:Url` may be the
same value (when SystemLink itself is the OIDC provider) or different values
(when an external OIDC provider is in use) — both configurations are valid.

**Screen lock.** Screen lock detection is not implemented in the POC. If `Login`
is called while the screen is locked the browser open attempt will fail silently
or the PKCE timeout will expire. This is acceptable for the POC; screen lock
detection is a production graduation concern (see [Open issues](#open-issues)).

## CLI and service API surface

The desktop login service exposes a service API and a CLI with a **1:1 mapping**
between commands and API methods. Every operation available through the service
has a corresponding CLI subcommand that exercises the same code path through
`IDesktopLoginClient`. Named Pipe is the preferred transport for both production
use and interactive testing. The CLI is the primary tool for validating
workflows like PKCE login end-to-end — for example, running `login` from the
terminal exercises the full login flow over the preferred transport without
requiring a separate gRPC client.

The proto definition is deferred — see [Open issues](#open-issues). Commands and
methods will be added incrementally as the POC progresses. The following
specifies enough of the proto contract to begin implementation; field numbers
and complete `.proto` syntax are left to the implementation phase.

**Package and service name**: `ni.desktoploginservice.v1` /
`DesktopLoginService`

**JSON field naming**: proto3 default camelCase (e.g., `accessToken`,
`systemLinkConfigured`, `given_name` → `givenName` in proto, serialized as
`given_name` in JSON via `json_name` option).

**API method signatures:**

| Method        | Request message      | Response message      |
| ------------- | -------------------- | --------------------- |
| `Login`       | `LoginRequest`       | `LoginResponse`       |
| `Logout`      | `LogoutRequest`      | `LogoutResponse`      |
| `GetToken`    | `GetTokenRequest`    | `GetTokenResponse`    |
| `GetIdentity` | `GetIdentityRequest` | `GetIdentityResponse` |
| `GetPolicies` | `GetPoliciesRequest` | `GetPoliciesResponse` |
| `Health`      | `HealthRequest`      | `HealthResponse`      |

All request messages are empty for the POC. Response messages mirror the
[Response types](#response-types) JSON fields. `GetPoliciesResponse.policies`
uses `google.protobuf.Struct` to carry the opaque policy document. All response
messages include `bool success` and `string error` fields following the pattern
established in [Response types](#response-types).

| CLI command    | Method        | Description                                                                                                                                                                                                                  |
| -------------- | ------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `setup`        | _(CLI only)_  | Interactive first-run setup: prompts for `SystemLink:Url`, `SystemLink:OidcAuthorityUrl`, and `SystemLink:ClientId`, then writes `appsettings.json` and creates required directories. Can be re-run to update configuration. |
| `login`        | `Login`       | Initiates login for the current user; returns an OAuth token                                                                                                                                                                 |
| `logout`       | `Logout`      | Invalidates the current session: clears in-memory access token, identity, and cached policy document; deletes the refresh token from the OS credential store; and calls the OIDC provider's token revocation endpoint        |
| `get-token`    | `GetToken`    | Returns the cached access token; silently refreshes using the stored refresh token if the token is expired or expires within 60 seconds. Returns an error if no login session exists — callers must call `Login` first.      |
| `get-identity` | `GetIdentity` | Returns the cached identity of the current user; includes a source field indicating whether the identity is from SystemLink or the local OS account                                                                          |
| `get-policies` | `GetPolicies` | Returns the current user's SystemLink policy document                                                                                                                                                                        |
| `health`       | `Health`      | Returns service liveness and readiness status; equivalent to the HTTP `/livez` and `/readyz` endpoints when gRPC transport is enabled                                                                                        |

## Client library

The desktop login service ships a companion NuGet package,
`NationalInstruments.DesktopLoginService.Client`, for use by NI applications
that need to integrate with the service. The library encapsulates Named Pipe
connection management, service discovery, and proto message serialization,
exposing a simple async C# API. Consumers do not need to know the gRPC proto
schema or manage transport lifecycle directly.

**JSON wire format.** All responses are serialized as JSON on the wire
regardless of transport. Over the Named Pipe transport, responses are plain
UTF-8 JSON objects terminated by a newline. Over the gRPC transport (when
enabled), responses use proto3 JSON serialization. The client library
deserializes each response into a typed C# record, so consumers work with
strongly-typed objects and never parse JSON directly. The service CLI prints
each response as JSON to stdout.

**Package**: `NationalInstruments.DesktopLoginService.Client`

**Primary interface:**

```csharp
public interface IDesktopLoginClient
{
    Task<LoginResult> LoginAsync(CancellationToken cancellationToken = default);
    Task<LogoutResult> LogoutAsync(CancellationToken cancellationToken = default);
    Task<TokenResult> GetTokenAsync(CancellationToken cancellationToken = default);
    Task<IdentityResult> GetIdentityAsync(CancellationToken cancellationToken = default);
    Task<PolicyResult> GetPoliciesAsync(CancellationToken cancellationToken = default);
    Task<HealthResult> GetHealthAsync(CancellationToken cancellationToken = default);
}
```

### Response types

Each method returns a typed C# record. The JSON shapes below define the Named
Pipe wire format and gRPC proto3 JSON mapping; the C# records mirror these
fields exactly.

**Error handling policy.** For unexpected failures (transport errors, unhandled
exceptions), all methods return `success: false` with the captured exception
message in `error`. This is intentional for POC debugging; the error surface
will be refined as more failure modes are identified during implementation.

---

**`LoginResult`** — returned by `LoginAsync`.

```json
{ "success": true }
{ "success": false, "error": "login flow already in progress" }
```

Possible `error` values: `"login flow already in progress"`,
`"authorization endpoint origin mismatch"`, `"login timed out"`,
`"<exception message>"` for unexpected failures.

```csharp
public record LoginResult(bool Success, string? Error = null);
```

---

**`LogoutResult`** — returned by `LogoutAsync`. Local state (in-memory tokens,
cached policy document, and credential store entry) is always cleared regardless
of whether the OIDC revocation endpoint succeeds. Clearing the policy cache on
logout prevents a subsequent user on the same session from receiving the
previous user's policy grants during the cache TTL window.

```json
{ "success": true }
{ "success": true, "warning": "SystemLink instance could not be reached; tokens revoked locally only" }
{ "success": false, "error": "<exception message>" }
```

```csharp
public record LogoutResult(bool Success, string? Warning = null, string? Error = null);
```

---

**`TokenResult`** — returned by `GetTokenAsync`.

```json
{ "success": true, "accessToken": "eyJ..." }
{ "success": false, "error": "no active login session; call Login first" }
{ "success": false, "error": "token refresh failed: request timed out" }
{ "success": false, "error": "token refresh failed: <reason>" }
```

```csharp
public record TokenResult(bool Success, string? AccessToken = null, string? Error = null);
```

---

**`IdentityResult`** — returned by `GetIdentityAsync`. Fields mirror the
standard OIDC ID token claims. The `source` field is added by the service.
`GetIdentityAsync` always returns an identity (either `SystemLink` or
`LocalOS`); `success: false` is used only for unexpected transport failures.

```json
{
  "success": true,
  "source": "SystemLink",
  "sub": "user-uuid",
  "name": "Jane Smith",
  "email": "jane@example.com",
  "given_name": "Jane",
  "family_name": "Smith"
}
```

```json
{
  "success": true,
  "source": "LocalOS",
  "sub": "DOMAIN\\jsmith",
  "name": "DOMAIN\\jsmith"
}
```

`email`, `given_name`, and `family_name` are omitted for `LocalOS` identities.

```csharp
public record IdentityResult(
    bool Success,
    string? Source = null,       // "SystemLink" | "LocalOS"
    string? Sub = null,
    string? Name = null,
    string? Email = null,
    [property: JsonPropertyName("given_name")] string? GivenName = null,
    [property: JsonPropertyName("family_name")] string? FamilyName = null,
    string? Error = null);
```

---

**`PolicyResult`** — returned by `GetPoliciesAsync`. The `policies` value is the
verbatim JSON body returned by `GET <systemlink-instance>/niauth/v1/auth`. The
client library treats it as an opaque `JsonElement` and does not parse it.

> **POC behaviour**: When SystemLink is unavailable — because no instance is
> configured, the instance is unreachable, or OIDC login failed — `GetPolicies`
> returns an error. This is a POC simplification. A production implementation
> will need to return a policy document in these cases; what that document
> contains is deferred to productization (see [Open issues](#open-issues)).

```json
{ "success": true, "policies": { /* verbatim /niauth/v1/auth response */ } }
{ "success": false, "error": "SystemLink cannot be reached" }
```

```csharp
public record PolicyResult(
    bool Success,
    JsonElement? Policies = null,
    string? Error = null);
```

---

**`HealthResult`** — returned by `GetHealthAsync` and at the HTTP health
endpoints. Based on the Discovery Service `{ "status": "pass" }` pattern,
extended with service-specific fields.

```json
{
  "status": "pass",
  "live": true,
  "ready": true,
  "activeTransports": ["NamedPipe"],
  "systemLinkConfigured": true
}
```

`ready` is `false` while the service is still initializing. `activeTransports`
lists currently enabled transports. `systemLinkConfigured` is `true` when
`SystemLink:Url` is set and passes HTTPS validation.

```csharp
public record HealthResult(
    string Status,
    bool Live,
    bool Ready,
    IReadOnlyList<string> ActiveTransports,
    [property: JsonPropertyName("systemLinkConfigured")]
    bool SystemLinkConfigured);
```

**Service discovery.** The client reads
`%LocalAppData%\NationalInstruments\DesktopLoginService\discovery.json`, which
the service writes on startup, to locate the active Named Pipe name or gRPC
port. This file is a POC mechanism; production will use MeasurementLink
Discovery Service registration (see [Open issues](#open-issues)). The client
library abstracts this so consuming applications require no configuration.

**DI registration.** The library follows the same `AddXxx` extension pattern
used by `NationalInstruments.Service.Extensions.*`:

```csharp
builder.Services.AddDesktopLoginClient();
```

This registers `IDesktopLoginClient` as a singleton backed by the Named Pipe
transport resolved from the service discovery file. Transport and timeout
options are configurable via an overload that accepts an
`Action<DesktopLoginClientOptions>`.

**Transport.** Named Pipe is the default (see [IPC transport](#ipc-transport)).
The client manages channel lifetime and reconnection transparently, and falls
back to the gRPC address from the discovery file if Named Pipe is not available.

### Ballyhoo test harness

**Ballyhoo** (`Ballyhoo.exe`) is a second CLI application built as part of the
POC to interactively exercise the desktop login service through the client
library. Its purpose is to validate end-to-end behavior — Named Pipe connection,
service discovery, and each API method — from a consumer's perspective, without
conflating the test with the service's own internal CLI.

The `bh` prefix on every command is intentional: it forces the developer to
remain aware of which application they are running. Commands issued via `bh` go
through `IDesktopLoginClient` over Named Pipe, exactly as a production NI
application would. Commands issued without the prefix exercise the service's own
CLI path.

| Ballyhoo command  | `IDesktopLoginClient` call | Equivalent service CLI |
| ----------------- | -------------------------- | ---------------------- |
| `bh login`        | `LoginAsync`               | `login`                |
| `bh logout`       | `LogoutAsync`              | `logout`               |
| `bh get-token`    | `GetTokenAsync`            | `get-token`            |
| `bh get-identity` | `GetIdentityAsync`         | `get-identity`         |
| `bh get-policies` | `GetPoliciesAsync`         | `get-policies`         |
| `bh health`       | `GetHealthAsync`           | `health`               |

Ballyhoo is a POC tool only and will not be shipped to customers.

## IPC transport

The desktop login service supports two IPC transport mechanisms. Which
transport(s) are active is controlled by the service configuration file, and
both can be enabled simultaneously.

| Transport                | Platform | Config key                    | Status                           |
| ------------------------ | -------- | ----------------------------- | -------------------------------- |
| Named Pipe               | Windows  | `Transport:NamedPipe:Enabled` | Preferred                        |
| Unix Domain Socket (UDS) | Linux    | `Transport:Uds:Enabled`       | Designed; not implemented in POC |
| gRPC / Kestrel (HTTP/2)  | All      | `Transport:Grpc:Enabled`      | Supported                        |

**Named Pipe is the preferred transport for production on Windows.** The pipe
name is `NationalInstruments.DesktopLoginService.<SID>` where `<SID>` is the
current user's Windows SID (e.g.,
`NationalInstruments.DesktopLoginService.S-1-5-21-...`). Using a SID-scoped name
ensures that simultaneous user sessions (Fast User Switching, Remote Desktop)
each get an independent pipe without name collisions, consistent with how the
credential store namespace is keyed. The full pipe name is written to
`discovery.json` at startup; client library consumers read it from there and
never need to construct it themselves. The pipe is an OS-mediated mechanism that
never touches the network stack and supports kernel-level caller identity
verification (see [Security considerations](#security-considerations)). It
eliminates the MITM surface that exists with any TCP-based transport.

**Named Pipe protocol.** The Named Pipe transport uses a simple JSON
request/response protocol — it does **not** use HTTP/2 or gRPC framing. Each
request is a UTF-8 JSON object terminated by a newline (`\n`). The service reads
the request, executes the operation, and writes back a UTF-8 JSON response
terminated by a newline. Each connection handles exactly one request/response
pair and is then closed.

Request format:

```json
{ "version": 1, "method": "Login" }
```

Response format:

```json
{ "version": 1 /* result fields — see Response types */ }
```

**Protocol versioning.** Both request and response carry a `"version"` integer
field. The current protocol version is `1`. The `version` field is optional in
requests — absence is treated as `v1` for backward compatibility with any
tooling built before versioning was added. In the POC the service always
responds with `"version": 1` and does not reject unknown versions; the field
reserves the namespace for future negotiation without any current cost. When a
breaking change is needed (new required field, renamed method, changed response
envelope), the version is incremented and the service can use the request
version to select a compatible response shape.

The `method` value maps to the gRPC method name (e.g., `"Login"`, `"GetToken"`,
`"Health"`). Methods that require parameters in the future will include a
`"params"` object in the request; all POC methods are zero-argument.

**UDS is the preferred transport for future Linux support.** The `ITransport`
abstraction and configuration model are designed to support UDS; implementation
is deferred to a future release.

**gRPC is supported but is disabled by default** (see the example
`appsettings.json`). When enabled it carries a security caveat: gRPC over TCP
loopback is susceptible to MITM from privileged local processes (driver-level
interception, Winsock LSP hooks on Windows). Mitigating this requires mutual TLS
(mTLS), which is not in scope for the POC. The gRPC transport must not be
deployed in production without mTLS (see [Open issues](#open-issues)).

**Transport abstraction.** Transport implementations satisfy
`IDesktopLoginClient` directly — there is no separate `ITransport` interface.
This keeps a single canonical contract and prevents the method signatures from
drifting out of sync across projects. Two implementations exist in the POC:

- **`LocalTransport`** — used by the service's own built-in CLI; calls service
  handlers directly in-process with no serialization overhead. Also implements
  `IAsyncDisposable` internally for lifecycle management; this is not surfaced
  through `IDesktopLoginClient`.
- **`NamedPipeTransport`** — used by Ballyhoo and the client library; connects
  to the Named Pipe and uses the JSON request/response protocol above. Also
  implements `IAsyncDisposable` to manage the connection lifecycle.

A `GrpcTransport` implementation of `IDesktopLoginClient` can be added when the
gRPC transport is needed.

## Token caching and expiry

- **Access tokens**: Held in memory. When `GetToken` is called the service
  checks the token's `exp` claim. If the token has more than
  `Limits:TokenRefreshDeadbandSeconds` (default: 60 s) of remaining lifetime it
  is returned immediately. If the token is expired or will expire within the
  deadband window, the service must obtain a fresh access token via the stored
  refresh token.

  The refresh operation is serialized with a per-session `SemaphoreSlim(1, 1)`.
  Only one refresh is ever in flight at a time; concurrent `GetToken` callers
  wait on the semaphore and share the result of the single in-flight refresh.
  This prevents the concurrent-rotation failure where two callers each send the
  same refresh token to the OIDC token endpoint, the first succeeds, and the
  provider invalidates the token before the second call completes.

  On a successful refresh, both the new access token (in-memory cache) and the
  new refresh token (credential store via `ITokenStore.SetRefreshTokenAsync`)
  are updated before the semaphore is released. This ensures that providers
  implementing refresh token rotation (RFC 6749, OAuth 2.0 Security BCP) always
  find a valid token on the next refresh cycle.

  The refresh HTTP POST to the OIDC token endpoint is bounded by
  `Limits:TokenRefreshTimeoutSeconds` (default: 30 s). The `CancellationToken`
  supplied by the caller is also forwarded to the refresh call, so caller-side
  cancellation is respected. If the HTTP call times out or the caller cancels,
  the service returns
  `{ "success": false, "error": "token refresh failed: request timed out" }`
  without modifying the cached state — the caller must retry or invoke `Login`
  again. If the refresh fails for any other reason (e.g., the refresh token has
  itself expired), the same error path applies.

- **Refresh tokens**: Longer-lived, persisted in the OS credential store.
  Invalidated only on explicit logout or by an administrator action in
  SystemLink.
- **User identity**: Decoded from the ID token at login and cached in memory for
  the session. Not refreshed independently — re-login produces a new ID token.
- **Authorization policy documents**: Fetched from
  `GET <systemlink-instance>/niauth/v1/auth` after login and cached in memory
  for `Limits:PolicyCacheDurationSeconds` (default: 300 s). Staleness within
  this window is acceptable in exchange for resilience to intermittent
  connectivity.

## Fallback behavior

The service must accommodate offline and unconfigured scenarios:

- If a cached access token is available but the network is unreachable, return
  the cached token without attempting a refresh.
- If no token is available and no SystemLink instance is reachable, derive an
  identity from the local OS account. The `sub` field is set to
  `WindowsIdentity.GetCurrent().Name` (e.g., `DOMAIN\jsmith`), and `name` is set
  to the same value. Fields other than `sub` are optionally provided.
- Applications receive the identity along with a `source` field that
  unambiguously indicates which case applies:
  - `SystemLink` — the identity was obtained from a successful OIDC login and
    reflects the user's SystemLink account. Policy-based authorization is
    available.
  - `LocalOS` — no SystemLink login is active. The identity reflects the local
    OS account only. Applications must degrade gracefully and must not enforce
    or rely on SystemLink policy.
- `GetIdentity` never blocks. It returns the most recently cached identity
  synchronously without attempting a network refresh.

## Logging

The service logs all meaningful security events and configuration changes using
Serilog:

- Login and logout events (success and failure, with reason)
- Token refresh events
- SystemLink connection configuration changes
- Credential store read/write failures

Tokens, token fragments, and identity claims are **never** included in log
output at any severity level, including debug. This constraint must be verified
in implementation review before each release.

**Windows log path:**
`%ProgramData%\National Instruments\Desktop Login Service\Logs\DesktopLoginService.txt`
(2 MB rolling, 5 retained files — consistent with Discovery Service convention)

**Linux log path** (not implemented in POC):
`${localstatedir}/log/${package}/DesktopLoginService.txt`

Linux logging has additional requirements not in scope for the POC:

- `ERROR` and `WARNING` level events must also be forwarded to syslog or
  journald, following the distribution's logging policies. Serilog's
  `Serilog.Sinks.Syslog` or `Serilog.Sinks.Journald` sinks are candidates.
- Log files must be owned by the OS account running the service and protected
  with mode `0640` (owner read/write, group read-only, no access for others).
  This prevents unprivileged accounts from reading security-relevant log
  content. The service must create the log directory with the same ownership and
  mode `0750`.

Serilog is configured via the `Serilog` section of `appsettings.json` (see
[Service configuration](#service-configuration)), so log path, rolling policy,
and output template are adjustable without code changes.

## Security considerations

### Refresh tokens never leave the service

The service never returns a refresh token to a caller over the IPC channel.
Refresh tokens are written to the OS credential store and accessed only by the
service process. Applications and CLI commands receive only short-lived access
tokens. This limits the blast radius of any spoofing attack: a stolen access
token expires in minutes; a stolen refresh token would permit indefinite
impersonation.

### Named Pipe as the preferred transport (Windows)

Named Pipe and UDS are OS-mediated mechanisms that never touch the network stack
and support kernel-level caller identity verification, eliminating the MITM
surface present in TCP-based transport. gRPC over TCP loopback requires a
transport security measure to reach the same security posture. See
[IPC transport](#ipc-transport) and
[Securing the gRPC transport](#securing-the-grpc-transport-out-of-scope-for-poc).

### Caller identity verification

Before responding to any request other than `Health`, the service verifies the
identity of the calling process using OS-level mechanisms. This applies to
`Login`, `GetToken`, `GetIdentity`, `GetPolicies`, and `Logout` — all of which
return or operate on sensitive data.

- **Windows Named Pipe**: `GetNamedPipeClientProcessId` retrieves the client
  PID; the service inspects the executable path and verifies its Authenticode
  code signature against NI's signing certificate. Applications that are
  unsigned, self-signed, or signed by any certificate other than an NI
  certificate are rejected.
- **Linux UDS** (future): `SO_PEERCRED` / `LOCAL_PEERCRED` returns the client's
  PID, UID, and GID at the kernel level and cannot be spoofed by the client
  process.

Requests from unrecognized or unsigned callers are rejected.

> **POC only**: When `Security:VerifyCallerSignature` is `false`, the NI
> certificate check is skipped entirely and any process — including unsigned and
> third-party-signed processes — may connect. This allows development tooling
> and unsigned POC builds to call the service without going through the NI
> code-signing pipeline. This flag and the bypass code path will be removed
> before production release; NI certificate verification will be unconditionally
> enforced.

### Transport ACLs and socket permissions

- **Windows Named Pipe**: The pipe is created with a security descriptor
  restricting connections to the current user's SID. Processes running under a
  different user or as elevated system processes cannot connect.
- **Linux UDS** (future): The socket file is created with `0600` permissions
  (owner read/write only), enforcing the same constraint at the filesystem
  level.
- **Service discovery file**: The address file written on startup is created
  with a per-user DACL matching the Named Pipe — readable only by the current
  user and SYSTEM. Processes running as a different user cannot read the pipe
  name or gRPC port from the file.

### User confirmation for new callers

The first time an unrecognized application requests a token, the service
presents a confirmation prompt using a Win32 `MessageBox` with two buttons:
**Allow** and **Deny**. The message text identifies the application by its
executable path: "Application `<path>` is requesting access to your SystemLink
identity." Because the service runs in the user's interactive session (see
[Architecture overview](#architecture-overview)), it can show this dialog
directly. Approved identities are persisted via the mechanism described in
[Approved callers file integrity](#approved-callers-file-integrity).

The prompt displays the executable path reported by the OS. When
`Security:VerifyCallerSignature` is `true` (production), this path is backed by
an Authenticode signature verified against NI's signing certificate — only
applications signed with an NI key will have passed the caller check. When
`VerifyCallerSignature` is `false` (POC mode), the NI certificate check is
skipped — the path is unverified and the prompt is a UX convenience only, not a
reliable security boundary.

#### Prompt serialization

Win32 `MessageBox` blocks the calling thread. Without coordination, two
unrecognized callers connecting simultaneously would each trigger a prompt and
both would appear on screen at once. To prevent this, the service serializes all
approval prompts behind a single `SemaphoreSlim(1, 1)`. Only one prompt is ever
visible at a time; requests from a second unrecognized caller wait in queue
until the active prompt is dismissed.

#### Per-caller rate limiting

A malicious or buggy caller can generate a stream of approval dialogs by
repeatedly connecting and requesting a token. The service enforces a per-caller
rate limit keyed on the executable path. After a prompt is dismissed (regardless
of Allow or Deny), that executable path is blocked from triggering another
prompt for `Security:CallerPromptCooldownSeconds` (default: 60 s). Any request
that arrives within the cool-down period receives an immediate error response
(`"approval rate limit exceeded"`) without displaying a dialog. This prevents a
single caller from monopolizing the approval queue or flooding the user with
dialogs. During interactive development the cool-down can be set to `0` to
disable rate limiting entirely.

### HTTPS enforcement for SystemLink connection

At startup, the service validates that both `SystemLink:Url` and
`SystemLink:OidcAuthorityUrl` use the `https` scheme. If either is configured
with `http://`, the service exits with the configuration error (see
[Startup validation](#service-configuration)) rather than starting in a degraded
state.

For all outbound HTTPS connections the service requires full TLS certificate
validation using .NET's default `HttpClient` stack (chain trust, hostname
verification, expiry, and revocation per OS settings). There is no option to
bypass certificate validation. The `setup` command also rejects non-HTTPS URLs
before writing `appsettings.json`.

### Approved callers file integrity

The approved callers file is stored at
`%LocalAppData%\NationalInstruments\DesktopLoginService\desktoploginservice.callers.json`,
separate from the executable directory, and is ACL'd to the current user.

As a second layer of tamper protection, each entry is HMAC-SHA256 signed by the
service when the user approves a caller. The HMAC key is generated on first run
and stored in the OS credential store under the key
`NationalInstruments/DesktopLoginService/CallerSigningKey`. It is never written
to the callers file or to disk in plaintext.

On startup, the service verifies every entry's signature. Entries that fail
verification are silently discarded — the affected callers are treated as new on
their next connection and the user is re-prompted. This ensures that an attacker
who tampers with the file (e.g., pre-approves their own application by writing a
crafted entry) gains nothing: the forged entry lacks a valid HMAC and is dropped
before the service accepts any requests.

### Securing the gRPC transport (out of scope for POC)

When the gRPC transport is enabled, the loopback TCP channel is susceptible to
MITM attacks from privileged local processes. Mutual TLS (mTLS) — where both the
service and each NI application client present certificates issued by a
per-installation CA — is one approach to mitigating this. Alternatively, the
platform may identify other transport security mechanisms that provide
equivalent protection. Either way, this is not in scope for the POC and is
tracked as an open issue. Enabling gRPC in production without an agreed
transport security measure is a known risk.

## Reuse

- **MeasurementLink Discovery Service** provides the reference architecture for
  the ASP.NET Core + gRPC + Kestrel service host, DI registration pattern, and
  Serilog configuration.
- **`ConfigureKestrelForMeasurementServices`** (from
  `NationalInstruments.Service.Extensions.Registration`) provides NI's shared
  Kestrel setup for gRPC services, including port binding via the
  `NI.Measurements` configuration section, HTTP/2 vs HTTP/1 separation, and port
  readback. Used when the gRPC transport is enabled.
- **NationalInstruments.Core** and **NationalInstruments.Service.Extensions.\***
  provide shared NI DI and service-hosting utilities.
- **[`Duende.IdentityModel.OidcClient`](https://www.nuget.org/packages/Duende.IdentityModel.OidcClient)**
  is used for the PKCE OAuth/OIDC flow. It handles authorization URL
  construction, PKCE code verifier/challenge generation, the loopback callback
  listener, authorization code exchange, ID token validation, and token refresh.
  This library is selected for the POC; a formal technology selection will be
  conducted post-POC to evaluate whether to continue with it or adopt an
  alternative (see [Open issues](#open-issues)).
- **OS credential store integration** is new NI IP developed as part of this
  effort. No existing NI credential management library was identified for reuse;
  building this abstraction is a primary deliverable of the POC.
- **`NationalInstruments.DesktopLoginService.Client`** (new NuGet, developed as
  part of this effort) is the companion client library consumed by Ballyhoo and,
  eventually, by production NI applications. See
  [Client library](#client-library).

## Testing strategy

Given the POC nature of this work, the testing strategy prioritizes validating
the technical approach over production coverage:

- **Unit tests**: `ITokenStore` implementations, token refresh logic, PKCE flow
  state machine, fallback identity construction.
- **Integration tests**: End-to-end login flow against a test SystemLink
  instance; OS credential store round-trips on Windows.
- **Manual validation via Ballyhoo**: The
  [Ballyhoo test harness](#ballyhoo-test-harness) exercises each
  `IDesktopLoginClient` method interactively over Named Pipe, validating the
  PKCE login flow, token refresh, identity and policy retrieval, and the
  fallback identity scenario when offline or unconfigured.
- **Service startup and CLI smoke test**: Verifies the service starts, writes
  the discovery file, and the service CLI commands respond correctly.

A more detailed test plan will be produced when the service graduates from POC
to production.

# Alternative implementations and designs

## Do nothing — physical isolation

Continue requiring customers to use OS-level access controls and physical
network isolation to restrict access to privileged NI application workflows.

Rejected because:

- Violates NIAP CC standards that require application-level access controls for
  privileged operations.
- Requires customers to have deep expertise in OS and network security
  configuration.
- Provides shallow defense-in-depth with no application-level enforcement.

## Per-application OIDC integration

Each NI application independently integrates with a customer's OIDC provider
rather than delegating to a shared service.

Rejected because:

- Login is not coordinated across applications — the user must log in separately
  to each.
- Each application team must independently develop and maintain OIDC client and
  credential management code.
- No centralized location for logging security events or managing token
  invalidation.

## Windows Web Account Manager (WAM) broker plugin

Windows 10+ includes a built-in identity broker (`tokenbroker.exe`) extensible
via WAM provider plugins. A WAM plugin is a COM/WinRT out-of-process server that
implements `IWebAccountProvider` and related interfaces. Once installed, any
application can call `WebAuthenticationCoreManager` APIs to request tokens
without knowing the details of the OIDC provider, and SSO across all
participating apps is managed by the OS. Microsoft's own MSAL library uses WAM
for Azure AD accounts on Windows.

Rejected because:

- **High implementation cost.** Writing a WAM provider plugin requires C++/WinRT
  or C#/WinRT with COM knowledge against a complex, poorly documented interface
  family. The engineering effort is comparable to or greater than the proposed
  custom service, without proportional benefit for the POC.
- **Windows-only.** WAM is a Windows Runtime facility with no equivalent on
  Linux. A future Linux desktop release would require a different solution,
  whereas the proposed custom service shares its codebase across platforms.
- **Admin-privilege installation.** WAM provider plugins are registered under
  `HKLM`, requiring elevated privileges at install time. This constrains
  deployment in environments where NI software is installed without admin
  rights.
- **OS-coupled lifecycle.** The plugin is registered system-wide and managed by
  Windows, which reduces NI's control over upgrade, rollback, and diagnostic
  behavior compared to a self-contained NI-managed service.
- **Provider URL is not known at install time.** WAM provider plugins are
  registered with a fixed authority URL. Because the SystemLink instance URL is
  supplied by the user at runtime (not at install time), the plugin would have
  no well-known authority to register against. Supporting multiple or
  user-configured SystemLink instances would require significant additional
  complexity in the plugin's registration and account discovery model.

# Open issues

1. **gRPC proto definition** — The `ni.desktoploginservice.v1` proto file is not
   yet defined. This will be the primary API design output of the POC
   implementation phase. A subsequent HLD update will include the full proto
   schema.

1. **Port numbers** — The HTTP/2 (gRPC) and HTTP/1 listen ports are TBD. They
   must not conflict with Discovery Service ports (42000/42001) or other
   MeasurementLink services.

1. **Production process model graduation** — The path from CLI tool to
   production user-session background process has not been fully designed. The
   process model decision (user-session startup application via Task Scheduler,
   not a Windows SCM service) has been made; remaining open questions include:
   - Task Scheduler task definition: conditions, triggers, and whether to use
     "run only when user is logged on" to prevent Session 0 startup.
   - Crash recovery: Task Scheduler supports restart-on-failure; the retry
     policy and delay need to be defined.
   - Screen-lock behavior for `Login`: the service should return a distinct
     error code when interactive login is unavailable (session locked), so
     callers can present an appropriate "sign in required" message.
   - NIPKG installer structure and upgrade behavior.

1. **Linux credential store and UDS transport** — The `ITokenStore` interface
   and `ITransport` abstraction are designed to support Linux (libsecret / GNOME
   Keyring for credential storage; UDS for IPC). Neither is implemented in the
   POC. Platform-specific behaviors that need validation include the libsecret
   session model and `SO_PEERCRED` caller identity on Linux.

1. **User identity abstraction for cross-platform support** — This document uses
   Windows SID throughout to represent the current user's OS-level identity
   (pipe name scoping, credential store namespacing, file ACLs). On Linux the
   equivalent concept is the `uid`/`gid` pair. Before Linux support is
   implemented, an abstraction (e.g., `IUserIdentity`) must be introduced so
   that all SID-keyed operations — pipe/socket naming, `ITokenStore` namespace,
   discovery file ACL — resolve to the correct platform representation at
   runtime. The abstraction should be introduced alongside the UDS transport
   work to avoid a later cross-cutting refactor.

1. **Caller verification on NI LinuxRT** — The Windows caller verification path
   relies on Authenticode code signing to confirm that a connecting process is a
   legitimate NI application. NI LinuxRT targets do not yet have universal
   binary signing, so this mechanism is not directly applicable. An alternative
   caller verification strategy for LinuxRT must be defined before the service
   can be deployed there. Candidate approaches include filesystem ACLs on the
   UDS socket path, a pre-approved path allowlist (analogous to the Windows
   callers file but without signature-backed integrity), or a LinuxRT-specific
   signing programme. The right approach depends on the LinuxRT security model
   and the timeline for broader NI binary signing adoption on that platform.

1. **gRPC transport security** — When the gRPC transport is enabled in
   production, the loopback TCP channel requires a transport security measure to
   prevent MITM attacks from privileged local processes. Mutual TLS (mTLS) is
   one option — it involves generating a per-installation CA and distributing
   client certificates to NI applications that use the gRPC transport.
   Alternatively, the platform may identify other mechanisms that provide
   equivalent protection. This decision is deferred to production graduation;
   the gRPC transport must not be deployed in production without an agreed
   security measure in place.

1. **OIDC client library selection** — `Duende.IdentityModel.OidcClient` is used
   for the POC. Post-POC, a formal technology selection should evaluate this
   library against alternatives (e.g., `Microsoft.Identity.Client` / MSAL) on
   criteria including license terms, long-term maintenance, NI third-party
   inclusion requirements, and fit with the production Windows service
   architecture.

1. **Discovery Service integration** — The POC uses a local `discovery.json`
   file at
   `%LocalAppData%\NationalInstruments\DesktopLoginService\discovery.json` for
   service location. In production, the service should register with the
   MeasurementLink Discovery Service so that client applications can locate it
   via the standard `IDiscoveryClient.ResolveServiceAsync` API, consistent with
   other MeasurementLink services. The `discovery.json` file and the hard-coded
   pipe name `NationalInstruments.DesktopLoginService.<SID>` are POC-only and
   will be replaced.

1. **OIDC configuration auto-discovery** — Users currently must configure three
   SystemLink-specific values manually: `SystemLink:Url`,
   `SystemLink:OidcAuthorityUrl`, and `SystemLink:ClientId`. A better experience
   would require only the SystemLink hostname; the service could fetch the OIDC
   authority URL and client ID from a public, read-only endpoint on the
   SystemLink server (e.g., `GET <systemlink-instance>/niauth/v1/client-info`).
   This would eliminate manual configuration steps and reduce misconfiguration
   risk. Implementing this requires server-side changes to SystemLink and is
   therefore out of scope for this POC. All three values remain required
   user-configured fields for now.

1. **Offline / `LocalOS` policy document** — In the POC, `GetPolicies` returns
   an error whenever SystemLink is unavailable. Production will require a policy
   document to be returned in this case so that applications have a consistent
   contract regardless of connectivity. The content and structure of that
   offline policy document — for example, a minimal installed baseline, a cached
   last-known document, or a well-defined empty grants set — is deferred to
   productization.

# POC implementation plan

The goal is a working POC within **10 business days**. Each story maps to a
feature branch that is PR-reviewed and merged before the next branch is cut.
Stories are ordered by dependency; stories on the same day can run in parallel
only if their dependencies are met.

---

## Story 1 — Project scaffold and shared types `feature/project-scaffold`

**Target**: Day 1

Create the solution with three projects — `DesktopLoginService`,
`NationalInstruments.DesktopLoginService.Client`, `Ballyhoo` — and establish the
shared foundation all later stories depend on.

**Acceptance criteria:**

- Solution builds cleanly on Windows with the .NET SDK version pinned in
  `global.json`.
- `setup` command prompts interactively for `SystemLink:Url`,
  `SystemLink:OidcAuthorityUrl`, and `SystemLink:ClientId`, then writes a
  complete `appsettings.json` (scopes defaulting to
  `["openid", "profile", "email"]`, `VerifyCallerSignature` defaulting to
  `false`). Re-running `setup` overwrites the existing file.
- On startup (post-setup), the service creates
  `%LocalAppData%\NationalInstruments\DesktopLoginService\` if absent and writes
  `discovery.json`. It also creates
  `%ProgramData%\National Instruments\Desktop Login Service\Logs\` if absent
  (assuming `%ProgramData%\National Instruments\` exists).
- If `appsettings.json` is missing or required fields are empty, the service
  exits with `"Desktop Login Service is not configured. Run: dls setup"`.
- The host reads and binds `IServiceConfiguration` from `appsettings.json`.
- All C# result records (`LoginResult`, `LogoutResult`, `TokenResult`,
  `IdentityResult`, `PolicyResult`, `HealthResult`) and both interfaces
  (`ITransport`, `IDesktopLoginClient`) are defined and compile in the Client
  project.
- Serilog is wired up; a startup log message is written to the configured path.

---

## Story 2 — OS credential store `feature/credential-store`

**Target**: Day 1–2  
**Depends on**: Story 1

Implement `ITokenStore` backed by Windows Credential Manager so the service can
persist and retrieve refresh tokens across restarts.

**Acceptance criteria:**

- `WindowsTokenStore` implements `ITokenStore` using
  `Windows.Security.Credentials.PasswordVault`.
- Credential key uses the SID-scoped namespace
  `NationalInstruments/DesktopLoginService/<SID>/<sub>`.
- Unit tests verify round-trip set/get/delete with a mock or test vault.
- `ITokenStore` is registered in DI; `WindowsTokenStore` is the production
  implementation.

---

## Story 3 — Named Pipe server + `Health` end-to-end `feature/named-pipe-transport`

**Target**: Day 2–3  
**Depends on**: Story 1

Implement the Named Pipe server, `LocalTransport`, `NamedPipeTransport`, and
wire up the `Health` method end-to-end. This validates the full request/response
path before any business logic is added.

**Acceptance criteria:**

- Named Pipe server listens on `NationalInstruments.DesktopLoginService.<SID>`
  (where `<SID>` is the current user's SID) with a per-user SID ACL.
- Server reads a newline-terminated JSON request, deserializes `method`, routes
  it to `LocalTransport`, serializes the response as newline-terminated JSON.
- `LocalTransport.GetHealthAsync()` returns a `HealthResult` with `live: true`,
  `ready: true`, `activeTransports: ["NamedPipe"]`.
- `NamedPipeTransport.GetHealthAsync()` connects to the pipe and receives the
  same response.
- `bh health` (Ballyhoo) and `health` (service CLI) both print the JSON to
  stdout.
- `discovery.json` ACL is verified: a second OS user account cannot read the
  file.

---

## Story 4 — PKCE login, identity, and policy retrieval `feature/pkce-login`

**Target**: Day 3–5  
**Depends on**: Stories 2, 3

Implement the full PKCE OAuth/OIDC flow. This is the core of the POC.

**Acceptance criteria:**

- `OidcClient` is configured with `ClientId`, `OidcAuthorityUrl` (OIDC
  authority/discovery base URL), and `Scopes` from `IServiceConfiguration`.
- Authorization endpoint origin is validated before the browser is opened.
- One concurrent PKCE flow enforced; second concurrent `Login` call returns
  `{ "success": false, "error": "login flow already in progress" }`.
- On success: refresh token written to `ITokenStore` (keyed by `sub`), access
  token and `IdentityResult` cached in memory.
- `GET /niauth/v1/auth` called with the access token; policy document cached in
  memory.
- `login`, `get-identity`, and `get-policies` CLI commands and matching Ballyhoo
  commands all produce correct JSON output.
- Running `bh login` against a real SystemLink instance completes the browser
  flow and prints `{ "success": true }`.
- `login` → `get-identity` → `get-policies` workflow validated end-to-end.

---

## Story 5 — Token management and `LocalOS` fallback `feature/token-management`

**Target**: Day 5–6  
**Depends on**: Story 4

Implement `GetToken` with expiry/refresh, `Logout`, and the `LocalOS` fallback
identity.

**Acceptance criteria:**

- `GetToken` checks `exp` claim; returns cached token if not expired.
- `GetToken` uses the stored refresh token when the access token is expired; the
  refresh is serialized so only one HTTP call is in flight at a time and
  concurrent callers share the result. On success, both the in-memory access
  token and the credential-store refresh token
  (`ITokenStore.SetRefreshTokenAsync`) are updated before the lock is released.
- `GetToken` returns
  `{ "success": false, "error": "no active login session; call Login first" }`
  when no session exists.
- `Logout` clears in-memory tokens, identity, and cached policy document;
  deletes the refresh token from `ITokenStore`; and calls the OIDC revocation
  endpoint. If revocation fails, local state is still cleared and a `warning` is
  included in `LogoutResult`.
- `GetPolicies` called immediately after `Logout` returns
  `{ "success": false, "error": "no active login session; call Login first" }` —
  not a stale policy document.
- With no `SystemLink:Url` configured (or invalid URL), `GetIdentity` returns a
  `LocalOS` identity with `sub` = `WindowsIdentity.GetCurrent().Name`.
- `GetPolicies` in `LocalOS` mode returns
  `{ "success": false, "error": "SystemLink cannot be reached" }`.
- `get-token`, `logout` CLI commands and matching Ballyhoo commands produce
  correct JSON output.

---

## Story 6 — Caller verification and approval prompt `feature/caller-verification`

**Target**: Day 6–7  
**Depends on**: Story 3

Implement the caller identity pipeline: PID resolution, executable path
inspection, code signature verification, and the Win32 `MessageBox` confirmation
prompt with HMAC-signed callers file.

**Acceptance criteria:**

- On Named Pipe connection, `GetNamedPipeClientProcessId` retrieves the client
  PID and the executable path is resolved.
- With `VerifyCallerSignature: true`, unrecognized or unsigned callers are
  rejected before any handler is invoked.
- With `VerifyCallerSignature: false`, all callers are accepted (POC mode).
- First call from an unrecognized process displays a `MessageBox` with **Allow**
  and **Deny** buttons. Denying returns an error to the caller. Allowing
  persists a signed entry to `desktoploginservice.callers.json`.
- HMAC signing key is generated on first run and stored in the credential store
  at `NationalInstruments/DesktopLoginService/CallerSigningKey`.
- On restart, tampered or forged entries in `callers.json` are discarded and
  those callers are re-prompted.
- `Health` is excluded from caller verification and always responds.

---

## Story 7 — Client library NuGet package `feature/client-library`

**Target**: Day 7–8  
**Depends on**: Story 3

Package `NationalInstruments.DesktopLoginService.Client` as a consumable NuGet
with `AddDesktopLoginClient()` DI integration.

**Acceptance criteria:**

- `AddDesktopLoginClient()` registers `IDesktopLoginClient` as a singleton.
- The implementation reads `discovery.json`, prefers `namedPipe` when present,
  falls back to `grpcHttp2Port` if no pipe name is set.
- All six methods proxy to `NamedPipeTransport` and return typed result records.
- Unit tests mock the Named Pipe and verify each method's deserialization.
- The package is buildable as a `.nupkg` via `dotnet pack`.

---

## Story 8 — End-to-end integration validation `feature/integration-validation`

**Target**: Day 8–10  
**Depends on**: Stories 4, 5, 6, 7

Run the full POC workflow against a real SystemLink instance and verify all
paths described in the HLD.

**Acceptance criteria:**

- Full happy path: start service → `bh login` (browser completes) →
  `bh get-identity` (SystemLink identity) → `bh get-token` → `bh get-policies` →
  `bh logout` all produce correct JSON.
- Token expiry path: force expiry → `bh get-token` triggers a silent refresh and
  returns a new token.
- `LocalOS` fallback path: start with no `SystemLink:Url` → `bh get-identity`
  returns `LocalOS` identity.
- Concurrent login path: two rapid `bh login` calls; second returns
  `"login flow already in progress"`.
- Caller verification path (with `VerifyCallerSignature: false`): Ballyhoo
  triggers the `MessageBox` on first run; subsequent calls skip the prompt.
- Service restart: refresh token survives restart; `bh get-token` returns valid
  token without re-login.
- HTTPS validation: configure an `http://` URL; service marks SystemLink
  unavailable and `bh get-identity` returns `LocalOS`.

_This document was created from the high-level design template (don't remove
this)_
