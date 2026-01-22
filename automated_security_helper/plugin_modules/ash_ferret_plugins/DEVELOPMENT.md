# Ferret-Scan Plugin Development Guide

This document is for maintainers and developers working on the ASH Ferret-Scan plugin integration. It covers the architecture, integration points, constraints, and maintenance tasks.

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [File Structure](#file-structure)
- [Integration Features](#integration-features)
- [ASH Conventions](#ash-conventions)
- [Version Compatibility](#version-compatibility)
- [Unsupported Options](#unsupported-options)
- [Testing](#testing)
- [Documentation](#documentation)
- [Common Maintenance Tasks](#common-maintenance-tasks)
- [Gotchas and Caveats](#gotchas-and-caveats)

## Architecture Overview

The ferret-scan plugin follows ASH's scanner plugin architecture:

```
┌─────────────────────────────────────────────────────────────────┐
│                         ASH Orchestrator                         │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ScannerPluginBase (base class)                │
│  - Provides: _pre_scan, _post_scan, _run_subprocess, etc.       │
│  - Handles: results directory, logging, error handling          │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      FerretScanner (this plugin)                 │
│  - Implements: scan(), validate_plugin_dependencies()           │
│  - Handles: config processing, version checking, SARIF output   │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ferret-scan CLI (external tool)               │
│  - Invoked via subprocess                                        │
│  - Output: SARIF format to file                                  │
└─────────────────────────────────────────────────────────────────┘
```

## File Structure

```
automated_security_helper/
└── plugin_modules/
    └── ash_ferret_plugins/
        ├── __init__.py              # Plugin registration (ASH_SCANNERS list)
        ├── ferret_scanner.py        # Main scanner implementation
        ├── ferret-config.yaml       # Default bundled configuration
        ├── README.md                # User documentation
        └── DEVELOPMENT.md           # This file (maintainer docs)

tests/
└── unit/
    └── plugin_modules/
        └── ash_ferret_plugins/
            ├── __init__.py          # Test package marker
            ├── conftest.py          # Shared test fixtures
            └── test_ferret_scanner.py  # Unit tests (64 tests)

docs/
└── content/
    └── docs/
        └── plugins/
            └── community/
                ├── index.md         # Community plugins index (update when adding)
                └── ferret-scan-plugin.md  # Full user documentation
```

## Integration Features

### 1. SARIF Output (Required by ASH)

The plugin always outputs SARIF format, which is required by ASH for result aggregation:

```python
self.args = ToolArgs(
    format_arg="--format",
    format_arg_value="sarif",  # Always SARIF - required by ASH
    ...
)
```

**Why**: ASH aggregates results from multiple scanners into a unified report. SARIF is the standard format that enables this aggregation.

### 2. Debug/Verbose Mode Inheritance

Debug and verbose modes are inherited from ASH's global settings, NOT configured at the plugin level:

```python
def _is_ash_debug_mode(self) -> bool:
    """Check if ASH is running in debug mode."""
    return self._get_ash_log_level() <= logging.DEBUG

def _is_ash_verbose_mode(self) -> bool:
    """Check if ASH is running in verbose mode (level 15)."""
    log_level = self._get_ash_log_level()
    return log_level <= 15 and log_level > logging.DEBUG
```

**Usage**: Run `uv run ash --debug scan ...` or `uv run ash --verbose scan ...` to enable these modes.

### 3. Version Compatibility Checking

The plugin validates ferret-scan version compatibility during dependency validation:

```python
# Version constants (update when ferret-scan releases breaking changes)
MIN_SUPPORTED_VERSION = "0.1.0"
MAX_SUPPORTED_VERSION = "2.0.0"
DEFAULT_VERSION_CONSTRAINT = ">=0.1.0,<2.0.0"
RECOMMENDED_VERSION = "1.0.0"
```

**Behavior**:
- Version check runs during `validate_plugin_dependencies()`
- Incompatible versions log a warning but don't block execution
- Users can bypass with `skip_version_check: true` in config

### 4. Config File Discovery

The plugin searches for ferret-scan config files in this order:

1. Explicitly specified via `config_file` option
2. Auto-discovery in source directory:
   - `ferret.yaml`, `ferret.yml`
   - `.ferret.yaml`, `.ferret.yml`
   - `.ash/ferret.yaml`, `.ash/ferret-scan.yaml`
3. Default config bundled with plugin (`ferret-config.yaml`)

### 5. Unsupported Options Validation

A Pydantic model validator prevents use of incompatible options:

```python
UNSUPPORTED_FERRET_OPTIONS = {
    "format": "ASH requires SARIF format...",
    "debug": "Debug mode is inherited from ASH's global --debug flag...",
    # ... more options
}

@model_validator(mode="before")
@classmethod
def validate_no_unsupported_options(cls, data: Any) -> Any:
    """Validate that no unsupported options are being used."""
    if isinstance(data, dict):
        for key in data.keys():
            normalized_key = key.lower().replace("-", "_")
            if normalized_key in UNSUPPORTED_FERRET_OPTIONS:
                raise ValueError(f"Unsupported option '{key}'...")
    return data
```

## ASH Conventions

### Inherited from ASH (Do NOT configure at plugin level)

| Feature | ASH Flag | Plugin Behavior |
|---------|----------|-----------------|
| Debug mode | `--debug` | Automatically adds `--debug` to ferret-scan |
| Verbose mode | `--verbose` | Automatically adds `--verbose` to ferret-scan |
| Output format | N/A | Always SARIF (hardcoded) |
| Color output | N/A | Always `--no-color` (ASH handles formatting) |
| Suppressions | `.ash/suppressions.yaml` | ASH manages centrally |
| Output directory | `--output-dir` | Uses `.ash/ash_output/scanners/ferret-scan/` |
| Offline mode | `ASH_OFFLINE=true` | Respects environment variable |

### Plugin-Specific Options (CAN be configured)

| Option | Description | Default |
|--------|-------------|---------|
| `confidence_levels` | Filter by confidence: high, medium, low | `"all"` |
| `checks` | Specific checks to run | `"all"` |
| `recursive` | Scan directories recursively | `true` |
| `config_file` | Path to ferret config file | Auto-discovered |
| `profile` | Profile name from config file | None |
| `exclude_patterns` | Glob patterns to exclude | `[]` |
| `show_match` | Display matched text in findings | `false` |
| `enable_preprocessors` | Extract text from documents | `true` |
| `tool_version` | Version constraint for installation | `">=0.1.0,<2.0.0"` |
| `skip_version_check` | Bypass version validation | `false` |

## Version Compatibility

### Updating Version Constants

When ferret-scan releases a new version:

1. **Test the new version** with the plugin
2. **Update constants** in `ferret_scanner.py`:

```python
# If new version is compatible:
MAX_SUPPORTED_VERSION = "3.0.0"  # Bump to next major
DEFAULT_VERSION_CONSTRAINT = ">=0.1.0,<3.0.0"

# If new version has breaking changes:
# Add version-specific handling in the code
```

3. **Update tests** in `test_ferret_scanner.py` if needed
4. **Update documentation** in README.md and ferret-scan-plugin.md

### Version Helper Functions

```python
parse_version("1.2.3")  # Returns (1, 2, 3)
compare_versions("1.0.0", "2.0.0")  # Returns -1 (v1 < v2)
is_version_compatible("1.5.0", "1.0.0", "2.0.0")  # Returns True
```

## Unsupported Options

### Adding New Unsupported Options

If ferret-scan adds a new option that conflicts with ASH:

1. **Add to `UNSUPPORTED_FERRET_OPTIONS`** dictionary:

```python
UNSUPPORTED_FERRET_OPTIONS = {
    # ... existing options ...
    "new_option": "Explanation of why this option is not supported in ASH.",
}
```

2. **Add a test** in `TestFerretScannerUnsupportedOptions`:

```python
def test_unsupported_option_new_option_raises_error(self):
    """Test that using 'new_option' raises an error."""
    with pytest.raises(ValueError) as exc_info:
        FerretScannerConfigOptions(new_option=True)
    
    assert "Unsupported option 'new_option'" in str(exc_info.value)
```

3. **Update documentation** in README.md

### Categories of Unsupported Options

| Category | Options | Reason |
|----------|---------|--------|
| Output format | `format`, `output_format` | ASH requires SARIF |
| Web server | `web`, `port` | Not applicable for batch scanning |
| Redaction | `enable_redaction`, `redaction_*`, `memory_scrub` | Post-processing, not scanning |
| Suppressions | `generate_suppressions`, `show_suppressed`, `suppressions_file` | ASH manages centrally |
| Utility modes | `extract_text` | Not a scanning mode |
| Logging | `debug`, `verbose` | Inherited from ASH |

## Testing

### Running Tests

```bash
# Run all ferret plugin tests
uv run pytest tests/unit/plugin_modules/ash_ferret_plugins/ -v --no-cov -n 0

# Run specific test class
uv run pytest tests/unit/plugin_modules/ash_ferret_plugins/test_ferret_scanner.py::TestFerretScannerConfig -v

# Run with coverage
uv run pytest tests/unit/plugin_modules/ash_ferret_plugins/ -v --cov=automated_security_helper.plugin_modules.ash_ferret_plugins
```

### Test Structure

The tests are organized into classes by functionality:

| Test Class | Purpose |
|------------|---------|
| `TestFerretScannerConfig` | Configuration initialization |
| `TestFerretScannerUnsupportedOptions` | Unsupported option validation |
| `TestFerretScannerConfigProcessing` | Config to CLI argument translation |
| `TestFerretScannerASHConventions` | ASH convention compliance |
| `TestFerretScannerConfigFileDiscovery` | Config file auto-discovery |
| `TestFerretScannerDependencies` | Dependency validation |
| `TestFerretScannerArgumentResolution` | CLI argument building |
| `TestFerretScannerScanning` | Scan workflow |
| `TestFerretScannerTargetValidation` | Target directory validation |
| `TestFerretScannerErrorHandling` | Error handling |
| `TestFerretScannerVersionSupport` | Version compatibility |

### Key Test Fixtures (in `conftest.py`)

```python
@pytest.fixture
def mock_plugin_context(tmp_path):
    """Creates a mock PluginContext with temp directories."""

@pytest.fixture
def default_ferret_config():
    """Returns default FerretScannerConfig."""

@pytest.fixture
def custom_ferret_config():
    """Returns FerretScannerConfig with custom options."""

@pytest.fixture
def mock_sarif_response():
    """Returns a valid SARIF response dict."""

@pytest.fixture
def mock_ferret_config_file(mock_plugin_context):
    """Creates a ferret.yaml file in the source directory."""
```

## Documentation

### Files to Update

When making changes to the plugin:

| Change Type | Files to Update |
|-------------|-----------------|
| New option | `ferret_scanner.py`, `README.md`, `ferret-scan-plugin.md`, `test_ferret_scanner.py` |
| New unsupported option | `ferret_scanner.py`, `README.md`, `test_ferret_scanner.py` |
| Version update | `ferret_scanner.py`, `README.md`, `ferret-scan-plugin.md` |
| Bug fix | `ferret_scanner.py`, `test_ferret_scanner.py` |
| Architecture change | All files including `DEVELOPMENT.md` |

### Documentation Locations

- **User docs**: `automated_security_helper/plugin_modules/ash_ferret_plugins/README.md`
- **Full docs**: `docs/content/docs/plugins/community/ferret-scan-plugin.md`
- **Community index**: `docs/content/docs/plugins/community/index.md`
- **Developer docs**: `automated_security_helper/plugin_modules/ash_ferret_plugins/DEVELOPMENT.md` (this file)

## Common Maintenance Tasks

### Task 1: Update for New ferret-scan Version

1. Install the new version: `pip install ferret-scan==X.Y.Z`
2. Run the test suite: `uv run pytest tests/unit/plugin_modules/ash_ferret_plugins/ -v`
3. If tests pass, update version constants if needed
4. If tests fail, add version-specific handling or update tests

### Task 2: Add a New Supported Option

1. Add field to `FerretScannerConfigOptions` class:
   ```python
   new_option: Annotated[
       bool,
       Field(description="Description of the option"),
   ] = False
   ```

2. Add processing in `_process_config_options()`:
   ```python
   if options.new_option:
       self.args.extra_args.append(
           ToolExtraArg(key="--new-option", value=None)
       )
   ```

3. Add tests in `test_ferret_scanner.py`
4. Update documentation

### Task 3: Handle Breaking Change in ferret-scan

1. Identify the breaking change
2. Add version-specific handling:
   ```python
   if compare_versions(self.tool_version, "2.0.0") >= 0:
       # New behavior for v2.0.0+
   else:
       # Old behavior
   ```
3. Update version constants
4. Update tests and documentation

## Gotchas and Caveats

### 1. Subprocess Mocking in Tests

When testing the scan workflow, you must mock multiple methods:

```python
with patch.object(scanner, '_pre_scan', return_value=True), \
     patch.object(scanner, '_post_scan'), \
     patch.object(scanner, '_run_subprocess') as mock_subprocess, \
     patch.object(scanner, '_plugin_log'), \
     patch("builtins.open", mock_open(read_data=json.dumps(mock_sarif_response))), \
     patch("pathlib.Path.exists", return_value=True):
```

**Why**: The scanner uses subprocess to run ferret-scan, and we don't want to actually execute it in unit tests.

### 2. Version Check During Dependency Validation

The version check runs during `validate_plugin_dependencies()`, not during scanning. This means:

- Version warnings appear early in the scan process
- Incompatible versions don't block execution (just warn)
- The `skip_version_check` option must be set before validation

### 3. Config File Discovery Order

The config file discovery has a specific priority order. If a user specifies `config_file` but it doesn't exist, the plugin will NOT fall back to auto-discovery - it will return `None` and log a warning.

### 4. Debug/Verbose Mode Detection

The verbose level in ASH is 15 (between DEBUG=10 and INFO=20). The `_is_ash_verbose_mode()` method checks for this specific range:

```python
return log_level <= 15 and log_level > logging.DEBUG
```

### 5. SARIF Output File Location

The SARIF output file is written to:
```
{results_dir}/{target_type}/ferret-scan.sarif
```

For example: `.ash/ash_output/scanners/ferret-scan/source/ferret-scan.sarif`

### 6. Empty Directory Handling

Empty or non-existent target directories return `True` (skip), not `False` (failure). This is intentional - there's nothing to scan.

### 7. Pydantic Model Validator Timing

The `validate_no_unsupported_options` validator runs in `mode="before"`, meaning it validates the raw input dict before Pydantic processes it. This catches unsupported options even if they're not defined as fields.

### 8. Extra Args Accumulation

The `_process_config_options()` method appends to `self.args.extra_args`. If called multiple times (e.g., in tests), args will accumulate. The scanner creates a fresh `ToolArgs` in `model_post_init`, so this is only an issue if you call `_process_config_options()` multiple times on the same scanner instance.

## Manual Testing Guide

Before releasing changes to the ferret-scan plugin, perform these manual tests to verify end-to-end functionality.

### Test Data Location

The project includes comprehensive test data for ferret-scan at:
```
tests/test_data/scanners/ferret-scan/
├── sample.txt       # Text file with various sensitive data patterns
└── 10-MB-Test.docx  # Large document for preprocessor testing
```

The `sample.txt` file contains examples across confidence levels:
- **High confidence**: Valid credit cards (Visa, MasterCard, AMEX, Discover, JCB), valid passports (US, UK, Canadian, EU, MRZ)
- **Medium confidence**: Test cards, suspicious passport patterns
- **Low confidence**: Invalid checksums, repeated digits, wrong lengths
- **False positives**: SKUs, serial numbers, phone numbers, dates, code snippets
- **Edge cases**: Mathematical constants, formatting variations, mixed contexts
- **International examples**: European, Asian, North American formats

### Prerequisites

```bash
# Ensure ferret-scan is installed
pip install ferret-scan
ferret-scan --version
```

### Test Scenarios

#### 1. Basic Plugin Discovery

```bash
# Verify plugin is discovered by ASH (using command line flag)
uv run ash plugin list --ash-plugin-modules automated_security_helper.plugin_modules.ash_ferret_plugins | grep -i ferret
# Expected: ferret-scan should appear in the list

# Or add to .ash/.ash.yaml and run:
# ash_plugin_modules:
#   - automated_security_helper.plugin_modules.ash_ferret_plugins
uv run ash plugin list | grep -i ferret
```

#### 2. Basic Scan with Test Data

```bash
# Run a basic scan using the project's test data
uv run ash scan --source-dir tests/test_data/scanners/ferret-scan --scanners ferret-scan \
    --ash-plugin-modules automated_security_helper.plugin_modules.ash_ferret_plugins

# Check output
ls -la .ash/ash_output/scanners/ferret-scan/source/
# Expected: ferret-scan.sarif file should exist with findings
```

#### 3. SARIF Output Verification

```bash
# Verify SARIF format
cat .ash/ash_output/scanners/ferret-scan/source/ferret-scan.sarif | jq '.version'
# Expected: "2.1.0"

# Check for findings (should find credit cards, passports, SSNs, etc.)
cat .ash/ash_output/scanners/ferret-scan/source/ferret-scan.sarif | jq '.runs[0].results | length'
# Expected: > 0 (should find many sensitive data patterns)

# View finding types
cat .ash/ash_output/scanners/ferret-scan/source/ferret-scan.sarif | jq '[.runs[0].results[].ruleId] | unique'
# Expected: Various rule IDs for credit cards, passports, etc.
```

#### 4. Debug Mode Inheritance

```bash
# Run with ASH debug mode (with plugin module flag)
uv run ash --debug scan --source-dir tests/test_data/scanners/ferret-scan --scanners ferret-scan \
    --ash-plugin-modules automated_security_helper.plugin_modules.ash_ferret_plugins 2>&1 | grep -i "debug"
# Expected: Should see debug output from both ASH and ferret-scan
```

#### 5. Verbose Mode Inheritance

```bash
# Run with ASH verbose mode
uv run ash --verbose scan --source-dir tests/test_data/scanners/ferret-scan --scanners ferret-scan \
    --ash-plugin-modules automated_security_helper.plugin_modules.ash_ferret_plugins 2>&1
# Expected: Should see verbose output
```

#### 6. Custom Configuration Options

```bash
# Test with high confidence only
uv run ash scan --source-dir tests/test_data/scanners/ferret-scan --scanners ferret-scan \
    --ash-plugin-modules automated_security_helper.plugin_modules.ash_ferret_plugins \
    --config-overrides "scanners.ferret-scan.options.confidence_levels=high"
# Expected: Should only show high-confidence findings (fewer results)

# Test with specific checks
uv run ash scan --source-dir tests/test_data/scanners/ferret-scan --scanners ferret-scan \
    --ash-plugin-modules automated_security_helper.plugin_modules.ash_ferret_plugins \
    --config-overrides "scanners.ferret-scan.options.checks=CREDIT_CARD"
# Expected: Should only show credit card findings
```

#### 7. Version Compatibility Warning

```bash
# If you have an incompatible version installed, verify warning is shown
uv run ash scan --source-dir tests/test_data/scanners/ferret-scan --scanners ferret-scan \
    --ash-plugin-modules automated_security_helper.plugin_modules.ash_ferret_plugins 2>&1 | grep -i "version"
```

#### 8. Unsupported Option Error

```bash
# Test that unsupported options raise clear errors
# Create a config file with unsupported option
cat > /tmp/test-ash-config.yaml << 'EOF'
ash_plugin_modules:
  - automated_security_helper.plugin_modules.ash_ferret_plugins
scanners:
  ferret-scan:
    enabled: true
    options:
      debug: true  # This should fail
EOF

uv run ash scan --source-dir tests/test_data/scanners/ferret-scan --config /tmp/test-ash-config.yaml 2>&1
# Expected: Error message about unsupported 'debug' option
rm /tmp/test-ash-config.yaml
```

#### 9. Empty Directory Handling

```bash
mkdir -p /tmp/empty-test-dir
uv run ash scan --source-dir /tmp/empty-test-dir --scanners ferret-scan \
    --ash-plugin-modules automated_security_helper.plugin_modules.ash_ferret_plugins 2>&1
# Expected: Should skip gracefully with appropriate message
rmdir /tmp/empty-test-dir
```

#### 10. Missing Binary Handling

```bash
# Temporarily rename ferret-scan binary
FERRET_PATH=$(which ferret-scan)
# Rename it, then run:
uv run ash scan --source-dir tests/test_data/scanners/ferret-scan --scanners ferret-scan \
    --ash-plugin-modules automated_security_helper.plugin_modules.ash_ferret_plugins 2>&1
# Expected: Clear error about missing ferret-scan binary
# Remember to restore the binary!
```

#### 11. Profile Usage

```bash
# Test using a profile from the default config
uv run ash scan --source-dir tests/test_data/scanners/ferret-scan --scanners ferret-scan \
    --ash-plugin-modules automated_security_helper.plugin_modules.ash_ferret_plugins \
    --config-overrides "scanners.ferret-scan.options.profile=quick"
# Expected: Should use the 'quick' profile settings (high confidence only)
```

#### 12. ASH Report Integration

```bash
# Verify ferret-scan results are included in aggregated ASH report
uv run ash scan --source-dir tests/test_data/scanners/ferret-scan \
    --ash-plugin-modules automated_security_helper.plugin_modules.ash_ferret_plugins
cat .ash/ash_output/reports/ash.sarif | jq '.runs[] | select(.tool.driver.name == "ferret-scan")'
# Expected: ferret-scan run should be present in aggregated report
```

#### 13. Combined with Other Scanners

```bash
# Run ferret-scan alongside other scanners
uv run ash scan --source-dir tests/test_data/scanners/ferret-scan --scanners ferret-scan,bandit \
    --ash-plugin-modules automated_security_helper.plugin_modules.ash_ferret_plugins
# Expected: Both scanners should run and results should be aggregated
```

#### 14. Document Preprocessing (DOCX)

```bash
# Test text extraction from Office documents
uv run ash scan --source-dir tests/test_data/scanners/ferret-scan --scanners ferret-scan \
    --ash-plugin-modules automated_security_helper.plugin_modules.ash_ferret_plugins \
    --config-overrides "scanners.ferret-scan.options.enable_preprocessors=true"
# Expected: Should scan both sample.txt and extract text from 10-MB-Test.docx
```

### Quick Smoke Test Script

```bash
#!/bin/bash
# Save as test-ferret-plugin.sh

set -e

echo "=== Ferret Plugin Smoke Test ==="

# Use project test data
TEST_DIR="tests/test_data/scanners/ferret-scan"
OUTPUT_DIR=".ash/ash_output"

echo "Test data directory: $TEST_DIR"

# Clean previous output
rm -rf "$OUTPUT_DIR"

# Run scan (with plugin module flag)
echo "Running ASH scan..."
uv run ash scan --source-dir "$TEST_DIR" --scanners ferret-scan \
    --ash-plugin-modules automated_security_helper.plugin_modules.ash_ferret_plugins

# Verify output
if [ -f "$OUTPUT_DIR/scanners/ferret-scan/source/ferret-scan.sarif" ]; then
    echo "✓ SARIF output file created"
    
    FINDINGS=$(cat "$OUTPUT_DIR/scanners/ferret-scan/source/ferret-scan.sarif" | jq '.runs[0].results | length')
    echo "✓ Found $FINDINGS findings"
    
    if [ "$FINDINGS" -gt 0 ]; then
        echo "✓ Smoke test PASSED"
        
        # Show summary of finding types
        echo ""
        echo "Finding types detected:"
        cat "$OUTPUT_DIR/scanners/ferret-scan/source/ferret-scan.sarif" | jq -r '[.runs[0].results[].ruleId] | group_by(.) | map({rule: .[0], count: length}) | .[] | "  \(.rule): \(.count)"'
    else
        echo "✗ No findings detected (expected many)"
        exit 1
    fi
else
    echo "✗ SARIF output file not found"
    exit 1
fi

echo ""
echo "=== Test Complete ==="
```

### Cleanup

```bash
# Remove ASH output (test data is part of the project, don't delete it)
rm -rf .ash/ash_output
```

## Related Resources

- [ferret-scan GitHub Repository](https://github.com/awslabs/ferret-scan)
- [ASH Plugin Development Guide](../../../docs/content/docs/plugins/development-guide.md)
- [ASH Scanner Plugin Architecture](../../../docs/content/docs/plugins/scanner-plugins.md)
- [SARIF Specification](https://sarifweb.azurewebsites.net/)
