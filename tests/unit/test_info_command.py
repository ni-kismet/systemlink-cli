"""Unit tests for slcli info command."""

import json
import ssl
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

import slcli.main as main_module
from slcli.main import cli
from slcli.profiles import Profile


class TestInfoCommand:
    """Tests for the info command."""

    def test_info_command_table_format_sle(self, monkeypatch: Any) -> None:
        """Test info command with table format for SLE platform."""
        test_profile = Profile(
            name="test",
            server="https://demo-api.lifecyclesolutions.ni.com",
            api_key="test-key",
            web_url="https://demo.lifecyclesolutions.ni.com",
            platform="SLE",
        )
        mock_status = {
            "server_reachable": True,
            "auth_valid": True,
            "services": {"Auth": "ok", "Test Monitor": "ok", "Work Order": "ok"},
            "platform": "SLE",
        }

        with patch("slcli.profiles.get_active_profile") as mock_profile, patch(
            "slcli.utils.get_base_url"
        ) as mock_base_url, patch("slcli.utils.get_web_url") as mock_web_url, patch(
            "slcli.utils.get_api_key"
        ) as mock_api_key, patch(
            "slcli.platform.check_service_status", return_value=mock_status
        ):
            mock_profile.return_value = test_profile
            mock_base_url.return_value = "https://demo-api.lifecyclesolutions.ni.com"
            mock_web_url.return_value = "https://demo.lifecyclesolutions.ni.com"
            mock_api_key.return_value = "test-key"

            runner = CliRunner()
            result = runner.invoke(cli, ["info"])

        assert result.exit_code == 0
        assert "SystemLink CLI Info" in result.output
        assert "Connected" in result.output
        assert "SystemLink Enterprise" in result.output
        assert "Service Health" in result.output
        assert "Auth" in result.output
        assert "OK" in result.output

    def test_info_command_table_format_sls(self, monkeypatch: Any) -> None:
        """Test info command with table format for SLS platform."""
        test_profile = Profile(
            name="test",
            server="https://my-server.local",
            api_key="test-key",
            web_url="https://my-server.local",
            platform="SLS",
        )
        mock_status = {
            "server_reachable": True,
            "auth_valid": True,
            "services": {
                "Auth": "ok",
                "DataFrame": "not_found",
                "File": "ok",
                "Test Monitor": "ok",
                "Work Order": "not_found",
            },
            "file_query_endpoint": "query-files",
            "elasticsearch_available": False,
            "system_query_endpoint": "query-systems",
            "materialized_search_available": False,
            "platform": "SLS",
        }

        with patch("slcli.profiles.get_active_profile") as mock_profile, patch(
            "slcli.utils.get_base_url"
        ) as mock_base_url, patch("slcli.utils.get_web_url") as mock_web_url, patch(
            "slcli.utils.get_api_key"
        ) as mock_api_key, patch(
            "slcli.platform.check_service_status", return_value=mock_status
        ):
            mock_profile.return_value = test_profile
            mock_base_url.return_value = "https://my-server.local"
            mock_web_url.return_value = "https://my-server.local"
            mock_api_key.return_value = "test-key"

            runner = CliRunner()
            result = runner.invoke(cli, ["info"])

        assert result.exit_code == 0
        assert "SystemLink CLI Info" in result.output
        assert "Connected" in result.output
        assert "SystemLink Server" in result.output
        assert "Service Health" in result.output
        assert "DataFrame" in result.output
        assert "Work Order" in result.output
        assert "Not available" in result.output
        assert "System Query" in result.output
        assert "query-systems" in result.output
        assert "query-files" in result.output
        assert "Elasticsearch unavailable" not in result.output

    def test_info_command_json_format_sle(self, monkeypatch: Any) -> None:
        """Test info command with JSON format for SLE platform."""
        test_profile = Profile(
            name="test",
            server="https://demo-api.lifecyclesolutions.ni.com",
            api_key="test-key",
            web_url="https://demo.lifecyclesolutions.ni.com",
            platform="SLE",
        )
        mock_status = {
            "server_reachable": True,
            "auth_valid": True,
            "services": {"Auth": "ok", "Test Monitor": "ok", "Work Order": "ok"},
            "platform": "SLE",
        }

        with patch("slcli.profiles.get_active_profile") as mock_profile, patch(
            "slcli.utils.get_base_url"
        ) as mock_base_url, patch("slcli.utils.get_web_url") as mock_web_url, patch(
            "slcli.utils.get_api_key"
        ) as mock_api_key, patch(
            "slcli.platform.check_service_status", return_value=mock_status
        ):
            mock_profile.return_value = test_profile
            mock_base_url.return_value = "https://demo-api.lifecyclesolutions.ni.com"
            mock_web_url.return_value = "https://demo.lifecyclesolutions.ni.com"
            mock_api_key.return_value = "test-key"

            runner = CliRunner()
            result = runner.invoke(cli, ["info", "--format", "json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["platform"] == "SLE"
        assert output["logged_in"] is True
        assert output["services"]["Auth"] == "ok"

    def test_info_command_json_format_sls(self, monkeypatch: Any) -> None:
        """Test info command with JSON format for SLS platform."""
        test_profile = Profile(
            name="test",
            server="https://my-server.local",
            api_key="test-key",
            web_url="https://my-server.local",
            platform="SLS",
        )
        mock_status = {
            "server_reachable": True,
            "auth_valid": True,
            "services": {
                "Auth": "ok",
                "Test Monitor": "ok",
                "Work Order": "not_found",
            },
            "system_query_endpoint": "query-systems",
            "materialized_search_available": False,
            "platform": "SLS",
        }

        with patch("slcli.profiles.get_active_profile") as mock_profile, patch(
            "slcli.utils.get_base_url"
        ) as mock_base_url, patch("slcli.utils.get_web_url") as mock_web_url, patch(
            "slcli.utils.get_api_key"
        ) as mock_api_key, patch(
            "slcli.platform.check_service_status", return_value=mock_status
        ):
            mock_profile.return_value = test_profile
            mock_base_url.return_value = "https://my-server.local"
            mock_web_url.return_value = "https://my-server.local"
            mock_api_key.return_value = "test-key"

            runner = CliRunner()
            result = runner.invoke(cli, ["info", "-f", "json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["platform"] == "SLS"
        assert output["logged_in"] is True
        assert output["system_query_endpoint"] == "query-systems"
        assert "features" not in output

    def test_info_command_not_logged_in(self, monkeypatch: Any) -> None:
        """Test info command when not logged in."""
        with patch("slcli.profiles.get_active_profile") as mock_profile, patch(
            "slcli.utils.get_base_url"
        ) as mock_base_url, patch("slcli.utils.get_web_url") as mock_web_url, patch(
            "slcli.utils.get_api_key"
        ) as mock_api_key, patch(
            "slcli.platform._get_keyring_config"
        ) as mock_keyring:
            mock_profile.return_value = None
            mock_base_url.side_effect = Exception("Not configured")
            mock_web_url.side_effect = Exception("Not configured")
            mock_api_key.side_effect = Exception("Not configured")
            mock_keyring.return_value = {}

            runner = CliRunner()
            result = runner.invoke(cli, ["info"])

        assert result.exit_code == 0
        assert "Not logged in" in result.output
        assert "Unknown" in result.output

    def test_info_command_server_unreachable(self, monkeypatch: Any) -> None:
        """Test info command shows unreachable when server cannot be contacted."""
        test_profile = Profile(
            name="test",
            server="https://offline.example.com",
            api_key="test-key",
            web_url="https://offline.example.com",
            platform="SLS",
        )
        mock_status = {
            "server_reachable": False,
            "auth_valid": None,
            "services": {"Auth": "unreachable", "Test Monitor": "unreachable"},
            "platform": "unreachable",
        }

        with patch("slcli.profiles.get_active_profile") as mock_profile, patch(
            "slcli.utils.get_base_url"
        ) as mock_base_url, patch("slcli.utils.get_web_url") as mock_web_url, patch(
            "slcli.utils.get_api_key"
        ) as mock_api_key, patch(
            "slcli.platform.check_service_status", return_value=mock_status
        ):
            mock_profile.return_value = test_profile
            mock_base_url.return_value = "https://offline.example.com"
            mock_web_url.return_value = "https://offline.example.com"
            mock_api_key.return_value = "test-key"

            runner = CliRunner()
            result = runner.invoke(cli, ["info"])

        assert result.exit_code == 0
        assert "Server unreachable" in result.output

    def test_info_command_api_key_unauthorized(self, monkeypatch: Any) -> None:
        """Test info command shows unauthorized when API key is invalid."""
        test_profile = Profile(
            name="test",
            server="https://api.example.com",
            api_key="bad-key",
            web_url="https://example.com",
            platform="SLE",
        )
        mock_status = {
            "server_reachable": True,
            "auth_valid": False,
            "services": {"Auth": "unauthorized", "Test Monitor": "unauthorized"},
            "platform": "SLE",
        }

        with patch("slcli.profiles.get_active_profile") as mock_profile, patch(
            "slcli.utils.get_base_url"
        ) as mock_base_url, patch("slcli.utils.get_web_url") as mock_web_url, patch(
            "slcli.utils.get_api_key"
        ) as mock_api_key, patch(
            "slcli.platform.check_service_status", return_value=mock_status
        ):
            mock_profile.return_value = test_profile
            mock_base_url.return_value = "https://api.example.com"
            mock_web_url.return_value = "https://example.com"
            mock_api_key.return_value = "bad-key"

            runner = CliRunner()
            result = runner.invoke(cli, ["info"])

        assert result.exit_code == 0
        assert "API key unauthorized" in result.output
        assert "Unauthorized" in result.output

    def test_info_command_debug_outputs_connection_diagnostics(self) -> None:
        """Test info --debug emits structured connection diagnostics."""
        test_profile = Profile(
            name="test",
            server="https://api.example.com",
            api_key="test-key",
            web_url="https://example.com",
            platform="SLE",
        )
        mock_status = {
            "server_reachable": True,
            "auth_valid": True,
            "services": {"Auth": "ok"},
            "platform": "SLE",
        }
        debug_rows = [
            ("SSL Verify", "enabled"),
            ("CA Source", "system (reason=injected:requests)"),
            ("Proxy HTTPS", "unset"),
            ("TLS Version", "TLSv1.3"),
            ("Leaf Cert Subject", "commonName=api.example.com"),
        ]

        with patch("slcli.profiles.get_active_profile") as mock_profile, patch(
            "slcli.utils.get_base_url"
        ) as mock_base_url, patch("slcli.utils.get_web_url") as mock_web_url, patch(
            "slcli.utils.get_api_key"
        ) as mock_api_key, patch(
            "slcli.platform.check_service_status", return_value=mock_status
        ), patch.object(
            main_module, "_collect_info_debug_rows", return_value=debug_rows
        ):
            mock_profile.return_value = test_profile
            mock_base_url.return_value = "https://api.example.com"
            mock_web_url.return_value = "https://example.com"
            mock_api_key.return_value = "test-key"

            runner = CliRunner()
            result = runner.invoke(cli, ["info", "--debug"])

        assert result.exit_code == 0
        # Diagnostics are emitted to stderr; CliRunner mixes stderr into output by default.
        assert "Debug Connection Diagnostics:" in result.output
        assert "SSL Verify: enabled" in result.output
        assert "CA Source: system (reason=injected:requests)" in result.output
        assert "TLS Version: TLSv1.3" in result.output
        assert "Leaf Cert Subject: commonName=api.example.com" in result.output

    def test_info_command_skip_health(self, monkeypatch: Any) -> None:
        """Test info command with --skip-health skips service checks."""
        test_profile = Profile(
            name="test",
            server="https://api.example.com",
            api_key="test-key",
            web_url="https://example.com",
            platform="SLE",
        )

        with patch("slcli.profiles.get_active_profile") as mock_profile, patch(
            "slcli.utils.get_base_url"
        ) as mock_base_url, patch("slcli.utils.get_web_url") as mock_web_url, patch(
            "slcli.utils.get_api_key"
        ) as mock_api_key, patch(
            "slcli.platform.check_service_status"
        ) as mock_check:
            mock_profile.return_value = test_profile
            mock_base_url.return_value = "https://api.example.com"
            mock_web_url.return_value = "https://example.com"
            mock_api_key.return_value = "test-key"

            runner = CliRunner()
            result = runner.invoke(cli, ["info", "--skip-health"])

        assert result.exit_code == 0
        assert "SystemLink Enterprise" in result.output
        assert "Service Health" not in result.output
        mock_check.assert_not_called()

    def test_info_command_reports_file_query_fallback(self, monkeypatch: Any) -> None:
        """Test info command shows query-files-linq when Elasticsearch is unavailable."""
        test_profile = Profile(
            name="test",
            server="https://my-server.local",
            api_key="test-key",
            web_url="https://my-server.local",
            platform="SLS",
        )
        mock_status = {
            "server_reachable": True,
            "auth_valid": True,
            "services": {
                "Auth": "ok",
                "Test Monitor": "ok",
                "File": "fallback",
                "Work Order": "not_found",
            },
            "file_query_endpoint": "query-files-linq",
            "elasticsearch_available": False,
            "platform": "SLS",
        }

        with patch("slcli.profiles.get_active_profile") as mock_profile, patch(
            "slcli.utils.get_base_url"
        ) as mock_base_url, patch("slcli.utils.get_web_url") as mock_web_url, patch(
            "slcli.utils.get_api_key"
        ) as mock_api_key, patch(
            "slcli.platform.check_service_status", return_value=mock_status
        ):
            mock_profile.return_value = test_profile
            mock_base_url.return_value = "https://my-server.local"
            mock_web_url.return_value = "https://my-server.local"
            mock_api_key.return_value = "test-key"

            runner = CliRunner()
            result = runner.invoke(cli, ["info"])

        assert result.exit_code == 0
        assert "query-files-linq" in result.output
        assert "Elasticsearch unavailable" in result.output
        assert "Fallback (no Elasticsearch)" in result.output

    def test_info_command_json_reports_file_query_fallback(self, monkeypatch: Any) -> None:
        """Test info JSON includes file query capability details."""
        test_profile = Profile(
            name="test",
            server="https://my-server.local",
            api_key="test-key",
            web_url="https://my-server.local",
            platform="SLS",
        )
        mock_status = {
            "server_reachable": True,
            "auth_valid": True,
            "services": {
                "Auth": "ok",
                "Test Monitor": "ok",
                "File": "fallback",
                "Work Order": "not_found",
            },
            "file_query_endpoint": "query-files-linq",
            "elasticsearch_available": False,
            "platform": "SLS",
        }

        with patch("slcli.profiles.get_active_profile") as mock_profile, patch(
            "slcli.utils.get_base_url"
        ) as mock_base_url, patch("slcli.utils.get_web_url") as mock_web_url, patch(
            "slcli.utils.get_api_key"
        ) as mock_api_key, patch(
            "slcli.platform.check_service_status", return_value=mock_status
        ):
            mock_profile.return_value = test_profile
            mock_base_url.return_value = "https://my-server.local"
            mock_web_url.return_value = "https://my-server.local"
            mock_api_key.return_value = "test-key"

            runner = CliRunner()
            result = runner.invoke(cli, ["info", "--format", "json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["file_query_endpoint"] == "query-files-linq"
        assert output["elasticsearch_available"] is False
        assert output["services"]["File"] == "fallback"


class TestGetCaSourceDisplay:
    """Tests for _get_ca_source_display helper."""

    def test_os_trust_injected(self) -> None:
        """Test CA source when OS trust is injected."""
        with patch.object(main_module, "OS_TRUST_INJECTED", True), patch.object(
            main_module, "OS_TRUST_REASON", "injected:requests"
        ):
            assert main_module._get_ca_source_display() == "system (reason=injected:requests)"

    def test_custom_pem(self, monkeypatch: Any) -> None:
        """Test CA source when custom PEM is set via env."""
        with patch.object(main_module, "OS_TRUST_INJECTED", False):
            monkeypatch.setenv("REQUESTS_CA_BUNDLE", "/path/to/ca.pem")
            assert main_module._get_ca_source_display() == "custom-pem (/path/to/ca.pem)"

    def test_certifi_fallback(self, monkeypatch: Any) -> None:
        """Test CA source falls back to certifi."""
        with patch.object(main_module, "OS_TRUST_INJECTED", False), patch.object(
            main_module, "OS_TRUST_REASON", "error:ImportError"
        ):
            monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
            monkeypatch.delenv("SSL_CERT_FILE", raising=False)
            assert main_module._get_ca_source_display() == "certifi (reason=error:ImportError)"


class TestBuildTlsDebugContext:
    """Tests for _build_tls_debug_context helper."""

    def test_verify_disabled_returns_unverified_context(self) -> None:
        """Test that ssl_verify=False returns a context with no verification."""
        ctx = main_module._build_tls_debug_context(False)
        assert isinstance(ctx, ssl.SSLContext)
        assert ctx.verify_mode == ssl.CERT_NONE
        assert ctx.check_hostname is False

    def test_verify_enabled_returns_default_context(self, monkeypatch: Any) -> None:
        """Test that ssl_verify=True returns a default context."""
        monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
        monkeypatch.delenv("SSL_CERT_FILE", raising=False)
        ctx = main_module._build_tls_debug_context(True)
        assert isinstance(ctx, ssl.SSLContext)
        assert ctx.verify_mode == ssl.CERT_REQUIRED

    def test_custom_pem_uses_cafile(self, monkeypatch: Any) -> None:
        """Test that REQUESTS_CA_BUNDLE overrides the CA file."""
        monkeypatch.setenv("REQUESTS_CA_BUNDLE", "/nonexistent/ca.pem")
        with pytest.raises(FileNotFoundError):
            main_module._build_tls_debug_context(True)


class TestFormatCertName:
    """Tests for _format_cert_name helper."""

    def test_valid_subject(self) -> None:
        """Test formatting a valid certificate subject."""
        name = ((("commonName", "example.com"),),)
        assert main_module._format_cert_name(name) == "commonName=example.com"

    def test_multi_rdn(self) -> None:
        """Test formatting with multiple relative distinguished names."""
        name = ((("organizationName", "Acme"),), (("commonName", "example.com"),))
        assert (
            main_module._format_cert_name(name) == "organizationName=Acme, commonName=example.com"
        )

    def test_non_tuple_returns_unavailable(self) -> None:
        """Test non-tuple input returns Unavailable."""
        assert main_module._format_cert_name("not a tuple") == "Unavailable"

    def test_empty_tuple_returns_unavailable(self) -> None:
        """Test empty tuple returns Unavailable."""
        assert main_module._format_cert_name(()) == "Unavailable"

    def test_malformed_inner_skipped(self) -> None:
        """Test malformed inner entries are skipped."""
        name = ((42,), (("commonName", "ok"),))  # type: ignore[arg-type]
        assert main_module._format_cert_name(name) == "commonName=ok"


class TestFormatSubjectAltNames:
    """Tests for _format_subject_alt_names helper."""

    def test_valid_sans(self) -> None:
        """Test formatting valid SANs."""
        sans = (("DNS", "example.com"), ("DNS", "www.example.com"))
        assert main_module._format_subject_alt_names(sans) == "DNS=example.com, DNS=www.example.com"

    def test_non_tuple_returns_unavailable(self) -> None:
        """Test non-tuple input returns Unavailable."""
        assert main_module._format_subject_alt_names("not a tuple") == "Unavailable"

    def test_empty_tuple_returns_unavailable(self) -> None:
        """Test empty tuple returns Unavailable."""
        assert main_module._format_subject_alt_names(()) == "Unavailable"

    def test_truncation_at_5_valid_entries(self) -> None:
        """Test that SANs are truncated after 5 valid entries."""
        sans = tuple(("DNS", f"host{i}.example.com") for i in range(8))
        result = main_module._format_subject_alt_names(sans)
        assert "host4.example.com" in result
        assert "host5.example.com" not in result
        assert "(+3 more)" in result

    def test_malformed_entries_skipped_without_affecting_limit(self) -> None:
        """Test that malformed SANs don't consume display slots."""
        sans = (
            ("not-valid",),  # malformed: wrong length
            ("DNS", "a.example.com"),
            (123, "b.example.com"),  # malformed: non-string key
            ("DNS", "c.example.com"),
            ("DNS", "d.example.com"),
            ("DNS", "e.example.com"),
            ("DNS", "f.example.com"),
            ("DNS", "g.example.com"),
        )
        result = main_module._format_subject_alt_names(sans)  # type: ignore[arg-type]
        # 5 valid entries shown, 1 extra
        assert "a.example.com" in result
        assert "f.example.com" in result
        assert "(+1 more)" in result


class TestGetProxyDebugRows:
    """Tests for _get_proxy_debug_rows helper."""

    def test_no_proxy_env(self, monkeypatch: Any) -> None:
        """Test output when no proxy environment variables are set."""
        for var in (
            "HTTPS_PROXY",
            "https_proxy",
            "HTTP_PROXY",
            "http_proxy",
            "NO_PROXY",
            "no_proxy",
        ):
            monkeypatch.delenv(var, raising=False)
        rows = main_module._get_proxy_debug_rows("https://example.com")
        row_dict = dict(rows)
        assert row_dict["Proxy HTTPS"] == "unset"
        assert row_dict["Proxy HTTP"] == "unset"
        assert row_dict["Proxy NO_PROXY"] == "unset"
        assert row_dict["Proxy Active"] == "no"

    def test_proxy_env_set(self, monkeypatch: Any) -> None:
        """Test output when proxy environment variables are set."""
        monkeypatch.setenv("HTTPS_PROXY", "http://proxy:8080")
        monkeypatch.setenv("HTTP_PROXY", "http://proxy:8080")
        monkeypatch.setenv("NO_PROXY", "localhost")
        rows = main_module._get_proxy_debug_rows("https://example.com")
        row_dict = dict(rows)
        assert row_dict["Proxy HTTPS"] == "set"
        assert row_dict["Proxy HTTP"] == "set"
        assert row_dict["Proxy NO_PROXY"] == "set"


class TestProbeTlsConnection:
    """Tests for _probe_tls_connection helper."""

    def test_not_configured(self) -> None:
        """Test probe skips when API URL is not configured."""
        rows = main_module._probe_tls_connection("Not configured", True)
        assert rows == [("TLS Probe", "Skipped (API URL not configured)")]

    def test_empty_url(self) -> None:
        """Test probe skips when API URL is empty."""
        rows = main_module._probe_tls_connection("", True)
        assert rows == [("TLS Probe", "Skipped (API URL not configured)")]

    def test_non_https(self) -> None:
        """Test probe skips for non-HTTPS URLs."""
        rows = main_module._probe_tls_connection("http://example.com", True)
        assert rows == [("TLS Probe", "Skipped (non-HTTPS API URL)")]

    def test_unparseable_host(self) -> None:
        """Test probe skips when hostname cannot be parsed."""
        rows = main_module._probe_tls_connection("https://", True)
        assert rows == [("TLS Probe", "Skipped (unable to parse host)")]

    def test_proxy_configured(self, monkeypatch: Any) -> None:
        """Test probe skips when proxy is configured for the target URL."""
        monkeypatch.setenv("HTTPS_PROXY", "http://proxy:8080")
        rows = main_module._probe_tls_connection("https://example.com", True)
        assert rows == [("TLS Probe", "Skipped (proxy-configured environment)")]

    def test_connection_error(self, monkeypatch: Any) -> None:
        """Test probe reports connection errors."""
        for var in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
            monkeypatch.delenv(var, raising=False)
        with patch("socket.create_connection", side_effect=OSError("Connection refused")):
            rows = main_module._probe_tls_connection("https://unreachable.example.com", True)
        row_dict = dict(rows)
        assert row_dict["TLS Target"] == "unreachable.example.com:443"
        assert "OSError" in row_dict["TLS Probe Error"]

    def test_successful_handshake(self, monkeypatch: Any) -> None:
        """Test probe returns TLS details on successful handshake."""
        for var in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
            monkeypatch.delenv(var, raising=False)

        mock_tls = MagicMock()
        mock_tls.getpeercert.side_effect = lambda binary_form=False: (
            {
                "subject": ((("commonName", "example.com"),),),
                "issuer": ((("organizationName", "CA"),),),
                "subjectAltName": (("DNS", "example.com"),),
                "notBefore": "Jan  1 00:00:00 2025 GMT",
                "notAfter": "Dec 31 23:59:59 2026 GMT",
            }
            if not binary_form
            else b"\x00\x01\x02"
        )
        mock_tls.version.return_value = "TLSv1.3"
        mock_tls.cipher.return_value = ("TLS_AES_256_GCM_SHA384", "TLSv1.3", 256)
        mock_tls.__enter__ = MagicMock(return_value=mock_tls)
        mock_tls.__exit__ = MagicMock(return_value=False)

        mock_tcp = MagicMock()
        mock_tcp.__enter__ = MagicMock(return_value=mock_tcp)
        mock_tcp.__exit__ = MagicMock(return_value=False)

        with patch("socket.create_connection", return_value=mock_tcp), patch.object(
            main_module, "_build_tls_debug_context"
        ) as mock_ctx:
            mock_ctx.return_value.wrap_socket.return_value = mock_tls
            rows = main_module._probe_tls_connection("https://example.com", True)

        row_dict = dict(rows)
        assert row_dict["TLS Target"] == "example.com:443"
        assert row_dict["TLS Version"] == "TLSv1.3"
        assert row_dict["TLS Cipher"] == "TLS_AES_256_GCM_SHA384"
        assert "commonName=example.com" in row_dict["Leaf Cert Subject"]
        assert "organizationName=CA" in row_dict["Leaf Cert Issuer"]
        assert "DNS=example.com" in row_dict["Leaf Cert SANs"]
        assert row_dict["Leaf Cert Valid From"] == "Jan  1 00:00:00 2025 GMT"
        assert "Leaf Cert SHA256" in row_dict


class TestCollectInfoDebugRows:
    """Tests for _collect_info_debug_rows helper."""

    def test_includes_ssl_and_ca_rows(self, monkeypatch: Any) -> None:
        """Test that the collected rows include SSL verify and CA source."""
        for var in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
            monkeypatch.delenv(var, raising=False)

        with patch.object(main_module, "OS_TRUST_INJECTED", False), patch.object(
            main_module, "OS_TRUST_REASON", "not-attempted"
        ), patch("slcli.utils.get_ssl_verify", return_value=True), patch.object(
            main_module,
            "_probe_tls_connection",
            return_value=[("TLS Probe", "Skipped (non-HTTPS API URL)")],
        ):
            monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
            monkeypatch.delenv("SSL_CERT_FILE", raising=False)
            rows = main_module._collect_info_debug_rows("http://localhost:8000")

        row_dict = dict(rows)
        assert row_dict["SSL Verify"] == "enabled"
        assert "certifi" in row_dict["CA Source"]
        assert "Proxy HTTPS" in row_dict
