# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for FerretScanner plugin."""

import json
import pytest
from unittest.mock import patch, MagicMock, mock_open

from automated_security_helper.plugin_modules.ash_ferret_plugins.ferret_scanner import (
    FerretScanner,
    FerretScannerConfig,
    FerretScannerConfigOptions,
)
from automated_security_helper.core.exceptions import ScannerError


@pytest.mark.unit
class TestFerretScannerConfig:
    """Test configuration handling for FerretScanner."""

    def test_default_config_initialization(self):
        """Test default configuration values."""
        config = FerretScannerConfig()

        assert config.name == "ferret-scan"
        assert config.enabled is True
        assert isinstance(config.options, FerretScannerConfigOptions)

        # Test default options
        options = config.options
        assert options.confidence_levels == "all"
        assert options.checks == "all"
        assert options.recursive is True
        assert options.config_file is None
        assert options.profile is None
        assert options.exclude_patterns == []
        assert options.no_color is True
        assert options.quiet is False

    def test_custom_config_initialization(self, custom_ferret_config):
        """Test custom configuration values."""
        config = custom_ferret_config

        assert config.name == "ferret-scan"
        assert config.enabled is True

        options = config.options
        assert options.confidence_levels == "high,medium"
        assert options.checks == "CREDIT_CARD,SECRETS,SSN"
        assert options.recursive is True
        assert options.profile == "security-audit"
        assert options.no_color is True
        assert options.quiet is False

    def test_scanner_initialization_with_default_config(self, mock_plugin_context):
        """Test scanner initialization with default configuration."""
        scanner = FerretScanner(context=mock_plugin_context)

        assert scanner.config is not None
        assert isinstance(scanner.config, FerretScannerConfig)
        assert scanner.command == "ferret-scan"
        assert scanner.tool_type == "Secrets"

    def test_scanner_initialization_with_custom_config(self, mock_plugin_context, custom_ferret_config):
        """Test scanner initialization with custom configuration."""
        scanner = FerretScanner(context=mock_plugin_context, config=custom_ferret_config)

        assert scanner.config == custom_ferret_config
        assert scanner.config.options.confidence_levels == "high,medium"
        assert scanner.config.options.checks == "CREDIT_CARD,SECRETS,SSN"


@pytest.mark.unit
class TestFerretScannerConfigProcessing:
    """Test configuration option processing."""

    def test_process_config_options_default(self, mock_plugin_context, default_ferret_config):
        """Test processing of default configuration options."""
        scanner = FerretScanner(context=mock_plugin_context, config=default_ferret_config)
        scanner._process_config_options()

        extra_args = scanner.args.extra_args

        # Should have recursive flag
        recursive_arg = next((arg for arg in extra_args if arg.key == "--recursive"), None)
        assert recursive_arg is not None

        # Should have no-color flag
        no_color_arg = next((arg for arg in extra_args if arg.key == "--no-color"), None)
        assert no_color_arg is not None

        # Should NOT have confidence arg (default is "all")
        confidence_arg = next((arg for arg in extra_args if arg.key == "--confidence"), None)
        assert confidence_arg is None

        # Should NOT have checks arg (default is "all")
        checks_arg = next((arg for arg in extra_args if arg.key == "--checks"), None)
        assert checks_arg is None

    def test_process_config_options_custom(self, mock_plugin_context, custom_ferret_config):
        """Test processing of custom configuration options."""
        scanner = FerretScanner(context=mock_plugin_context, config=custom_ferret_config)
        scanner._process_config_options()

        extra_args = scanner.args.extra_args

        # Should have custom confidence levels
        confidence_arg = next((arg for arg in extra_args if arg.key == "--confidence"), None)
        assert confidence_arg is not None
        assert confidence_arg.value == "high,medium"

        # Should have custom checks
        checks_arg = next((arg for arg in extra_args if arg.key == "--checks"), None)
        assert checks_arg is not None
        assert checks_arg.value == "CREDIT_CARD,SECRETS,SSN"

        # Should have profile
        profile_arg = next((arg for arg in extra_args if arg.key == "--profile"), None)
        assert profile_arg is not None
        assert profile_arg.value == "security-audit"

    def test_process_exclude_patterns(self, mock_plugin_context):
        """Test exclude patterns processing."""
        config = FerretScannerConfig(
            options=FerretScannerConfigOptions(
                exclude_patterns=["*.log", "node_modules/**", "vendor/**"]
            )
        )

        scanner = FerretScanner(context=mock_plugin_context, config=config)
        scanner._process_config_options()

        extra_args = scanner.args.extra_args
        exclude_args = [arg for arg in extra_args if arg.key == "--exclude"]

        # Should have at least 3 exclude patterns
        assert len(exclude_args) >= 3
        exclude_values = [arg.value for arg in exclude_args]
        assert "*.log" in exclude_values
        assert "node_modules/**" in exclude_values
        assert "vendor/**" in exclude_values

    def test_process_quiet_mode(self, mock_plugin_context):
        """Test quiet mode processing."""
        config = FerretScannerConfig(
            options=FerretScannerConfigOptions(quiet=True)
        )

        scanner = FerretScanner(context=mock_plugin_context, config=config)
        scanner._process_config_options()

        extra_args = scanner.args.extra_args
        quiet_arg = next((arg for arg in extra_args if arg.key == "--quiet"), None)
        assert quiet_arg is not None


@pytest.mark.unit
class TestFerretScannerConfigFileDiscovery:
    """Test configuration file discovery."""

    def test_find_config_file_explicit(self, mock_plugin_context, mock_ferret_config_file):
        """Test finding explicitly specified config file."""
        scanner = FerretScanner(context=mock_plugin_context)

        result = scanner._find_config_file(mock_ferret_config_file)
        assert result == mock_ferret_config_file

    def test_find_config_file_auto_discovery(self, mock_plugin_context, mock_ferret_config_file):
        """Test auto-discovery of config file."""
        scanner = FerretScanner(context=mock_plugin_context)

        # Should find ferret.yaml in source directory
        result = scanner._find_config_file(None)
        assert result == mock_ferret_config_file

    def test_find_config_file_not_found(self, mock_plugin_context):
        """Test when no config file is found in source dir, falls back to default."""
        scanner = FerretScanner(context=mock_plugin_context)

        result = scanner._find_config_file(None)
        # Should return the default config bundled with the plugin
        assert result is not None
        assert "ferret-config.yaml" in str(result)

    def test_find_config_file_disabled_default(self, mock_plugin_context):
        """Test when default config is disabled and no source config exists."""
        from automated_security_helper.plugin_modules.ash_ferret_plugins.ferret_scanner import (
            FerretScannerConfig,
            FerretScannerConfigOptions,
        )
        config = FerretScannerConfig(
            options=FerretScannerConfigOptions(use_default_config=False)
        )
        scanner = FerretScanner(context=mock_plugin_context, config=config)

        result = scanner._find_config_file(None)
        assert result is None

    def test_find_config_file_nonexistent_explicit(self, mock_plugin_context):
        """Test when explicitly specified config file doesn't exist."""
        scanner = FerretScanner(context=mock_plugin_context)

        result = scanner._find_config_file("nonexistent.yaml")
        assert result is None


@pytest.mark.unit
class TestFerretScannerDependencies:
    """Test dependency validation for FerretScanner."""

    @patch("automated_security_helper.plugin_modules.ash_ferret_plugins.ferret_scanner.find_executable")
    def test_validate_dependencies_success(self, mock_find_executable, mock_plugin_context):
        """Test successful dependency validation when ferret-scan is available."""
        mock_find_executable.return_value = "/usr/local/bin/ferret-scan"

        scanner = FerretScanner(context=mock_plugin_context)
        result = scanner.validate_plugin_dependencies()

        assert result is True
        assert scanner.dependencies_satisfied is True
        mock_find_executable.assert_called_once_with("ferret-scan")

    @patch("automated_security_helper.plugin_modules.ash_ferret_plugins.ferret_scanner.find_executable")
    def test_validate_dependencies_failure_not_found(self, mock_find_executable, mock_plugin_context):
        """Test dependency validation failure when ferret-scan is not found."""
        mock_find_executable.return_value = None

        scanner = FerretScanner(context=mock_plugin_context)
        result = scanner.validate_plugin_dependencies()

        assert result is False
        mock_find_executable.assert_called_once_with("ferret-scan")

    @patch("automated_security_helper.plugin_modules.ash_ferret_plugins.ferret_scanner.find_executable")
    def test_validate_dependencies_failure_empty_string(self, mock_find_executable, mock_plugin_context):
        """Test dependency validation failure when find_executable returns empty string."""
        mock_find_executable.return_value = ""

        scanner = FerretScanner(context=mock_plugin_context)
        result = scanner.validate_plugin_dependencies()

        assert result is False
        mock_find_executable.assert_called_once_with("ferret-scan")


@pytest.mark.unit
class TestFerretScannerArgumentResolution:
    """Test argument resolution for FerretScanner."""

    def test_resolve_arguments_default(self, mock_plugin_context, mock_target_directory):
        """Test argument resolution with default config."""
        scanner = FerretScanner(context=mock_plugin_context)

        args = scanner._resolve_arguments(target=mock_target_directory)

        assert args[0] == "ferret-scan"
        assert "--format" in args
        assert "sarif" in args
        assert "--file" in args
        assert str(mock_target_directory) in args[-1]

    def test_resolve_arguments_with_options(self, mock_plugin_context, mock_target_directory, custom_ferret_config):
        """Test argument resolution with custom options."""
        scanner = FerretScanner(context=mock_plugin_context, config=custom_ferret_config)

        args = scanner._resolve_arguments(target=mock_target_directory)

        assert "ferret-scan" in args
        assert "--confidence" in args
        assert "high,medium" in args
        assert "--checks" in args
        assert "--profile" in args
        assert "security-audit" in args


@pytest.mark.unit
class TestFerretScannerScanning:
    """Test scanning workflow for FerretScanner."""

    @patch("automated_security_helper.plugin_modules.ash_ferret_plugins.ferret_scanner.find_executable")
    def test_scan_successful_execution(self, mock_find_executable, mock_plugin_context,
                                       mock_target_directory, mock_sarif_response, mock_results_directory):
        """Test successful scan execution with valid target."""
        mock_find_executable.return_value = "/usr/local/bin/ferret-scan"
        results_dir, source_dir = mock_results_directory

        scanner = FerretScanner(context=mock_plugin_context)
        scanner.results_dir = results_dir
        scanner.dependencies_satisfied = True

        with patch.object(scanner, '_pre_scan', return_value=True), \
             patch.object(scanner, '_post_scan'), \
             patch.object(scanner, '_run_subprocess') as mock_subprocess, \
             patch.object(scanner, '_plugin_log'), \
             patch("builtins.open", mock_open(read_data=json.dumps(mock_sarif_response))), \
             patch("pathlib.Path.exists", return_value=True):

            mock_subprocess.return_value = {"stdout": "", "stderr": ""}

            result = scanner.scan(target=mock_target_directory, target_type="source")

            assert result is not None
            mock_subprocess.assert_called_once()

    @patch("automated_security_helper.plugin_modules.ash_ferret_plugins.ferret_scanner.find_executable")
    def test_scan_pre_scan_failure(self, mock_find_executable, mock_plugin_context, mock_target_directory):
        """Test scan behavior when pre-scan validation fails."""
        mock_find_executable.return_value = "/usr/local/bin/ferret-scan"

        scanner = FerretScanner(context=mock_plugin_context)

        with patch.object(scanner, '_pre_scan', return_value=False), \
             patch.object(scanner, '_post_scan') as mock_post_scan:

            result = scanner.scan(target=mock_target_directory, target_type="source")

            assert result is False
            mock_post_scan.assert_called_once()

    @patch("automated_security_helper.plugin_modules.ash_ferret_plugins.ferret_scanner.find_executable")
    def test_scan_dependencies_not_satisfied(self, mock_find_executable, mock_plugin_context, mock_target_directory):
        """Test scan behavior when dependencies are not satisfied."""
        mock_find_executable.return_value = None

        scanner = FerretScanner(context=mock_plugin_context)
        scanner.dependencies_satisfied = False

        with patch.object(scanner, '_pre_scan', return_value=True), \
             patch.object(scanner, '_post_scan') as mock_post_scan:

            result = scanner.scan(target=mock_target_directory, target_type="source")

            assert result is False
            mock_post_scan.assert_called_once()

    def test_scan_scanner_error_propagation(self, mock_plugin_context, mock_target_directory):
        """Test that ScannerError exceptions are properly propagated."""
        scanner = FerretScanner(context=mock_plugin_context)

        with patch.object(scanner, '_pre_scan', side_effect=ScannerError("Test error")):

            with pytest.raises(ScannerError, match="Test error"):
                scanner.scan(target=mock_target_directory, target_type="source")


@pytest.mark.unit
class TestFerretScannerTargetValidation:
    """Test target validation for FerretScanner."""

    def test_scan_empty_directory(self, mock_plugin_context, mock_empty_directory):
        """Test scan behavior with empty target directory."""
        scanner = FerretScanner(context=mock_plugin_context)

        with patch.object(scanner, '_plugin_log') as mock_log, \
             patch.object(scanner, '_post_scan') as mock_post_scan:

            result = scanner.scan(target=mock_empty_directory, target_type="source")

            assert result is True  # Empty directory returns True (skip)
            mock_post_scan.assert_called_once()

            # Verify appropriate logging
            mock_log.assert_called()
            log_message = mock_log.call_args[0][0]
            assert "empty or doesn't exist" in log_message

    def test_scan_nonexistent_directory(self, mock_plugin_context, tmp_path):
        """Test scan behavior with non-existent target directory."""
        nonexistent_dir = tmp_path / "does_not_exist"

        scanner = FerretScanner(context=mock_plugin_context)

        with patch.object(scanner, '_plugin_log') as mock_log, \
             patch.object(scanner, '_post_scan') as mock_post_scan:

            result = scanner.scan(target=nonexistent_dir, target_type="source")

            assert result is True  # Non-existent directory returns True (skip)
            mock_post_scan.assert_called_once()


@pytest.mark.unit
class TestFerretScannerErrorHandling:
    """Test comprehensive error handling for FerretScanner."""

    @patch("automated_security_helper.plugin_modules.ash_ferret_plugins.ferret_scanner.find_executable")
    def test_json_parse_error(self, mock_find_executable, mock_plugin_context,
                              mock_target_directory, mock_results_directory):
        """Test handling of JSON parse errors from ferret-scan output."""
        mock_find_executable.return_value = "/usr/local/bin/ferret-scan"
        results_dir, source_dir = mock_results_directory

        scanner = FerretScanner(context=mock_plugin_context)
        scanner.results_dir = results_dir
        scanner.dependencies_satisfied = True

        with patch.object(scanner, '_pre_scan', return_value=True), \
             patch.object(scanner, '_post_scan'), \
             patch.object(scanner, '_run_subprocess') as mock_subprocess, \
             patch.object(scanner, '_plugin_log'), \
             patch("builtins.open", mock_open(read_data="not valid json")), \
             patch("pathlib.Path.exists", return_value=True):

            mock_subprocess.return_value = {"stdout": "", "stderr": ""}

            result = scanner.scan(target=mock_target_directory, target_type="source")

            # Should return error dict, not raise exception
            assert isinstance(result, dict)
            assert "errors" in result

    @patch("automated_security_helper.plugin_modules.ash_ferret_plugins.ferret_scanner.find_executable")
    def test_missing_output_file(self, mock_find_executable, mock_plugin_context,
                                   mock_target_directory, mock_results_directory):
        """Test handling when output file is not created."""
        mock_find_executable.return_value = "/usr/local/bin/ferret-scan"
        results_dir, source_dir = mock_results_directory

        scanner = FerretScanner(context=mock_plugin_context)
        scanner.results_dir = results_dir
        scanner.dependencies_satisfied = True

        with patch.object(scanner, '_pre_scan', return_value=True), \
             patch.object(scanner, '_post_scan'), \
             patch.object(scanner, '_run_subprocess') as mock_subprocess, \
             patch.object(scanner, '_plugin_log'):

            mock_subprocess.return_value = {"stdout": "", "stderr": ""}

            result = scanner.scan(target=mock_target_directory, target_type="source")

            assert isinstance(result, dict)
            assert result.get("findings") == []

    @patch("automated_security_helper.plugin_modules.ash_ferret_plugins.ferret_scanner.find_executable")
    def test_general_exception_handling(self, mock_find_executable, mock_plugin_context,
                                        mock_target_directory, mock_results_directory):
        """Test handling of general exceptions during scan."""
        mock_find_executable.return_value = "/usr/local/bin/ferret-scan"
        results_dir, source_dir = mock_results_directory

        scanner = FerretScanner(context=mock_plugin_context)
        scanner.results_dir = results_dir
        scanner.dependencies_satisfied = True

        with patch.object(scanner, '_pre_scan', return_value=True), \
             patch.object(scanner, '_resolve_arguments', side_effect=Exception("Test error")):

            with pytest.raises(ScannerError) as exc_info:
                scanner.scan(target=mock_target_directory, target_type="source")

            assert "Ferret scan failed: Test error" in str(exc_info.value)
