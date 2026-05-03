"""Tests for the auth module."""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from strava_integration import auth


class TestLoadConfig:
    def test_loads_valid_config(self, tmp_path):
        config_file = tmp_path / "config.json"
        data = {"client_id": "123", "access_token": "tok", "expires_at": 9999999999}
        config_file.write_text(json.dumps(data))

        result = auth.load_config(path=config_file)
        assert result == data

    def test_raises_when_file_missing(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="Config file not found"):
            auth.load_config(path=tmp_path / "nonexistent.json")


class TestSaveConfig:
    def test_writes_json_to_path(self, tmp_path):
        config_file = tmp_path / "config.json"
        data = {"access_token": "new_tok", "expires_at": 123}

        auth.save_config(data, path=config_file)

        saved = json.loads(config_file.read_text())
        assert saved == data

    def test_creates_parent_directories(self, tmp_path):
        config_file = tmp_path / "nested" / "dir" / "config.json"
        auth.save_config({"token": "x"}, path=config_file)
        assert config_file.exists()


class TestRefreshToken:
    def test_returns_updated_config(self):
        config = {
            "client_id": "cid",
            "client_secret": "csec",
            "refresh_token": "old_refresh",
        }
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "access_token": "new_access",
            "refresh_token": "new_refresh",
            "expires_at": 9999999999,
        }
        mock_response.raise_for_status.return_value = None

        with patch("strava_integration.auth.requests.post", return_value=mock_response):
            result = auth.refresh_token(config)

        assert result["access_token"] == "new_access"
        assert result["refresh_token"] == "new_refresh"
        assert result["expires_at"] == 9999999999
        assert result["client_id"] == "cid"

    def test_raises_on_http_error(self):
        config = {"client_id": "x", "client_secret": "y", "refresh_token": "z"}
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.HTTPError()

        with patch("strava_integration.auth.requests.post", return_value=mock_response):
            with pytest.raises(requests.HTTPError):
                auth.refresh_token(config)


class TestExchangeCode:
    def test_returns_config_with_tokens(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "access_token": "acc",
            "refresh_token": "ref",
            "expires_at": 9999999999,
        }
        mock_response.raise_for_status.return_value = None

        with patch("strava_integration.auth.requests.post", return_value=mock_response) as mock_post:
            result = auth.exchange_code("cid", "csec", "authcode", "http://localhost:9999/callback")

        assert result["client_id"] == "cid"
        assert result["client_secret"] == "csec"
        assert result["access_token"] == "acc"
        assert result["refresh_token"] == "ref"
        assert result["expires_at"] == 9999999999
        call_data = mock_post.call_args[1]["data"]
        assert call_data["grant_type"] == "authorization_code"
        assert call_data["code"] == "authcode"

    def test_raises_on_http_error(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.HTTPError()

        with patch("strava_integration.auth.requests.post", return_value=mock_response):
            with pytest.raises(requests.HTTPError):
                auth.exchange_code("cid", "csec", "bad_code", "http://localhost:9999/callback")


class TestGetValidToken:
    def test_returns_token_when_not_expired(self):
        config = {"access_token": "valid_tok", "expires_at": int(time.time()) + 3600}
        result = auth.get_valid_token(config)
        assert result == "valid_tok"

    def test_refreshes_and_saves_when_expired(self, tmp_path):
        config_file = tmp_path / "config.json"
        config = {
            "client_id": "cid",
            "client_secret": "csec",
            "access_token": "old",
            "refresh_token": "refresh",
            "expires_at": 0,
        }
        config_file.write_text(json.dumps(config))

        refreshed = {**config, "access_token": "new_tok", "expires_at": int(time.time()) + 3600}

        with patch("strava_integration.auth.refresh_token", return_value=refreshed):
            result = auth.get_valid_token(config, path=config_file)

        assert result == "new_tok"
        saved = json.loads(config_file.read_text())
        assert saved["access_token"] == "new_tok"
