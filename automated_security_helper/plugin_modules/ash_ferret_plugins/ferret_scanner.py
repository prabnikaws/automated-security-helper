# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Module containing the Ferret Scan sensitive data detection scanner implementation."""

import json
import logging
from pathlib import Path
from typing import Annotated, Any, List, Literal

from pydantic import Field

from automated_security_helper.base.options import ScannerOptionsBase
from automated_security_helper.base.scanner_plugin import ScannerPluginConfigBase
from automated_security_helper.models.core import ToolArgs, ToolExtraArg
from automated_security_helper.base.scanner_plugin import ScannerPluginBase
from automated_security_helper.core.exceptions import ScannerError
from automated_security_helper.plugins.decorators import ash_scanner_plugin
from automated_security_helper.schemas.sarif_schema_model import (
    ArtifactLocation,
    Invocation,
    SarifReport,
)
from automated_security_helper.utils.get_shortest_name import get_shortest_name
from automated_security_helper.utils.sarif_utils import attach_scanner_details
from automated_security_helper.utils.subprocess_utils import find_executable

# Path to the default ferret-scan config bundled with this plugin
DEFAULT_FERRET_CONFIG = Path(__file__).parent / "ferret-config.yaml"


class FerretScannerConfigOptions(ScannerOptionsBase):
    """Configuration options for the Ferret scanner."""

    confidence_levels: Annotated[
        Literal["all", "high", "medium", "low", "high,medium", "high,low", "medium,low"],
        Field(
            description="Confidence levels to display: 'high', 'medium', 'low', or combinations"
        ),
    ] = "all"

    checks: Annotated[
        str,
        Field(
            description="Specific checks to run, comma-separated: CREDIT_CARD, EMAIL, "
            "INTELLECTUAL_PROPERTY, IP_ADDRESS, METADATA, PASSPORT, PERSON_NAME, "
            "PHONE, SECRETS, SOCIAL_MEDIA, SSN, or 'all'"
        ),
    ] = "all"

    recursive: Annotated[
        bool,
        Field(description="Recursively scan directories"),
    ] = True

    config_file: Annotated[
        Path | str | None,
        Field(
            description="Path to Ferret configuration file (YAML). "
            "If not specified, uses the default config bundled with this plugin. "
            "Set to a custom path to override the default configuration."
        ),
    ] = None

    use_default_config: Annotated[
        bool,
        Field(
            description="Use the default ferret-config.yaml bundled with this plugin. "
            "Set to False to disable the default config and rely only on ferret-scan's built-in defaults."
        ),
    ] = True

    profile: Annotated[
        str | None,
        Field(
            description="Profile name to use from config file (e.g., 'quick', 'ci', "
            "'security-audit', 'comprehensive')"
        ),
    ] = None

    exclude_patterns: Annotated[
        List[str],
        Field(
            description="File patterns to exclude from scanning (glob patterns)"
        ),
    ] = []

    no_color: Annotated[
        bool,
        Field(description="Disable colored output"),
    ] = True

    quiet: Annotated[
        bool,
        Field(description="Quiet mode - minimal output"),
    ] = False


class FerretScannerConfig(ScannerPluginConfigBase):
    """Configuration for the Ferret scanner."""

    name: Literal["ferret-scan"] = "ferret-scan"
    enabled: bool = True
    options: Annotated[
        FerretScannerConfigOptions,
        Field(description="Configure Ferret Scan sensitive data detector"),
    ] = FerretScannerConfigOptions()


@ash_scanner_plugin
class FerretScanner(ScannerPluginBase[FerretScannerConfig]):
    """Implementation of a sensitive data detection scanner using Ferret Scan.

    Ferret Scan detects sensitive information such as:
    - Credit card numbers (15+ card brands with mathematical validation)
    - Passport numbers (multi-country formats including MRZ)
    - Social Security Numbers (domain-aware validation)
    - Email addresses (RFC-compliant with domain validation)
    - Phone numbers (international and domestic formats)
    - API keys and secrets (40+ patterns including AWS, GitHub, etc.)
    - IP addresses (IPv4 and IPv6)
    - Social media profiles and handles
    - Intellectual property (patents, trademarks, copyrights)
    - Document metadata (EXIF, document properties)
    """

    def model_post_init(self, context):
        if self.config is None:
            self.config = FerretScannerConfig()

        self.command = "ferret-scan"
        self.tool_type = "Secrets"
        self.tool_description = (
            "Ferret Scan is a sensitive data detection tool that scans files "
            "for potential sensitive information such as credit card numbers, "
            "passport numbers, SSNs, API keys, and other secrets."
        )

        self.args = ToolArgs(
            format_arg="--format",
            format_arg_value="sarif",
            output_arg="--output",
            scan_path_arg="--file",
            extra_args=[],
        )

        super().model_post_init(context)

    def validate_plugin_dependencies(self) -> bool:
        """Validate scanner configuration and dependencies.

        Returns:
            bool: True if validation passes
        """
        if self._is_offline_mode():
            self._plugin_log(
                f"Offline mode detected. Checking for pre-installed {self.__class__.__name__}",
                level=logging.INFO,
            )

        ferret_binary = find_executable("ferret-scan")
        if not ferret_binary or ferret_binary is None:
            self._plugin_log(
                "ferret-scan binary not found. Please install it from "
                "https://github.com/awslabs/ferret-scan or via 'pip install ferret-scan'",
                level=logging.ERROR,
            )
            return False

        self.dependencies_satisfied = True
        return True

    def _process_config_options(self):
        """Process configuration options into command line arguments."""
        options = self.config.options

        # Confidence levels
        if options.confidence_levels and options.confidence_levels != "all":
            self.args.extra_args.append(
                ToolExtraArg(key="--confidence", value=options.confidence_levels)
            )

        # Specific checks
        if options.checks and options.checks != "all":
            self.args.extra_args.append(
                ToolExtraArg(key="--checks", value=options.checks)
            )

        # Recursive scanning
        if options.recursive:
            self.args.extra_args.append(
                ToolExtraArg(key="--recursive", value=None)
            )

        # Config file
        config_file_path = self._find_config_file(options.config_file)
        if config_file_path:
            self.args.extra_args.append(
                ToolExtraArg(key="--config", value=str(config_file_path))
            )

        # Profile
        if options.profile:
            self.args.extra_args.append(
                ToolExtraArg(key="--profile", value=options.profile)
            )

        # Exclude patterns
        for pattern in options.exclude_patterns:
            self.args.extra_args.append(
                ToolExtraArg(key="--exclude", value=pattern)
            )

        # No color output
        if options.no_color:
            self.args.extra_args.append(
                ToolExtraArg(key="--no-color", value=None)
            )

        # Quiet mode
        if options.quiet:
            self.args.extra_args.append(
                ToolExtraArg(key="--quiet", value=None)
            )

        return super()._process_config_options()

    def _find_config_file(self, config_file: Path | str | None) -> Path | None:
        """Find the Ferret configuration file.

        Priority order:
        1. Explicitly specified config file (via config_file option)
        2. Config file in source directory (ferret.yaml, .ferret.yaml, etc.)
        3. Default config bundled with this plugin (if use_default_config is True)

        Args:
            config_file: Explicitly specified config file path

        Returns:
            Path to config file if found, None otherwise
        """
        # 1. Check explicitly specified config file
        if config_file:
            path = Path(config_file)
            if path.is_absolute():
                if path.exists():
                    self._plugin_log(
                        f"Using explicitly specified config file: {path}",
                        level=logging.DEBUG,
                    )
                    return path
                else:
                    self._plugin_log(
                        f"Specified config file not found: {path}",
                        level=logging.WARNING,
                    )
                    return None
            # Relative to source directory
            full_path = self.context.source_dir / path
            if full_path.exists():
                self._plugin_log(
                    f"Using config file relative to source: {full_path}",
                    level=logging.DEBUG,
                )
                return full_path
            else:
                self._plugin_log(
                    f"Specified config file not found: {full_path}",
                    level=logging.WARNING,
                )
                return None

        # 2. Search for config files in source directory
        possible_paths = [
            self.context.source_dir / "ferret.yaml",
            self.context.source_dir / "ferret.yml",
            self.context.source_dir / ".ferret.yaml",
            self.context.source_dir / ".ferret.yml",
            self.context.source_dir / ".ash" / "ferret.yaml",
            self.context.source_dir / ".ash" / "ferret-scan.yaml",
        ]

        for path in possible_paths:
            if path.exists():
                self._plugin_log(
                    f"Found Ferret config file in source directory: {path}",
                    level=logging.DEBUG,
                )
                return path

        # 3. Use default config bundled with this plugin
        if self.config.options.use_default_config and DEFAULT_FERRET_CONFIG.exists():
            self._plugin_log(
                f"Using default Ferret config bundled with plugin: {DEFAULT_FERRET_CONFIG}",
                level=logging.DEBUG,
            )
            return DEFAULT_FERRET_CONFIG

        return None

    def _resolve_arguments(
        self, target: Path, results_file: Path | None = None
    ) -> List[str]:
        """Resolve arguments for Ferret scan command.

        Args:
            target: Target to scan
            results_file: Path to write SARIF results

        Returns:
            List[str]: Arguments to pass to Ferret
        """
        # Process configuration options
        self._process_config_options()

        # Build command
        args = [self.command]

        # Add format argument
        if self.args.format_arg and self.args.format_arg_value:
            args.extend([self.args.format_arg, self.args.format_arg_value])

        # Add output file argument
        if results_file and self.args.output_arg:
            args.extend([self.args.output_arg, Path(results_file).as_posix()])

        # Add extra args
        for tool_extra_arg in self.args.extra_args:
            args.append(tool_extra_arg.key)
            if tool_extra_arg.value is not None:
                args.append(str(tool_extra_arg.value))

        # Add target path
        if self.args.scan_path_arg:
            args.append(self.args.scan_path_arg)
        args.append(Path(target).as_posix())

        return args

    def scan(
        self,
        target: Path,
        target_type: Literal["source", "converted"],
        global_ignore_paths: List[Any] = [],
        config: FerretScannerConfig | None = None,
        *args,
        **kwargs,
    ) -> SarifReport | dict | bool:
        """Execute Ferret scan and return results.

        Args:
            target: Path to scan
            target_type: Type of target (source or converted)
            global_ignore_paths: List of paths to ignore
            config: Scanner configuration

        Returns:
            SarifReport containing the scan findings, or dict/bool on error

        Raises:
            ScannerError: If the scan fails
        """
        # Check if the target directory is empty or doesn't exist
        if not target.exists() or (target.is_dir() and not any(target.iterdir())):
            message = (
                f"Target directory {target} is empty or doesn't exist. Skipping scan."
            )
            self._plugin_log(
                message,
                target_type=target_type,
                level=logging.INFO,
                append_to_stream="stderr",
            )
            self._post_scan(target=target, target_type=target_type)
            return True

        try:
            validated = self._pre_scan(
                target=target,
                target_type=target_type,
                config=config,
            )
            if not validated:
                self._post_scan(target=target, target_type=target_type)
                return False
        except ScannerError as exc:
            raise exc

        if not self.dependencies_satisfied:
            self._post_scan(target=target, target_type=target_type)
            return False

        try:
            target_results_dir = self.results_dir.joinpath(target_type)
            results_file = target_results_dir.joinpath("ferret-scan.sarif")
            target_results_dir.mkdir(exist_ok=True, parents=True)

            # Add exclude patterns for global ignore paths
            for ignore_path in global_ignore_paths:
                if hasattr(ignore_path, "path"):
                    self.config.options.exclude_patterns.append(str(ignore_path.path))

            final_args = self._resolve_arguments(target=target, results_file=results_file)

            self._plugin_log(
                f"Running command: {' '.join(final_args)}",
                target_type=target_type,
                level=logging.DEBUG,
            )

            # Run ferret-scan with output to file
            self._run_subprocess(
                command=final_args,
                results_dir=target_results_dir,
                stdout_preference="write",
                stderr_preference="write",
            )

            self._post_scan(target=target, target_type=target_type)

            # Read SARIF output from file
            if not results_file.exists():
                self._plugin_log(
                    f"No results file found at {results_file}",
                    target_type=target_type,
                    level=logging.WARNING,
                )
                return {"findings": [], "errors": self.errors}

            try:
                with open(results_file, "r", encoding="utf-8") as f:
                    scanner_results = json.load(f)

                sarif_report: SarifReport = SarifReport.model_validate(scanner_results)

                # Attach scanner details
                sarif_report = attach_scanner_details(
                    sarif_report=sarif_report,
                    scanner_name=self.config.name,
                    scanner_version=getattr(self, "tool_version", None),
                    invocation_details={
                        "command_line": " ".join(final_args),
                        "arguments": final_args[1:],
                        "working_directory": get_shortest_name(input=target),
                        "start_time": self.start_time.isoformat() if self.start_time else None,
                        "end_time": self.end_time.isoformat() if self.end_time else None,
                        "exit_code": self.exit_code,
                    },
                )

                sarif_report.runs[0].invocations = [
                    Invocation(
                        commandLine=" ".join(final_args),
                        arguments=final_args[1:],
                        startTimeUtc=self.start_time,
                        endTimeUtc=self.end_time,
                        executionSuccessful=self.exit_code == 0,
                        exitCode=self.exit_code,
                        exitCodeDescription="\n".join(self.errors) if self.errors else None,
                        workingDirectory=ArtifactLocation(
                            uri=get_shortest_name(input=target),
                        ),
                    )
                ]

                return sarif_report

            except json.JSONDecodeError as e:
                self._plugin_log(
                    f"Failed to parse Ferret output as JSON: {e}",
                    target_type=target_type,
                    level=logging.ERROR,
                    append_to_stream="stderr",
                )
                return {"findings": [], "errors": [str(e), *self.errors]}

            except Exception as e:
                self._plugin_log(
                    f"Failed to parse Ferret results as SARIF: {e}",
                    target_type=target_type,
                    level=logging.WARNING,
                    append_to_stream="stderr",
                )
                return scanner_results

        except Exception as e:
            raise ScannerError(f"Ferret scan failed: {e}")
