"""Web editor utilities for DFF configuration editing."""

import http.server
import json
import shutil
import socketserver
import sys
import threading
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Optional, Any

import click
import requests

from .utils import ExitCodes, get_base_url, get_headers, get_ssl_verify, load_json_file


class DFFWebEditor:
    """Web-based editor for Dynamic Form Fields configurations."""

    def __init__(self, port: int = 8080, output_dir: str = "dff-editor"):
        """Initialize the DFF web editor.

        Args:
            port: Port number for the HTTP server
            output_dir: Directory name for editor files
        """
        self.port = port
        self.output_dir = Path(output_dir)

    def launch(self, file: Optional[str] = None, open_browser: bool = True) -> None:
        """Launch the web editor with optional file loading.

        Args:
            file: Optional JSON file to load initially
            open_browser: Whether to automatically open browser
        """
        try:
            self._create_editor_directory()
            initial_content = self._load_initial_content(file)
            self._create_editor_files(initial_content, file)
            self._write_editor_config()
            self._start_server(open_browser)
        except Exception as exc:
            click.echo(f"✗ Error starting editor: {exc}", err=True)
            sys.exit(ExitCodes.GENERAL_ERROR)

    def _create_editor_directory(self) -> None:
        """Create the editor directory structure."""
        self.output_dir.mkdir(exist_ok=True)

    def _load_initial_content(self, file: Optional[str]) -> str:
        """Load initial content from file or use default template.

        Args:
            file: Optional file path to load

        Returns:
            JSON string for initial editor content
        """
        if file and Path(file).exists():
            try:
                existing_data = load_json_file(file)
                return json.dumps(existing_data, indent=2)
            except Exception:
                return self._get_default_template()
        else:
            return self._get_default_template()

    def _get_default_template(self) -> str:
        """Get the default DFF configuration template."""
        return """{
  "configurations": [
    {
      "name": "Example Configuration",
      "workspace": "your-workspace-id",
      "resourceType": "workorder:workorder",
      "groupKeys": ["group1"],
      "properties": {}
    }
  ],
  "groups": [
    {
      "key": "group1",
      "workspace": "your-workspace-id",
      "name": "Example Group",
      "displayText": "Example Group",
      "fieldKeys": ["field1"],
      "properties": {}
    }
  ],
  "fields": [
    {
      "key": "field1",
      "workspace": "your-workspace-id",
      "name": "Example Field",
      "displayText": "Example Field",
      "fieldType": "STRING",
      "required": false,
      "validation": {},
      "properties": {}
    }
  ]
}"""

    def _create_editor_files(self, initial_content: str, file: Optional[str]) -> None:
        """Create or copy the editor assets into the output directory.

        Prefers copying the packaged `dff-editor` assets (Monaco-based editor).
        Falls back to the legacy generated HTML/JS if the assets are missing.

        Args:
            initial_content: Initial JSON content for the editor (used for legacy fallback)
            file: Optional source file name for display (used for legacy fallback)
        """
        source_dir = Path(__file__).resolve().parent.parent / "dff-editor"
        target_dir = self.output_dir.resolve()

        # If source and target are the same, assets are already in place (development mode)
        if source_dir.exists() and source_dir != target_dir:
            # Only copy the essential editor files
            essential_files = ["index.html", "editor.js", "README.md"]
            for filename in essential_files:
                source_file = source_dir / filename
                if source_file.exists():
                    target_file = target_dir / filename
                    shutil.copy2(source_file, target_file)
            return
        elif source_dir.exists() and source_dir == target_dir:
            # Already in the right place (development mode)
            return

        # Fallback to legacy generated assets if packaged files are unavailable.
        html_content = self._generate_html_content(initial_content, file)
        (self.output_dir / "index.html").write_text(html_content)
        readme_content = self._generate_readme_content()
        (self.output_dir / "README.md").write_text(readme_content)

    def _write_editor_config(self) -> None:
        """Write the editor configuration consumed by the frontend."""
        server_url = get_base_url().rstrip("/")
        config_path = self.output_dir / "slcli-config.json"
        config_path.write_text(json.dumps({"serverUrl": server_url}, indent=2))

    def _generate_html_content(self, initial_content: str, file: Optional[str]) -> str:
        """Generate the HTML editor content."""
        file_info = f"Editing: {file}" if file else "Mode: New Configuration"

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dynamic Form Fields Editor</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #333;
            border-bottom: 2px solid #007acc;
            padding-bottom: 10px;
        }}
        .notice {{
            background: #e3f2fd;
            border: 1px solid #2196f3;
            padding: 15px;
            border-radius: 4px;
            margin: 20px 0;
        }}
        .file-info {{
            background: #f0f0f0;
            padding: 15px;
            border-radius: 4px;
            margin: 10px 0;
            font-family: monospace;
        }}
        button {{
            background: #007acc;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 4px;
            cursor: pointer;
            margin: 5px;
        }}
        button:hover {{
            background: #005a9e;
        }}
        textarea {{
            width: 100%;
            height: 400px;
            font-family: monospace;
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 4px;
        }}
        .status {{
            margin-top: 20px;
            padding: 10px;
            border-radius: 4px;
        }}
        .status.success {{
            background: #d4edda;
            border: 1px solid #c3e6cb;
            color: #155724;
        }}
        .status.error {{
            background: #f8d7da;
            border: 1px solid #f5c6cb;
            color: #721c24;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Dynamic Form Fields Editor</h1>
        
        <div class="notice">
            <strong>🚧 Under Development</strong><br>
            This web-based editor for Dynamic Form Fields is currently under development.
            In the future, this will provide:
            <ul>
                <li>Visual configuration builder</li>
                <li>Field validation</li>
                <li>Real-time preview</li>
                <li>Schema validation</li>
                <li>Import/export functionality</li>
                <li>Save to file functionality</li>
            </ul>
        </div>
        
        <div class="file-info"><strong>{file_info}</strong></div>
        
        <div class="notice">
            <strong>📋 Resource Types</strong><br>
            The <code>resourceType</code> field must be one of these valid values:
            <ul>
                <li><code>workorder:workorder</code></li>
                <li><code>workorder:testplan</code></li>
                <li><code>asset:asset</code></li>
                <li><code>system:system</code></li>
                <li><code>testmonitor:product</code></li>
            </ul>
        </div>
        
        <h3>JSON Configuration</h3>
        <textarea id="jsonEditor" placeholder="Enter your Dynamic Form Fields configuration JSON here...">{initial_content}</textarea>
        
        <div>
            <button onclick="validateJson()">Validate JSON</button>
            <button onclick="formatJson()">Format JSON</button>
            <button onclick="downloadConfiguration()">Download JSON</button>
            <button onclick="loadExample()">Load Example</button>
        </div>
        
        <div id="status"></div>
    </div>
    
    <script>
        {self._get_javascript_content()}
    </script>
</body>
</html>"""

    def _get_javascript_content(self) -> str:
        """Get the JavaScript content for the editor."""
        return """
        function validateJson() {
            const textarea = document.getElementById('jsonEditor');
            const status = document.getElementById('status');
            try {
                JSON.parse(textarea.value);
                showStatus('✓ JSON is valid', 'success');
            } catch (e) {
                showStatus('✗ Invalid JSON: ' + e.message, 'error');
            }
        }
        
        function formatJson() {
            const textarea = document.getElementById('jsonEditor');
            const status = document.getElementById('status');
            try {
                const config = JSON.parse(textarea.value);
                textarea.value = JSON.stringify(config, null, 2);
                showStatus('✓ JSON formatted', 'success');
            } catch (e) {
                showStatus('✗ Cannot format: Invalid JSON', 'error');
            }
        }
        
        function downloadConfiguration() {
            const textarea = document.getElementById('jsonEditor');
            try {
                const config = JSON.parse(textarea.value);
                const blob = new Blob([JSON.stringify(config, null, 2)], { type: 'application/json' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'dff-configuration.json';
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
                showStatus('✓ Configuration downloaded', 'success');
            } catch (e) {
                showStatus('✗ Cannot download: Invalid JSON', 'error');
            }
        }
        
        function loadExample() {
            const exampleConfig = {
                "configurations": [
                    {
                        "name": "Sample Configuration",
                        "workspace": "your-workspace-id",
                        "resourceType": "TestResult",
                        "groupKeys": ["basicInfo", "measurements"],
                        "properties": {}
                    }
                ],
                "groups": [
                    {
                        "key": "basicInfo",
                        "workspace": "your-workspace-id",
                        "name": "Basic Information",
                        "displayText": "Basic Information",
                        "fieldKeys": ["deviceId", "operator"],
                        "properties": {}
                    }
                ],
                "fields": [
                    {
                        "key": "deviceId",
                        "workspace": "your-workspace-id",
                        "name": "Device ID",
                        "displayText": "Device Identifier",
                        "fieldType": "STRING",
                        "required": true,
                        "validation": {
                            "maxLength": 50
                        },
                        "properties": {}
                    }
                ]
            };
            
            document.getElementById('jsonEditor').value = JSON.stringify(exampleConfig, null, 2);
            showStatus('✓ Example configuration loaded', 'success');
        }
        
        function showStatus(message, type) {
            const status = document.getElementById('status');
            status.className = 'status ' + type;
            status.textContent = message;
            setTimeout(() => {
                status.className = 'status';
                status.textContent = '';
            }, 5000);
        }
        """

    def _generate_readme_content(self) -> str:
        """Generate README content for the editor directory."""
        return f"""# Dynamic Form Fields Editor

This directory contains a standalone web editor for SystemLink Dynamic Form Fields configurations.

## Files

- `index.html` - The main editor interface
- `README.md` - This file

## Usage

1. Start the editor server:
   ```
   slcli dff edit --output-dir {self.output_dir.name} --port {self.port}
   ```

2. Open your browser to: http://localhost:{self.port}

3. Edit your configuration in the JSON editor

4. Use the tools to validate, format, and download your configuration

## Configuration Structure

Dynamic Form Fields configurations consist of:

- **Configurations**: Top-level configuration objects that define how forms are structured
- **Groups**: Logical groupings of fields within a configuration
- **Fields**: Individual form fields with types, validation rules, and properties

### Resource Types

The `resourceType` field in configurations must be one of these valid values:

- `workorder:workorder`
- `workorder:testplan`
- `asset:asset`
- `system:system`
- `testmonitor:product`

See the example configuration in the editor for a sample structure.
"""

    def _start_server(self, open_browser: bool) -> None:
        """Start the HTTP server and optionally open browser.

        Args:
            open_browser: Whether to automatically open browser
        """
        output_dir = self.output_dir  # Capture for closure
        api_base = get_base_url().rstrip("/")
        default_headers = get_headers()
        ssl_verify = get_ssl_verify()

        class EditorTCPServer(socketserver.TCPServer):
            allow_reuse_address = True

        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs) -> None:  # type: ignore
                super().__init__(*args, directory=str(output_dir), **kwargs)

            def log_message(self, format: str, *args: Any) -> None:
                # Suppress server logs
                pass

            def _proxy_request(self, method: str) -> bool:
                parsed = urllib.parse.urlparse(self.path)
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
                except requests.RequestException as exc:  # pragma: no cover - network failure path
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
            with EditorTCPServer(("", self.port), Handler) as httpd:
                server_url = f"http://localhost:{self.port}"

                # Start server in background thread
                server_thread = threading.Thread(target=httpd.serve_forever)
                server_thread.daemon = True
                server_thread.start()

                click.echo(f"✓ Created editor files in: {self.output_dir.absolute()}")
                click.echo(f"✓ Starting Dynamic Form Fields editor at {server_url}")

                if open_browser:
                    click.echo("✓ Opening in your default browser...")
                    webbrowser.open(server_url)

                click.echo(f"\nEditor files created in: {self.output_dir.absolute()}")
                click.echo("- index.html (main editor)")
                click.echo("- README.md (documentation)")
                click.echo("\nPress Ctrl+C to stop the editor server")

                try:
                    # Keep the server running
                    while True:
                        threading.Event().wait(1)
                except KeyboardInterrupt:
                    click.echo("\n✓ Editor server stopped")
                    click.echo(f"✓ Editor files remain in: {self.output_dir.absolute()}")
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
    output_dir: str = "dff-editor",
    open_browser: bool = True,
) -> None:
    """Launch the DFF web editor with specified configuration.

    Args:
        file: Optional JSON file to edit
        port: Port for local HTTP server
        output_dir: Directory to create editor files in
        open_browser: Whether to auto-open browser
    """
    editor = DFFWebEditor(port=port, output_dir=output_dir)
    editor.launch(file=file, open_browser=open_browser)
