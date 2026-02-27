"""
Tests for Git service SSH path resolution.

Covers:
  - _resolve_secret function for SSH key path resolution
  - Absolute paths (/root/.ssh/id_rsa)
  - Tilde expansion (~/.ssh/id_rsa)
  - Relative paths (./keys/id_rsa)
  - Environment variable lookup (SSH_KEY)
  - Edge cases (empty string, None)
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.git_service import _resolve_secret


# ═══════════════════════════════════════════════════════════════════
# 1. DIRECT PATH RESOLUTION TESTS
# ═══════════════════════════════════════════════════════════════════

class TestResolveSecret:
    """Tests for _resolve_secret function."""

    def test_absolute_path(self):
        """/root/.ssh/id_rsa is returned directly."""
        result = _resolve_secret("/root/.ssh/id_rsa")
        
        assert result == "/root/.ssh/id_rsa"

    def test_tilde_path(self):
        """~/.ssh/id_rsa is expanded to absolute path."""
        result = _resolve_secret("~/.ssh/id_rsa")
        
        # Should expand to user's home directory
        expected_prefix = os.path.expanduser("~")
        assert result is not None
        assert result.startswith(expected_prefix)
        assert result.endswith(".ssh/id_rsa")

    def test_relative_path_dot_slash(self):
        """./keys/id_rsa is treated as path."""
        result = _resolve_secret("./keys/id_rsa")
        
        # Should treat as a path, not env var
        assert result == "./keys/id_rsa"

    def test_path_with_separator(self):
        """paths/to/key is treated as path due to separator."""
        result = _resolve_secret("keys/id_rsa")
        
        # Contains / so should be treated as path
        assert result == "keys/id_rsa"

    def test_windows_path_separator(self):
        """Windows path with backslash is treated as path."""
        # This test simulates Windows-style path detection
        with patch("os.sep", "\\"):
            result = _resolve_secret("keys\\id_rsa")
            # Should treat as path since it contains os.sep
            assert result is not None


# ═══════════════════════════════════════════════════════════════════
# 2. ENVIRONMENT VARIABLE TESTS
# ═══════════════════════════════════════════════════════════════════

class TestEnvVarResolution:
    """Tests for environment variable resolution."""

    def test_env_var_name(self):
        """SSH_KEY looks up environment variable."""
        with patch.dict(os.environ, {"SSH_KEY": "/actual/path/to/key"}):
            result = _resolve_secret("SSH_KEY")
            
            assert result == "/actual/path/to/key"

    def test_env_var_not_set(self):
        """Unset env var returns None."""
        # Make sure env var doesn't exist
        env_without_key = {k: v for k, v in os.environ.items() if k != "NONEXISTENT_VAR_XYZ"}
        
        with patch.dict(os.environ, env_without_key, clear=True):
            result = _resolve_secret("NONEXISTENT_VAR_XYZ")
            
            assert result is None

    def test_env_var_empty(self):
        """Empty env var returns None."""
        with patch.dict(os.environ, {"EMPTY_VAR": ""}):
            result = _resolve_secret("EMPTY_VAR")
            
            assert result is None


# ═══════════════════════════════════════════════════════════════════
# 3. EDGE CASES
# ═══════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Edge case tests."""

    def test_empty_string(self):
        """Empty string returns None."""
        result = _resolve_secret("")
        
        assert result is None

    def test_none_input(self):
        """None input returns None."""
        result = _resolve_secret(None)
        
        assert result is None

    def test_whitespace_only(self):
        """Whitespace-only string returns None."""
        result = _resolve_secret("   ")
        
        # Stripped whitespace becomes empty
        assert result is None

    def test_whitespace_around_path(self):
        """Whitespace around path is stripped."""
        result = _resolve_secret("  /path/to/key  ")
        
        assert result == "/path/to/key"

    def test_whitespace_around_env_var(self):
        """Whitespace around env var name is stripped."""
        with patch.dict(os.environ, {"MY_KEY": "/the/path"}):
            result = _resolve_secret("  MY_KEY  ")
            
            assert result == "/the/path"

    def test_home_dir_only(self):
        """Just ~ expands to home directory."""
        result = _resolve_secret("~")
        
        expected = os.path.expanduser("~")
        assert result == expected

    def test_complex_path(self):
        """Complex path with multiple components."""
        result = _resolve_secret("/home/user/.ssh/custom_keys/github_deploy_key")
        
        assert result == "/home/user/.ssh/custom_keys/github_deploy_key"


# ═══════════════════════════════════════════════════════════════════
# 4. INTEGRATION WITH GIT SERVICE
# ═══════════════════════════════════════════════════════════════════

class TestGitServiceIntegration:
    """Integration tests for path resolution in git service context."""

    def test_real_path_exists_check(self, tmp_path):
        """Resolution with actual existing file."""
        # Create a temporary "key" file
        key_file = tmp_path / "test_key"
        key_file.write_text("fake key content")
        
        result = _resolve_secret(str(key_file))
        
        assert result == str(key_file)
        assert Path(result).exists()

    def test_tilde_expands_correctly(self):
        """Tilde expansion produces valid path."""
        result = _resolve_secret("~/.ssh/id_rsa")
        
        # Result should be an absolute path (not start with ~)
        assert not result.startswith("~")
        assert result.startswith("/") or (os.name == "nt" and ":" in result)

    def test_distinguishes_path_from_env_var(self):
        """Correctly distinguishes file paths from env var names."""
        # This looks like an env var name (no path separators)
        with patch.dict(os.environ, {"GIT_SSH_KEY": "/from/env"}):
            result = _resolve_secret("GIT_SSH_KEY")
            assert result == "/from/env"
        
        # This looks like a path (starts with /)
        result2 = _resolve_secret("/GIT_SSH_KEY")
        assert result2 == "/GIT_SSH_KEY"
        
        # This looks like a path (contains /)
        result3 = _resolve_secret("ssh/key")
        assert result3 == "ssh/key"


# ═══════════════════════════════════════════════════════════════════
# 5. UI LABEL COMPATIBILITY TESTS
# ═══════════════════════════════════════════════════════════════════

class TestUILabelCompatibility:
    """Tests matching UI placeholder examples."""

    def test_example_tilde_path(self):
        """~/.ssh/id_rsa as shown in UI placeholder."""
        result = _resolve_secret("~/.ssh/id_rsa")
        
        home = os.path.expanduser("~")
        assert result == f"{home}/.ssh/id_rsa"

    def test_example_root_path(self):
        """/root/.ssh/id_rsa as shown in UI placeholder."""
        result = _resolve_secret("/root/.ssh/id_rsa")
        
        assert result == "/root/.ssh/id_rsa"

    def test_example_env_var_fallback(self):
        """Still supports env var for backward compatibility."""
        with patch.dict(os.environ, {"SSH_DEPLOY_KEY": "/etc/keys/deploy.pem"}):
            result = _resolve_secret("SSH_DEPLOY_KEY")
            
            assert result == "/etc/keys/deploy.pem"
