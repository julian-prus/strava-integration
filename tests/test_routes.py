"""Tests for the routes module."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from strava_integration.routes import download_gpx


class TestDownloadGpx:
    def test_returns_gpx_bytes_on_success(self):
        fake_gpx = b"<?xml version='1.0'?><gpx></gpx>"
        mock_response = MagicMock()
        mock_response.content = fake_gpx
        mock_response.raise_for_status.return_value = None

        with patch("strava_integration.routes.requests.get", return_value=mock_response) as mock_get:
            result = download_gpx(12345, "test_token")

        assert result == fake_gpx
        mock_get.assert_called_once_with(
            "https://www.strava.com/api/v3/routes/12345/export_gpx",
            headers={"Authorization": "Bearer test_token"},
            timeout=30,
        )

    def test_raises_on_401_unauthorized(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.HTTPError(
            response=MagicMock(status_code=401)
        )

        with patch("strava_integration.routes.requests.get", return_value=mock_response):
            with pytest.raises(requests.HTTPError):
                download_gpx(12345, "bad_token")

    def test_raises_on_404_not_found(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.HTTPError(
            response=MagicMock(status_code=404)
        )

        with patch("strava_integration.routes.requests.get", return_value=mock_response):
            with pytest.raises(requests.HTTPError):
                download_gpx(99999999, "test_token")

    def test_url_contains_route_id(self):
        mock_response = MagicMock()
        mock_response.content = b"gpx"
        mock_response.raise_for_status.return_value = None

        with patch("strava_integration.routes.requests.get", return_value=mock_response) as mock_get:
            download_gpx(99887766, "tok")

        url = mock_get.call_args[0][0]
        assert "99887766" in url
