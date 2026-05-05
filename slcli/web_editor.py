"""Web editor utilities for custom fields configuration editing."""

import http.server
import json
import secrets
import socketserver
import sys
import threading
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Optional, Any

import click
import requests

from .utils import ExitCodes, get_base_url, get_headers, get_ssl_verify


def _validated_proxy_origin(api_base: str) -> tuple[str, str]:
    """Return a validated scheme and netloc for proxy requests.

    Args:
        api_base: Configured SystemLink base URL.

    Returns:
        Tuple of scheme and network location.

    Raises:
        ValueError: If the configured base URL is not a plain HTTP(S) origin.
    """
    parsed = urllib.parse.urlsplit(api_base)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Editor proxy requires an HTTP(S) SystemLink base URL")
    if not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("Editor proxy requires a base URL without embedded credentials")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("Editor proxy requires a base URL without path, query, or fragment")
    return parsed.scheme, parsed.netloc


def _build_proxy_url(
    origin_scheme: str,
    origin_netloc: str,
    target_path: str,
) -> str:
    """Build a proxy URL from a validated origin and allowlisted path."""
    return urllib.parse.urlunsplit((origin_scheme, origin_netloc, target_path, "", ""))


def _validated_proxy_path(request_path: str) -> str:
    """Return a decoded absolute proxy path without dot-segments."""
    decoded_path = urllib.parse.unquote(request_path)
    if not decoded_path.startswith("/"):
        raise ValueError("Editor proxy requires an absolute request path")
    if any(segment in {".", ".."} for segment in decoded_path.split("/")):
        raise ValueError("Editor proxy rejects paths containing dot-segments")
    return decoded_path


def _validated_proxy_query_params(query: str) -> dict[str, list[str]]:
    """Return parsed proxy query parameters."""
    if not query:
        return {}

    try:
        return urllib.parse.parse_qs(
            query,
            keep_blank_values=True,
            strict_parsing=True,
            separator="&",
        )
    except ValueError as exc:
        raise ValueError("Editor proxy received an invalid query string") from exc


def _validated_single_query_value(
    query_params: dict[str, list[str]],
    name: str,
) -> str:
    """Return a single query value and reject repeated parameters."""
    values = query_params.get(name)
    if not values:
        raise ValueError(f"Editor proxy requires query parameter: {name}")
    if len(values) != 1:
        raise ValueError(f"Editor proxy rejects repeated query parameter: {name}")
    return values[0]


def _validated_integer_query_value(
    query_params: dict[str, list[str]],
    name: str,
    *,
    minimum: int,
    maximum: Optional[int] = None,
) -> str:
    """Return a validated integer query value preserved as a string."""
    raw_value = _validated_single_query_value(query_params, name)

    try:
        parsed_value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"Editor proxy requires an integer query parameter: {name}") from exc

    if parsed_value < minimum or (maximum is not None and parsed_value > maximum):
        raise ValueError(f"Editor proxy rejected out-of-range query parameter: {name}")

    return str(parsed_value)


def _validated_identifier_query_value(query_params: dict[str, list[str]], name: str) -> str:
    """Return a single identifier-like query value safe for proxy forwarding."""
    value = _validated_single_query_value(query_params, name)
    if len(value) > 256:
        raise ValueError(f"Editor proxy rejected oversized query parameter: {name}")
    if any(ord(character) < 32 for character in value):
        raise ValueError(f"Editor proxy rejected invalid query parameter: {name}")
    if any(character in value for character in "/\\?#"):
        raise ValueError(f"Editor proxy rejected invalid query parameter: {name}")
    return value


def _resolve_proxy_target(
    method: str,
    request_path: str,
    query: str,
) -> Optional[tuple[str, dict[str, str]]]:
    """Resolve a frontend route to a fixed upstream path and validated params."""
    query_params = _validated_proxy_query_params(query)

    if method == "POST":
        post_route_map = {
            "/api/dff/configurations": "/nidynamicformfields/v1/configurations",
            "/api/dff/update-configurations": "/nidynamicformfields/v1/update-configurations",
            "/nidynamicformfields/v1/update-configurations": "/nidynamicformfields/v1/update-configurations",
        }
        target_path = post_route_map.get(request_path)
        if target_path is None:
            return None
        if query_params:
            raise ValueError("Editor proxy does not forward query parameters for this route")
        return target_path, {}

    if method == "GET" and request_path == "/niuser/v1/workspaces":
        unexpected_params = set(query_params) - {"take", "skip"}
        if unexpected_params:
            raise ValueError("Editor proxy rejected unsupported workspace query parameters")

        safe_params: dict[str, str] = {}
        if "take" in query_params:
            safe_params["take"] = _validated_integer_query_value(
                query_params, "take", minimum=1, maximum=1000
            )
        if "skip" in query_params:
            safe_params["skip"] = _validated_integer_query_value(query_params, "skip", minimum=0)
        return "/niuser/v1/workspaces", safe_params

    if method == "GET" and request_path == "/nidynamicformfields/v1/resolved-configuration":
        unexpected_params = set(query_params) - {"configurationId"}
        if unexpected_params:
            raise ValueError(
                "Editor proxy rejected unsupported resolved-configuration query parameters"
            )
        return "/nidynamicformfields/v1/resolved-configuration", {
            "configurationId": _validated_identifier_query_value(query_params, "configurationId")
        }

    return None


class DFFWebEditor:
    """Web-based editor for custom fields configurations."""

    def __init__(self, port: int = 8080):
        """Initialize the DFF web editor.

        Args:
            port: Port number for the HTTP server
        """
        self.port = port
        self._editor_dir = self._resolve_editor_directory()

    def launch(self, file: Optional[str] = None, open_browser: bool = True) -> None:
        """Launch the web editor with optional file loading.

        Args:
            file: Optional JSON file to load initially
            open_browser: Whether to automatically open browser
        """
        try:
            import tempfile

            # Create a per-session temp directory for runtime files (config, uploaded files)
            # Keep it alive for the server lifetime
            self._temp_dir = tempfile.TemporaryDirectory(prefix="slcli-dff-")
            self._temp_path = Path(self._temp_dir.name)

            # Generate per-session secret for proxy auth
            self._secret = secrets.token_urlsafe(24)
            self._write_editor_config(file)
            self._start_server(open_browser)
        except Exception as exc:
            click.echo(f"✗ Error starting editor: {exc}", err=True)
            sys.exit(ExitCodes.GENERAL_ERROR)
        finally:
            # Clean up temp directory on exit
            if hasattr(self, "_temp_dir"):
                self._temp_dir.cleanup()

    def _resolve_editor_directory(self) -> Path:
        """Resolve the editor directory from the install location.

        Priority:
        1) PyInstaller MEIPASS (onefile extraction dir)
        2) Frozen onedir next to the executable
        3) Site-packages root containing dff-editor (pip/Poetry install)
        4) Source tree relative to this file (development)

        Returns:
            Path to the dff-editor directory

        Raises:
            FileNotFoundError: If dff-editor directory cannot be found
        """
        candidates = []

        # PyInstaller onefile mode
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "dff-editor")

        # Frozen onedir layout
        if getattr(sys, "frozen", False):
            candidates.append(Path(sys.executable).resolve().parent / "dff-editor")

        # pip/Poetry install: dff-editor alongside slcli package
        site_packages_dir = Path(__file__).resolve().parent.parent
        candidates.append(site_packages_dir / "dff-editor")

        # Development/source tree
        candidates.append(Path(__file__).resolve().parent.parent / "dff-editor")

        for candidate in candidates:
            if candidate.exists() and (candidate / "index.html").exists():
                return candidate

        # No editor directory found
        raise FileNotFoundError(
            "DFF editor assets not found. Please ensure the installation is complete. "
            "Try reinstalling: pip install --force-reinstall slcli"
        )

    def _write_editor_config(self, file: Optional[str]) -> None:
        """Write the editor configuration consumed by the frontend.

        Args:
            file: Optional initial file to load
        """
        config: dict[str, Any] = {
            "serverUrl": get_base_url().rstrip("/"),
            "secret": getattr(self, "_secret", None),
        }

        # If a file was provided, copy it to the temp directory for the editor to load
        if file:
            import shutil

            source_path = Path(file)
            if source_path.exists():
                dest_path = self._temp_path / "config.json"
                shutil.copy(source_path, dest_path)
                config["configFile"] = "config.json"

        config_path = self._temp_path / "slcli-config.json"
        config_path.write_text(json.dumps(config, indent=2))

    def _start_server(self, open_browser: bool) -> None:
        """Start the HTTP server and optionally open browser.

        Args:
            open_browser: Whether to automatically open browser
        """
        editor_dir = self._editor_dir  # Capture for closure
        temp_path = self._temp_path  # Capture for closure
        api_base = get_base_url().rstrip("/")
        api_scheme, api_netloc = _validated_proxy_origin(api_base)
        default_headers = get_headers()
        ssl_verify = get_ssl_verify()
        secret = self._secret

        class EditorTCPServer(socketserver.TCPServer):
            allow_reuse_address = True

        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                super().__init__(*args, directory=str(editor_dir), **kwargs)

            def log_message(self, format: str, *args: Any) -> None:
                # Suppress server logs
                pass

            def _proxy_request(self, method: str) -> bool:
                parsed = urllib.parse.urlparse(self.path)
                try:
                    request_path = _validated_proxy_path(parsed.path)
                except ValueError as exc:
                    self.send_error(400, str(exc))
                    return True

                # Serve slcli-config.json from temp directory
                if request_path == "/slcli-config.json" and method == "GET":
                    config_file = temp_path / "slcli-config.json"
                    if config_file.exists():
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(config_file.read_bytes())
                        return True
                    else:
                        self.send_error(404, "Config not found")
                        return True

                # Serve config.json (the DFF configuration) from temp directory
                if request_path == "/config.json" and method == "GET":
                    config_file = temp_path / "config.json"
                    if config_file.exists():
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(config_file.read_bytes())
                        return True
                    else:
                        self.send_error(404, "Config file not found")
                        return True

                try:
                    resolved_target = _resolve_proxy_target(method, request_path, parsed.query)
                except ValueError as exc:
                    self.send_error(400, str(exc))
                    return True

                if resolved_target is None:
                    return False

                target_path, target_params = resolved_target

                # Require per-session secret on all proxied routes
                req_secret = self.headers.get("X-Editor-Secret")
                if not secret or req_secret != secret:
                    self.send_error(403, "Forbidden: Missing or invalid editor secret")
                    return True

                target_url = _build_proxy_url(
                    origin_scheme=api_scheme,
                    origin_netloc=api_netloc,
                    target_path=target_path,
                )

                headers = dict(default_headers)
                data = None

                if method == "POST":
                    content_length = int(self.headers.get("Content-Length", "0"))
                    data = self.rfile.read(content_length) if content_length > 0 else b""
                    headers["Content-Type"] = self.headers.get("Content-Type", "application/json")

                try:
                    resp = requests.request(
                        method=method,
                        url=target_url,
                        headers=headers,
                        data=data,
                        params=target_params or None,
                        verify=ssl_verify,
                    )
                except requests.RequestException as exc:  # pragma: no cover
                    self.send_error(502, f"Proxy error: {exc}")
                    return True

                self.send_response(resp.status_code)
                content_type = resp.headers.get("Content-Type")
                if content_type:
                    self.send_header("Content-Type", content_type)
                self.end_headers()
                self.wfile.write(resp.content)
                return True

            def do_GET(self) -> None:  # noqa: N802
                if self._proxy_request("GET"):
                    return
                super().do_GET()

            def do_POST(self) -> None:  # noqa: N802
                if self._proxy_request("POST"):
                    return
                # SimpleHTTPRequestHandler lacks POST; return 405 when not proxied.
                self.send_error(405, "Method Not Allowed")

        try:
            with EditorTCPServer(("127.0.0.1", self.port), Handler) as httpd:
                server_url = f"http://127.0.0.1:{self.port}"

                # Start server in background thread
                server_thread = threading.Thread(target=httpd.serve_forever)
                server_thread.daemon = True
                server_thread.start()

                click.echo(f"✓ Starting Custom Fields editor at {server_url}")
                click.echo(f"✓ Loading editor from: {editor_dir}")

                if open_browser:
                    click.echo("✓ Opening in your default browser...")
                    webbrowser.open(server_url)

                click.echo("\nPress Ctrl+C to stop the editor server")

                try:
                    # Keep the server running
                    while True:
                        threading.Event().wait(1)
                except KeyboardInterrupt:
                    click.echo("\n✓ Editor server stopped")
                    httpd.shutdown()
                    httpd.server_close()
                    server_thread.join(timeout=2)

        except OSError as e:
            if "Address already in use" in str(e):
                click.echo(
                    f"✗ Port {self.port} is already in use. Try a different port with --port",
                    err=True,
                )
                sys.exit(ExitCodes.GENERAL_ERROR)
            else:
                raise


def launch_dff_editor(
    file: Optional[str] = None,
    port: int = 8080,
    open_browser: bool = True,
) -> None:
    """Launch the DFF web editor with specified configuration.

    Args:
        file: Optional JSON file to edit
        port: Port for local HTTP server
        open_browser: Whether to auto-open browser
    """
    editor = DFFWebEditor(port=port)
    editor.launch(file=file, open_browser=open_browser)
