"""Tests for the main module."""

import pytest
from strava_integration import main


class TestMain:
    """Test cases for main module functions."""

    def test_hello_strava(self):
        """Test the hello_strava function."""
        result = main.hello_strava()
        assert result == "Hello from Strava Integration!"
        assert isinstance(result, str)
