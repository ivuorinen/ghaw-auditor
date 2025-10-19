"""Tests for GitHub client module."""

from unittest.mock import Mock, patch

import httpx
import pytest

from ghaw_auditor.github_client import GitHubClient, should_retry_http_error


def test_github_client_initialization_no_token() -> None:
    """Test GitHub client initialization without token."""
    client = GitHubClient()

    assert client.base_url == "https://api.github.com"
    assert "Accept" in client.headers
    assert "Authorization" not in client.headers
    assert client.client is not None

    client.close()


def test_github_client_initialization_with_token() -> None:
    """Test GitHub client initialization with token."""
    client = GitHubClient(token="ghp_test123")

    assert "Authorization" in client.headers
    assert client.headers["Authorization"] == "Bearer ghp_test123"

    client.close()


def test_github_client_custom_base_url() -> None:
    """Test GitHub client with custom base URL."""
    client = GitHubClient(base_url="https://github.enterprise.com/api/v3")

    assert client.base_url == "https://github.enterprise.com/api/v3"

    client.close()


@patch("httpx.Client")
def test_get_ref_sha_success(mock_client_class: Mock) -> None:
    """Test successful ref SHA resolution."""
    # Setup mock
    mock_response = Mock()
    mock_response.json.return_value = {"sha": "abc123def456"}
    mock_response.raise_for_status = Mock()

    mock_http_client = Mock()
    mock_http_client.get.return_value = mock_response
    mock_client_class.return_value = mock_http_client

    # Test
    client = GitHubClient(token="test")
    sha = client.get_ref_sha("actions", "checkout", "v4")

    assert sha == "abc123def456"
    mock_http_client.get.assert_called_once_with("https://api.github.com/repos/actions/checkout/commits/v4")


@patch("httpx.Client")
def test_get_ref_sha_http_error(mock_client_class: Mock) -> None:
    """Test ref SHA resolution with HTTP error."""
    # Setup mock to raise HTTPStatusError
    mock_error_response = Mock()
    mock_error_response.status_code = 404

    mock_response = Mock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "404 Not Found",
        request=Mock(),
        response=mock_error_response,
    )

    mock_http_client = Mock()
    mock_http_client.get.return_value = mock_response
    mock_client_class.return_value = mock_http_client

    # Test - 404 errors should not be retried, so expect HTTPStatusError
    client = GitHubClient(token="test")
    with pytest.raises(httpx.HTTPStatusError):
        client.get_ref_sha("actions", "nonexistent", "v1")


@patch("httpx.Client")
def test_get_file_content_success(mock_client_class: Mock) -> None:
    """Test successful file content retrieval."""
    # Setup mock
    mock_response = Mock()
    mock_response.text = "name: Test Action\\nruns:\\n  using: node20"
    mock_response.raise_for_status = Mock()

    mock_http_client = Mock()
    mock_http_client.get.return_value = mock_response
    mock_client_class.return_value = mock_http_client

    # Test
    client = GitHubClient()
    content = client.get_file_content("actions", "checkout", "action.yml", "abc123")

    assert "Test Action" in content
    mock_http_client.get.assert_called_once_with("https://raw.githubusercontent.com/actions/checkout/abc123/action.yml")


@patch("httpx.Client")
def test_get_file_content_http_error(mock_client_class: Mock) -> None:
    """Test file content retrieval with HTTP error."""
    # Setup mock to raise HTTPStatusError
    mock_error_response = Mock()
    mock_error_response.status_code = 404

    mock_response = Mock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "404 Not Found",
        request=Mock(),
        response=mock_error_response,
    )

    mock_http_client = Mock()
    mock_http_client.get.return_value = mock_response
    mock_client_class.return_value = mock_http_client

    # Test - 404 errors should not be retried, so expect HTTPStatusError
    client = GitHubClient()
    with pytest.raises(httpx.HTTPStatusError):
        client.get_file_content("actions", "checkout", "missing.yml", "abc123")


@patch("httpx.Client")
def test_github_client_context_manager(mock_client_class: Mock) -> None:
    """Test GitHub client as context manager."""
    mock_http_client = Mock()
    mock_client_class.return_value = mock_http_client

    # Test context manager
    with GitHubClient(token="test") as client:
        assert client is not None
        assert isinstance(client, GitHubClient)

    # Should have called close
    mock_http_client.close.assert_called_once()


@patch("httpx.Client")
def test_github_client_close(mock_client_class: Mock) -> None:
    """Test GitHub client close method."""
    mock_http_client = Mock()
    mock_client_class.return_value = mock_http_client

    client = GitHubClient()
    client.close()

    mock_http_client.close.assert_called_once()


@patch("httpx.Client")
def test_github_client_logs_successful_ref_sha(mock_client_class: Mock, caplog: pytest.LogCaptureFixture) -> None:
    """Test that successful ref SHA requests are logged at DEBUG level."""
    import logging

    mock_http_client = Mock()
    mock_response = Mock()
    mock_response.json.return_value = {"sha": "abc123def"}
    mock_http_client.get.return_value = mock_response
    mock_client_class.return_value = mock_http_client

    with caplog.at_level(logging.DEBUG):
        client = GitHubClient(token="test")
        sha = client.get_ref_sha("actions", "checkout", "v4")

    assert sha == "abc123def"
    assert "Fetching ref SHA: actions/checkout@v4" in caplog.text
    assert "Resolved actions/checkout@v4 -> abc123def" in caplog.text


@patch("httpx.Client")
def test_github_client_logs_4xx_error(mock_client_class: Mock, caplog: pytest.LogCaptureFixture) -> None:
    """Test that 404 errors are logged with user-friendly messages at ERROR level."""
    import logging

    mock_http_client = Mock()
    mock_response = Mock()
    mock_response.status_code = 404
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Not found", request=Mock(), response=mock_response
    )
    mock_http_client.get.return_value = mock_response
    mock_client_class.return_value = mock_http_client

    with caplog.at_level(logging.ERROR):
        client = GitHubClient()
        with pytest.raises(httpx.HTTPStatusError):
            client.get_ref_sha("actions", "nonexistent", "v1")

    # Check for user-friendly error message
    assert "Action not found" in caplog.text
    assert "actions/nonexistent@v1" in caplog.text


@patch("httpx.Client")
def test_github_client_logs_successful_file_content(mock_client_class: Mock, caplog: pytest.LogCaptureFixture) -> None:
    """Test that successful file content requests are logged at DEBUG level."""
    import logging

    mock_http_client = Mock()
    mock_response = Mock()
    mock_response.text = "name: Checkout\ndescription: Test"
    mock_http_client.get.return_value = mock_response
    mock_client_class.return_value = mock_http_client

    with caplog.at_level(logging.DEBUG):
        client = GitHubClient(token="test")
        content = client.get_file_content("actions", "checkout", "action.yml", "v4")

    assert content == "name: Checkout\ndescription: Test"
    assert "Fetching file: actions/checkout/action.yml@v4" in caplog.text
    assert "Downloaded action.yml" in caplog.text
    assert "bytes" in caplog.text


@patch("httpx.Client")
def test_github_client_retries_5xx_errors(mock_client_class: Mock) -> None:
    """Test that 5xx errors are retried."""
    from tenacity import RetryError

    mock_http_client = Mock()
    mock_response = Mock()
    mock_response.status_code = 500
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Server error", request=Mock(), response=mock_response
    )
    mock_http_client.get.return_value = mock_response
    mock_client_class.return_value = mock_http_client

    client = GitHubClient()
    with pytest.raises(RetryError):
        client.get_ref_sha("actions", "checkout", "v1")

    # Should have retried 3 times
    assert mock_http_client.get.call_count == 3


@patch("httpx.Client")
def test_github_client_logs_5xx_warning(mock_client_class: Mock, caplog: pytest.LogCaptureFixture) -> None:
    """Test that 5xx errors are logged at WARNING level."""
    import logging

    from tenacity import RetryError

    mock_http_client = Mock()
    mock_response = Mock()
    mock_response.status_code = 503
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Service unavailable", request=Mock(), response=mock_response
    )
    mock_http_client.get.return_value = mock_response
    mock_client_class.return_value = mock_http_client

    with caplog.at_level(logging.WARNING):
        client = GitHubClient()
        with pytest.raises(RetryError):
            client.get_file_content("actions", "checkout", "action.yml", "v4")

    assert "HTTP 503" in caplog.text


def test_should_retry_http_error_network_errors() -> None:
    """Test that network errors should be retried."""
    error = httpx.RequestError("Connection failed")
    assert should_retry_http_error(error) is True


def test_should_retry_http_error_404() -> None:
    """Test that 404 errors should not be retried."""
    mock_response = Mock()
    mock_response.status_code = 404
    error = httpx.HTTPStatusError("Not found", request=Mock(), response=mock_response)
    assert should_retry_http_error(error) is False


def test_should_retry_http_error_403() -> None:
    """Test that 403 errors should not be retried."""
    mock_response = Mock()
    mock_response.status_code = 403
    error = httpx.HTTPStatusError("Forbidden", request=Mock(), response=mock_response)
    assert should_retry_http_error(error) is False


def test_should_retry_http_error_429() -> None:
    """Test that 429 rate limiting errors should be retried."""
    mock_response = Mock()
    mock_response.status_code = 429
    error = httpx.HTTPStatusError("Rate limited", request=Mock(), response=mock_response)
    assert should_retry_http_error(error) is True


def test_should_retry_http_error_500() -> None:
    """Test that 500 errors should be retried."""
    mock_response = Mock()
    mock_response.status_code = 500
    error = httpx.HTTPStatusError("Server error", request=Mock(), response=mock_response)
    assert should_retry_http_error(error) is True


def test_should_retry_http_error_other() -> None:
    """Test that non-HTTP errors should not be retried."""
    error = ValueError("Some other error")
    assert should_retry_http_error(error) is False


@patch("httpx.Client")
def test_github_client_logs_403_error(mock_client_class: Mock, caplog: pytest.LogCaptureFixture) -> None:
    """Test that 403 errors are logged with user-friendly messages."""
    import logging

    mock_http_client = Mock()
    mock_response = Mock()
    mock_response.status_code = 403
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Forbidden", request=Mock(), response=mock_response
    )
    mock_http_client.get.return_value = mock_response
    mock_client_class.return_value = mock_http_client

    with caplog.at_level(logging.ERROR):
        client = GitHubClient()
        with pytest.raises(httpx.HTTPStatusError):
            client.get_ref_sha("actions", "checkout", "v1")

    assert "Access denied (check token permissions)" in caplog.text


@patch("httpx.Client")
def test_github_client_logs_401_error(mock_client_class: Mock, caplog: pytest.LogCaptureFixture) -> None:
    """Test that 401 errors are logged with user-friendly messages."""
    import logging

    mock_http_client = Mock()
    mock_response = Mock()
    mock_response.status_code = 401
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Unauthorized", request=Mock(), response=mock_response
    )
    mock_http_client.get.return_value = mock_response
    mock_client_class.return_value = mock_http_client

    with caplog.at_level(logging.ERROR):
        client = GitHubClient()
        with pytest.raises(httpx.HTTPStatusError):
            client.get_file_content("actions", "checkout", "action.yml", "abc123")

    assert "Authentication required" in caplog.text


@patch("httpx.Client")
def test_github_client_logs_401_error_get_ref_sha(mock_client_class: Mock, caplog: pytest.LogCaptureFixture) -> None:
    """Test that 401 errors are logged in get_ref_sha."""
    import logging

    mock_http_client = Mock()
    mock_response = Mock()
    mock_response.status_code = 401
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Unauthorized", request=Mock(), response=mock_response
    )
    mock_http_client.get.return_value = mock_response
    mock_client_class.return_value = mock_http_client

    with caplog.at_level(logging.ERROR):
        client = GitHubClient()
        with pytest.raises(httpx.HTTPStatusError):
            client.get_ref_sha("actions", "checkout", "v1")

    assert "Authentication required" in caplog.text


@patch("httpx.Client")
def test_github_client_logs_403_error_get_file_content(
    mock_client_class: Mock, caplog: pytest.LogCaptureFixture
) -> None:
    """Test that 403 errors are logged in get_file_content."""
    import logging

    mock_http_client = Mock()
    mock_response = Mock()
    mock_response.status_code = 403
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Forbidden", request=Mock(), response=mock_response
    )
    mock_http_client.get.return_value = mock_response
    mock_client_class.return_value = mock_http_client

    with caplog.at_level(logging.ERROR):
        client = GitHubClient()
        with pytest.raises(httpx.HTTPStatusError):
            client.get_file_content("actions", "checkout", "action.yml", "abc123")

    assert "Access denied (check token permissions)" in caplog.text
