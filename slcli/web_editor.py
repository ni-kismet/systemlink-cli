"""Web editor utilities for DFF configuration editing."""

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


class DFFWebEditor:
    """Web-based editor for Dynamic Form Fields configurations."""

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
            file: Optional initial file to load (currently unused by frontend)
        """
        config: dict[str, Any] = {
            "serverUrl": get_base_url().rstrip("/"),
            "secret": getattr(self, "_secret", None),
        }

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

                # Serve slcli-config.json from temp directory
                if parsed.path == "/slcli-config.json" and method == "GET":
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

                # Handle API proxying
                path_map = {
                    "/api/dff/configurations": "/nidynamicformfields/v1/configurations",
                    "/api/dff/update-configurations": "/nidynamicformfields/v1/update-configurations",
                }

                if parsed.path in path_map:
                    target_path = path_map[parsed.path]
                elif parsed.path.startswith("/nidynamicformfields/v1/"):
                    target_path = parsed.path
                else:
                    return False

                # Require per-session secret on all proxied routes
                req_secret = self.headers.get("X-Editor-Secret")
                if not secret or req_secret != secret:
                    self.send_error(403, "Forbidden: Missing or invalid editor secret")
                    return True

                target_url = f"{api_base}{target_path}"
                if parsed.query:
                    target_url = f"{target_url}?{parsed.query}"

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

                click.echo(f"✓ Starting Dynamic Form Fields editor at {server_url}")
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
