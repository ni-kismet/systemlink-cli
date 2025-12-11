"""Unit tests for slcli.platform module."""

import json
from unittest.mock import MagicMock, patch

import pytest

from slcli.platform import (
    PLATFORM_SLE,
    PLATFORM_SLS,
    PLATFORM_UNKNOWN,
    detect_platform,
    get_platform,
    get_platform_info,
    has_feature,
    require_feature,
    PLATFORM_FEATURES,
)


class TestDetectPlatform:
    """Tests for platform detection logic."""

    def test_detect_platform_sle_workorder_endpoint_available(self) -> None:
        """Test that SLE is detected when workorder endpoint returns 200."""
        with patch("slcli.platform.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_post.return_value = mock_response

            result = detect_platform("https://api.example.com", "test-key")

            assert result == PLATFORM_SLE
            mock_post.assert_called_once()

    def test_detect_platform_sle_workorder_endpoint_bad_request(self) -> None:
        """Test SLE detected when workorder endpoint returns 400 (exists but bad request)."""
        with patch("slcli.platform.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 400
            mock_post.return_value = mock_response

            result = detect_platform("https://api.example.com", "test-key")

            assert result == PLATFORM_SLE

    def test_detect_platform_sls_workorder_endpoint_not_found(self) -> None:
        """Test that SLS is detected when workorder endpoint returns 404."""
        with patch("slcli.platform.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_post.return_value = mock_response

            result = detect_platform("https://api.example.com", "test-key")

            assert result == PLATFORM_SLS

    def test_detect_platform_sle_url_pattern_systemlink_io(self) -> None:
        """Test that SLE is detected from api.systemlink.io URL pattern."""
        import requests as req_module

        with patch("slcli.platform.requests.post") as mock_post:
            # Simulate connection error to fall through to URL pattern matching
            mock_post.side_effect = req_module.RequestException("Connection failed")

            # api.systemlink.io is the SLE production URL
            result = detect_platform("https://api.systemlink.io", "test-key")

            assert result == PLATFORM_SLE

    def test_detect_platform_sls_for_on_prem_systemlink_io_subdomain(self) -> None:
        """Test that SLS is detected for on-prem servers using systemlink.io subdomains."""
        import requests as req_module

        with patch("slcli.platform.requests.post") as mock_post:
            # Simulate connection error to fall through to URL pattern matching
            mock_post.side_effect = req_module.RequestException("Connection failed")

            # On-prem servers may use custom *.systemlink.io subdomains
            result = detect_platform("https://base.systemlink.io", "test-key")

            assert result == PLATFORM_SLS

    def test_detect_platform_sle_url_pattern_lifecyclesolutions(self) -> None:
        """Test that SLE is detected from lifecyclesolutions URL pattern."""
        import requests as req_module

        with patch("slcli.platform.requests.post") as mock_post:
            mock_post.side_effect = req_module.RequestException("Connection failed")

            result = detect_platform("https://demo-api.lifecyclesolutions.ni.com", "test-key")

            assert result == PLATFORM_SLE

    def test_detect_platform_sls_unknown_domain(self) -> None:
        """Test that SLS is detected for unknown/custom domains."""
        import requests as req_module

        with patch("slcli.platform.requests.post") as mock_post:
            mock_post.side_effect = req_module.RequestException("Connection failed")

            result = detect_platform("https://my-server.company.local", "test-key")

            assert result == PLATFORM_SLS


class TestGetPlatform:
    """Tests for get_platform function."""

    def test_get_platform_from_keyring_sle(self) -> None:
        """Test getting SLE platform from keyring config."""
        config = {"api_url": "https://demo.systemlink.io", "platform": "SLE"}

        with patch("slcli.platform.keyring.get_password") as mock_keyring:
            mock_keyring.return_value = json.dumps(config)

            result = get_platform()

            assert result == PLATFORM_SLE

    def test_get_platform_from_keyring_sls(self) -> None:
        """Test getting SLS platform from keyring config."""
        config = {"api_url": "https://my-server.local", "platform": "SLS"}

        with patch("slcli.platform.keyring.get_password") as mock_keyring:
            mock_keyring.return_value = json.dumps(config)

            result = get_platform()

            assert result == PLATFORM_SLS

    def test_get_platform_unknown_when_not_configured(self) -> None:
        """Test that UNKNOWN is returned when keyring has no config."""
        with patch("slcli.platform.keyring.get_password") as mock_keyring:
            mock_keyring.return_value = None

            result = get_platform()

            assert result == PLATFORM_UNKNOWN

    def test_get_platform_unknown_when_platform_not_in_config(self) -> None:
        """Test that UNKNOWN is returned when platform not in config."""
        config = {"api_url": "https://demo.systemlink.io"}

        with patch("slcli.platform.keyring.get_password") as mock_keyring:
            mock_keyring.return_value = json.dumps(config)

            result = get_platform()

            assert result == PLATFORM_UNKNOWN


class TestHasFeature:
    """Tests for has_feature function."""

    def test_has_feature_sle_dff_available(self) -> None:
        """Test that DFF is available on SLE."""
        config = {"platform": "SLE"}

        with patch("slcli.platform.keyring.get_password") as mock_keyring:
            mock_keyring.return_value = json.dumps(config)

            result = has_feature("dynamic_form_fields")

            assert result is True

    def test_has_feature_sls_dff_not_available(self) -> None:
        """Test that DFF is not available on SLS."""
        config = {"platform": "SLS"}

        with patch("slcli.platform.keyring.get_password") as mock_keyring:
            mock_keyring.return_value = json.dumps(config)

            result = has_feature("dynamic_form_fields")

            assert result is False

    def test_has_feature_unknown_platform_returns_true(self) -> None:
        """Test that features are allowed when platform is unknown (graceful degradation)."""
        with patch("slcli.platform.keyring.get_password") as mock_keyring:
            mock_keyring.return_value = None

            result = has_feature("dynamic_form_fields")

            assert result is True

    def test_has_feature_unknown_feature_returns_true(self) -> None:
        """Test that unknown features default to available."""
        config = {"platform": "SLE"}

        with patch("slcli.platform.keyring.get_password") as mock_keyring:
            mock_keyring.return_value = json.dumps(config)

            result = has_feature("unknown_feature")

            assert result is True


class TestRequireFeature:
    """Tests for require_feature function."""

    def test_require_feature_available_does_not_exit(self) -> None:
        """Test that require_feature does not exit when feature is available."""
        config = {"platform": "SLE"}

        with patch("slcli.platform.keyring.get_password") as mock_keyring:
            mock_keyring.return_value = json.dumps(config)

            # Should not raise
            require_feature("dynamic_form_fields")

    def test_require_feature_not_available_exits(self) -> None:
        """Test that require_feature exits when feature is not available."""
        config = {"platform": "SLS"}

        with patch("slcli.platform.keyring.get_password") as mock_keyring:
            mock_keyring.return_value = json.dumps(config)

            with pytest.raises(SystemExit) as exc_info:
                require_feature("dynamic_form_fields")

            assert exc_info.value.code == 2  # INVALID_INPUT


class TestGetPlatformInfo:
    """Tests for get_platform_info function."""

    def test_get_platform_info_sle(self) -> None:
        """Test getting platform info for SLE."""
        config = {
            "api_url": "https://demo-api.lifecyclesolutions.ni.com",
            "web_url": "https://demo.lifecyclesolutions.ni.com",
            "api_key": "test-key",
            "platform": "SLE",
        }

        with patch("slcli.platform.keyring.get_password") as mock_keyring:
            mock_keyring.return_value = json.dumps(config)

            result = get_platform_info()

            assert result["platform"] == "SLE"
            assert result["platform_display"] == "SystemLink Enterprise (Cloud)"
            assert result["logged_in"] is True
            assert "features" in result
            assert result["features"]["Dynamic Form Fields"] is True

    def test_get_platform_info_sls(self) -> None:
        """Test getting platform info for SLS."""
        config = {
            "api_url": "https://my-server.local",
            "web_url": "https://my-server.local",
            "api_key": "test-key",
            "platform": "SLS",
        }

        with patch("slcli.platform.keyring.get_password") as mock_keyring:
            mock_keyring.return_value = json.dumps(config)

            result = get_platform_info()

            assert result["platform"] == "SLS"
            assert result["platform_display"] == "SystemLink Server (On-Premises)"
            assert result["logged_in"] is True
            assert "features" in result
            assert result["features"]["Dynamic Form Fields"] is False

    def test_get_platform_info_not_logged_in(self) -> None:
        """Test getting platform info when not logged in."""
        with patch("slcli.platform.keyring.get_password") as mock_keyring:
            mock_keyring.return_value = None

            result = get_platform_info()

            assert result["logged_in"] is False
            assert result["platform"] == PLATFORM_UNKNOWN


class TestPlatformFeatureMatrix:
    """Tests to validate the platform feature matrix."""

    def test_sle_has_all_cloud_features(self) -> None:
        """Test that SLE has all cloud-only features enabled."""
        sle_features = PLATFORM_FEATURES[PLATFORM_SLE]

        assert sle_features["dynamic_form_fields"] is True
        assert sle_features["function_execution"] is True
        assert sle_features["workorder_service"] is True
        assert sle_features["templates"] is True
        assert sle_features["workflows"] is True

    def test_sls_does_not_have_cloud_features(self) -> None:
        """Test that SLS does not have cloud-only features."""
        sls_features = PLATFORM_FEATURES[PLATFORM_SLS]

        assert sls_features["dynamic_form_fields"] is False
        assert sls_features["function_execution"] is False
        assert sls_features["workorder_service"] is False
        assert sls_features["templates"] is False
        assert sls_features["workflows"] is False
