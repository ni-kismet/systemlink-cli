"""Unit tests for slcli.platform module."""

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests as req_module
from slcli.platform import (
    PLATFORM_SLE,
    PLATFORM_SLS,
    PLATFORM_UNKNOWN,
    PLATFORM_UNREACHABLE,
    check_service_status,
    clear_platform_cache,
    detect_platform,
    get_platform,
    get_platform_info,
    has_feature,
    require_feature,
    PLATFORM_FEATURES,
)


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    """Clear the platform cache before each test."""
    clear_platform_cache()


class TestDetectPlatform:
    """Tests for platform detection via check_service_status."""

    def test_detect_platform_sle_when_workorder_ok(self) -> None:
        """Test SLE detected when check_service_status reports workorder OK."""
        with patch("slcli.platform.check_service_status") as mock_check:
            mock_check.return_value = {
                "server_reachable": True,
                "auth_valid": True,
                "services": {"Work Order": "ok"},
                "platform": PLATFORM_SLE,
            }
            assert detect_platform("https://api.example.com", "key") == PLATFORM_SLE

    def test_detect_platform_sls_when_workorder_not_found(self) -> None:
        """Test SLS detected when workorder endpoint returns 404."""
        with patch("slcli.platform.check_service_status") as mock_check:
            mock_check.return_value = {
                "server_reachable": True,
                "auth_valid": True,
                "services": {"Work Order": "not_found"},
                "platform": PLATFORM_SLS,
            }
            assert detect_platform("https://my-server.local", "key") == PLATFORM_SLS

    def test_detect_platform_unreachable_when_no_connection(self) -> None:
        """Test UNREACHABLE when server cannot be reached."""
        with patch("slcli.platform.check_service_status") as mock_check:
            mock_check.return_value = {
                "server_reachable": False,
                "auth_valid": None,
                "services": {},
                "platform": PLATFORM_UNREACHABLE,
            }
            assert detect_platform("https://offline.example.com", "key") == PLATFORM_UNREACHABLE


def _make_mock_response(status_code: int) -> MagicMock:
    """Helper to create a mock requests response."""
    resp = MagicMock()
    resp.status_code = status_code
    return resp


class TestCheckServiceStatus:
    """Tests for check_service_status function."""

    def _mock_requests(self, responses: dict[str, Any]) -> tuple[MagicMock, MagicMock]:
        """Create mock get/post that return status codes based on URL substring.

        responses maps a URL substring to either a status_code int or an exception.
        """
        mock_get = MagicMock()
        mock_post = MagicMock()

        def side_effect_get(url: str, **kwargs: Any) -> MagicMock:
            for pattern, result in responses.items():
                if pattern in url:
                    if isinstance(result, Exception):
                        raise result
                    return _make_mock_response(result)
            return _make_mock_response(200)

        def side_effect_post(url: str, **kwargs: Any) -> MagicMock:
            for pattern, result in responses.items():
                if pattern in url:
                    if isinstance(result, Exception):
                        raise result
                    return _make_mock_response(result)
            return _make_mock_response(200)

        mock_get.side_effect = side_effect_get
        mock_post.side_effect = side_effect_post
        return mock_get, mock_post

    def test_all_services_ok_sle(self) -> None:
        """Test all services returning 200 on an SLE server."""
        mock_get, mock_post = self._mock_requests(
            {
                "/niauth/": 200,
                "/nitestmonitor/": 200,
                "/niapm/": 200,
                "/nisysmgmt/": 200,
                "/nitag/": 200,
                "/nifile/": 200,
                "/ninotebook/": 200,
                "/niapp/": 200,
                "/nidynamicformfields/": 200,
                "/niworkorder/": 200,
            }
        )
        with patch("slcli.platform.requests.get", mock_get), patch(
            "slcli.platform.requests.post", mock_post
        ):
            result = check_service_status("https://api.example.com", "valid-key")

        assert result["server_reachable"] is True
        assert result["auth_valid"] is True
        assert result["platform"] == PLATFORM_SLE
        assert result["services"]["Auth"] == "ok"
        assert result["services"]["Test Monitor"] == "ok"
        assert result["services"]["Work Order"] == "ok"

    def test_all_services_ok_sls(self) -> None:
        """Test SLS detected when workorder returns 404."""
        mock_get, mock_post = self._mock_requests(
            {
                "/niauth/": 200,
                "/nitestmonitor/": 200,
                "/niapm/": 200,
                "/nisysmgmt/": 200,
                "/nitag/": 200,
                "/nifile/": 200,
                "/ninotebook/": 404,
                "/niapp/": 200,
                "/nidynamicformfields/": 404,
                "/niworkorder/": 404,
            }
        )
        with patch("slcli.platform.requests.get", mock_get), patch(
            "slcli.platform.requests.post", mock_post
        ):
            result = check_service_status("https://my-server.local", "valid-key")

        assert result["server_reachable"] is True
        assert result["auth_valid"] is True
        assert result["platform"] == PLATFORM_SLS
        assert result["services"]["Work Order"] == "not_found"

    def test_all_services_unauthorized(self) -> None:
        """Test invalid API key — all services return 401."""
        mock_get, mock_post = self._mock_requests(
            {
                "/niauth/": 401,
                "/nitestmonitor/": 401,
                "/niapm/": 401,
                "/nisysmgmt/": 401,
                "/nitag/": 401,
                "/nifile/": 401,
                "/ninotebook/": 401,
                "/niapp/": 401,
                "/nidynamicformfields/": 401,
                "/niworkorder/": 401,
            }
        )
        with patch("slcli.platform.requests.get", mock_get), patch(
            "slcli.platform.requests.post", mock_post
        ):
            result = check_service_status("https://api.example.com", "bad-key")

        assert result["server_reachable"] is True
        assert result["auth_valid"] is False
        assert result["services"]["Auth"] == "unauthorized"
        assert result["services"]["Test Monitor"] == "unauthorized"

    def test_partial_unauthorized(self) -> None:
        """Test when some services accept the key but others don't."""
        mock_get, mock_post = self._mock_requests(
            {
                "/niauth/": 200,
                "/nitestmonitor/": 403,
                "/niapm/": 200,
                "/nisysmgmt/": 200,
                "/nitag/": 200,
                "/nifile/": 200,
                "/ninotebook/": 200,
                "/niapp/": 200,
                "/nidynamicformfields/": 200,
                "/niworkorder/": 200,
            }
        )
        with patch("slcli.platform.requests.get", mock_get), patch(
            "slcli.platform.requests.post", mock_post
        ):
            result = check_service_status("https://api.example.com", "partial-key")

        assert result["server_reachable"] is True
        assert result["auth_valid"] is True
        assert result["services"]["Auth"] == "ok"
        assert result["services"]["Test Monitor"] == "unauthorized"

    def test_all_services_unreachable(self) -> None:
        """Test completely unreachable server."""
        conn_err = req_module.ConnectionError("Connection refused")
        mock_get, mock_post = self._mock_requests(
            {
                "/niauth/": conn_err,
                "/nitestmonitor/": conn_err,
                "/niapm/": conn_err,
                "/nisysmgmt/": conn_err,
                "/nitag/": conn_err,
                "/nifile/": conn_err,
                "/ninotebook/": conn_err,
                "/niapp/": conn_err,
                "/nidynamicformfields/": conn_err,
                "/niworkorder/": conn_err,
            }
        )
        with patch("slcli.platform.requests.get", mock_get), patch(
            "slcli.platform.requests.post", mock_post
        ):
            result = check_service_status("https://offline.example.com", "any-key")

        assert result["server_reachable"] is False
        assert result["auth_valid"] is None
        assert result["platform"] == PLATFORM_UNREACHABLE

    def test_inconclusive_workorder_status_returns_unknown(self) -> None:
        """Test that unauthorized workorder status no longer guesses the platform."""
        mock_get, mock_post = self._mock_requests(
            {
                "/niauth/": 200,
                "/nitestmonitor/": 200,
                "/niapm/": 200,
                "/nisysmgmt/": 200,
                "/nitag/": 200,
                "/nifile/": 200,
                "/ninotebook/": 200,
                "/niapp/": 200,
                "/nidynamicformfields/": 200,
                "/niworkorder/": 401,
            }
        )
        with patch("slcli.platform.requests.get", mock_get), patch(
            "slcli.platform.requests.post", mock_post
        ):
            result = check_service_status("https://demo-api.lifecyclesolutions.ni.com", "key")

        assert result["server_reachable"] is True
        assert result["platform"] == PLATFORM_UNKNOWN

    def test_reports_file_query_fallback_capability(self) -> None:
        """Test file service health includes query-files-linq fallback details."""
        mock_get, mock_post = self._mock_requests(
            {
                "/niauth/": 200,
                "/nitestmonitor/": 200,
                "/niapm/": 200,
                "/nisysmgmt/": 200,
                "/nitag/": 404,
                "/nifile/": 404,
                "/ninotebook/": 404,
                "/niapp/": 404,
                "/nidynamicformfields/": 404,
                "/niworkorder/": 404,
            }
        )
        with patch("slcli.platform.requests.get", mock_get), patch(
            "slcli.platform.requests.post", mock_post
        ), patch(
            "slcli.platform.get_file_query_capability",
            return_value={
                "status": "fallback",
                "file_query_endpoint": "query-files-linq",
                "elasticsearch_available": False,
            },
        ):
            result = check_service_status("https://my-server.local", "valid-key")

        assert result["services"]["File"] == "fallback"
        assert result["file_query_endpoint"] == "query-files-linq"
        assert result["elasticsearch_available"] is False

    def test_reports_sls_query_files_capability(self) -> None:
        """Test file service health reports query-files for SLS servers."""
        mock_get, mock_post = self._mock_requests(
            {
                "/niauth/": 200,
                "/nitestmonitor/": 200,
                "/niapm/": 200,
                "/nisysmgmt/": 200,
                "/nitag/": 404,
                "/nifile/": 404,
                "/ninotebook/": 404,
                "/niapp/": 404,
                "/nidynamicformfields/": 404,
                "/niworkorder/": 404,
            }
        )
        with patch("slcli.platform.requests.get", mock_get), patch(
            "slcli.platform.requests.post", mock_post
        ), patch(
            "slcli.platform.get_file_query_capability",
            return_value={
                "status": "ok",
                "file_query_endpoint": "query-files",
                "elasticsearch_available": False,
            },
        ):
            result = check_service_status("https://my-server.local", "valid-key")

        assert result["services"]["File"] == "ok"
        assert result["file_query_endpoint"] == "query-files"
        assert result["elasticsearch_available"] is False


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

    def test_get_platform_unknown_when_only_api_url_env_is_set(self) -> None:
        """Test that API URL alone does not trigger hostname-based platform guessing."""
        with patch.dict(
            "os.environ",
            {"SYSTEMLINK_API_URL": "https://demo-api.lifecyclesolutions.ni.com"},
            clear=True,
        ), patch("slcli.platform.keyring.get_password") as mock_keyring:
            mock_keyring.return_value = None

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
        """Test getting platform info for SLE with service details."""
        from slcli.profiles import Profile

        profile = Profile(
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
            "platform": PLATFORM_SLE,
        }

        with patch("slcli.profiles.get_active_profile") as mock_profile, patch(
            "slcli.utils.get_base_url"
        ) as mock_base_url, patch("slcli.utils.get_web_url") as mock_web_url, patch(
            "slcli.utils.get_api_key"
        ) as mock_api_key, patch(
            "slcli.platform.check_service_status", return_value=mock_status
        ):
            mock_profile.return_value = profile
            mock_base_url.return_value = "https://demo-api.lifecyclesolutions.ni.com"
            mock_web_url.return_value = "https://demo.lifecyclesolutions.ni.com"
            mock_api_key.return_value = "test-key"

            result = get_platform_info()

            assert result["platform"] == "SLE"
            assert result["platform_display"] == "SystemLink Enterprise"
            assert result["logged_in"] is True
            assert result["server_reachable"] is True
            assert result["auth_valid"] is True
            assert result["services"]["Auth"] == "ok"
            assert "features" not in result

    def test_get_platform_info_sls(self) -> None:
        """Test getting platform info for SLS."""
        from slcli.profiles import Profile

        profile = Profile(
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
                "File": "ok",
                "Work Order": "not_found",
            },
            "file_query_endpoint": "query-files",
            "elasticsearch_available": False,
            "platform": PLATFORM_SLS,
        }

        with patch("slcli.profiles.get_active_profile") as mock_profile, patch(
            "slcli.utils.get_base_url"
        ) as mock_base_url, patch("slcli.utils.get_web_url") as mock_web_url, patch(
            "slcli.utils.get_api_key"
        ) as mock_api_key, patch(
            "slcli.platform.check_service_status", return_value=mock_status
        ):
            mock_profile.return_value = profile
            mock_base_url.return_value = "https://my-server.local"
            mock_web_url.return_value = "https://my-server.local"
            mock_api_key.return_value = "test-key"

            result = get_platform_info()

            assert result["platform"] == "SLS"
            assert result["platform_display"] == "SystemLink Server"
            assert result["logged_in"] is True
            assert result["server_reachable"] is True
            assert result["file_query_endpoint"] == "query-files"
            assert "features" not in result

    def test_get_platform_info_file_query_fallback(self) -> None:
        """Test get_platform_info reports query-files-linq when search-files is unavailable."""
        from slcli.profiles import Profile

        profile = Profile(
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
            "platform": PLATFORM_SLS,
        }

        with patch("slcli.profiles.get_active_profile") as mock_profile, patch(
            "slcli.utils.get_base_url"
        ) as mock_base_url, patch("slcli.utils.get_web_url") as mock_web_url, patch(
            "slcli.utils.get_api_key"
        ) as mock_api_key, patch(
            "slcli.platform.check_service_status", return_value=mock_status
        ):
            mock_profile.return_value = profile
            mock_base_url.return_value = "https://my-server.local"
            mock_web_url.return_value = "https://my-server.local"
            mock_api_key.return_value = "test-key"

            result = get_platform_info()

            assert result["services"]["File"] == "fallback"
            assert result["file_query_endpoint"] == "query-files-linq"
            assert result["elasticsearch_available"] is False

    def test_get_platform_info_not_logged_in(self) -> None:
        """Test getting platform info when not logged in."""
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

            result = get_platform_info()

            assert result["logged_in"] is False
            assert result["server_reachable"] is None
            assert result["auth_valid"] is None
            assert result["platform"] == PLATFORM_UNKNOWN

    def test_get_platform_info_unreachable_server(self) -> None:
        """Test that platform shows unreachable when server cannot be contacted."""
        from slcli.profiles import Profile

        profile = Profile(
            name="test",
            server="https://my-server.local",
            api_key="test-key",
            web_url="https://my-server.local",
            platform="SLS",
        )
        mock_status = {
            "server_reachable": False,
            "auth_valid": None,
            "services": {"Auth": "unreachable", "Test Monitor": "unreachable"},
            "platform": PLATFORM_UNREACHABLE,
        }

        with patch("slcli.profiles.get_active_profile") as mock_profile, patch(
            "slcli.utils.get_base_url"
        ) as mock_base_url, patch("slcli.utils.get_web_url") as mock_web_url, patch(
            "slcli.utils.get_api_key"
        ) as mock_api_key, patch(
            "slcli.platform.check_service_status", return_value=mock_status
        ):
            mock_profile.return_value = profile
            mock_base_url.return_value = "https://my-server.local"
            mock_web_url.return_value = "https://my-server.local"
            mock_api_key.return_value = "test-key"

            result = get_platform_info()

            assert result["platform"] == PLATFORM_UNREACHABLE
            assert result["platform_display"] == "Unreachable (could not connect to server)"
            assert result["logged_in"] is True
            assert result["server_reachable"] is False
            assert result["auth_valid"] is None
            assert "features" not in result

    def test_get_platform_info_unauthorized(self) -> None:
        """Test that auth_valid=False is reported when API key is unauthorized."""
        from slcli.profiles import Profile

        profile = Profile(
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
            "platform": PLATFORM_SLE,
        }

        with patch("slcli.profiles.get_active_profile") as mock_profile, patch(
            "slcli.utils.get_base_url"
        ) as mock_base_url, patch("slcli.utils.get_web_url") as mock_web_url, patch(
            "slcli.utils.get_api_key"
        ) as mock_api_key, patch(
            "slcli.platform.check_service_status", return_value=mock_status
        ):
            mock_profile.return_value = profile
            mock_base_url.return_value = "https://api.example.com"
            mock_web_url.return_value = "https://example.com"
            mock_api_key.return_value = "bad-key"

            result = get_platform_info()

            assert result["auth_valid"] is False
            assert result["server_reachable"] is True
            assert result["services"]["Auth"] == "unauthorized"


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
