# ASH Ferret Scan Plugin

This plugin integrates [Ferret Scan](https://github.com/awslabs/ferret-scan) into the Automated Security Helper (ASH) for sensitive data detection.

## Overview

Ferret Scan is a sensitive data detection tool that scans files for potential sensitive information including:

- **Credit Card Numbers** - 15+ card brands with mathematical validation
- **Passport Numbers** - Multi-country formats (US, UK, Canada, EU, MRZ)
- **Social Security Numbers** - Domain-aware validation with HR/Tax/Healthcare context
- **Email Addresses** - RFC-compliant with domain validation
- **Phone Numbers** - International and domestic formats
- **API Keys & Secrets** - 40+ patterns (AWS, GitHub, Google Cloud, Stripe, etc.)
- **IP Addresses** - IPv4 and IPv6 with network context
- **Social Media Profiles** - LinkedIn, Twitter/X, Facebook, GitHub, etc.
- **Intellectual Property** - Patents, trademarks, copyrights, trade secrets
- **Document Metadata** - EXIF and document metadata extraction

## Installation

### Prerequisites

Install Ferret Scan:

```bash
# Via pip (recommended)
pip install ferret-scan

# Or build from source
git clone https://github.com/awslabs/ferret-scan.git
cd ferret-scan
make build
```

### Enable the Plugin

Add the plugin module to your ASH configuration:

```yaml
ash_plugin_modules:
  - automated_security_helper.plugin_modules.ash_ferret_plugins
```

## Configuration

### Default Configuration

This plugin includes a default `ferret-config.yaml` that is automatically used when no custom config is specified. The default config includes:

- Comprehensive validator patterns for intellectual property detection
- Social media platform detection patterns
- Pre-configured profiles for common use cases (quick, thorough, ci, security-audit, etc.)
- AWS/Amazon internal URL patterns for IP detection

### Basic Configuration

```yaml
scanners:
  ferret-scan:
    enabled: true
    options:
      confidence_levels: "all"  # high, medium, low, or combinations
      checks: "all"             # or specific: CREDIT_CARD,EMAIL,SECRETS
      recursive: true
```

### Overriding the Default Config

You can override the default configuration in several ways:

#### Option 1: Provide a custom config file path

```yaml
scanners:
  ferret-scan:
    enabled: true
    options:
      config_file: "/path/to/your/custom-ferret.yaml"
```

#### Option 2: Place a config file in your source directory

The plugin searches for config files in this order:
1. Explicitly specified `config_file` path
2. `ferret.yaml` or `.ferret.yaml` in the source directory
3. `.ash/ferret.yaml` or `.ash/ferret-scan.yaml` in the source directory
4. Default config bundled with this plugin

Simply create a `ferret.yaml` or `.ferret.yaml` in your project root to override the defaults.

#### Option 3: Disable the default config entirely

```yaml
scanners:
  ferret-scan:
    enabled: true
    options:
      use_default_config: false  # Use ferret-scan's built-in defaults only
```

### Advanced Configuration

```yaml
scanners:
  ferret-scan:
    enabled: true
    options:
      confidence_levels: "high,medium"
      checks: "CREDIT_CARD,SECRETS,SSN,PASSPORT"
      recursive: true
      profile: "security-audit"  # Use predefined profile from config
      config_file: "my-ferret-config.yaml"  # Custom config file
      exclude_patterns:
        - "*.log"
        - "node_modules/**"
        - "vendor/**"
      quiet: false
      no_color: true
```

### Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `confidence_levels` | string | `"all"` | Confidence levels: `high`, `medium`, `low`, or combinations |
| `checks` | string | `"all"` | Specific checks to run (comma-separated) |
| `recursive` | bool | `true` | Recursively scan directories |
| `config_file` | string | `null` | Path to custom Ferret YAML config file |
| `use_default_config` | bool | `true` | Use the default config bundled with this plugin |
| `profile` | string | `null` | Profile name from config file |
| `exclude_patterns` | list | `[]` | Glob patterns to exclude |
| `no_color` | bool | `true` | Disable colored output |
| `quiet` | bool | `false` | Minimal output mode |

### Available Checks

- `CREDIT_CARD` - Credit card numbers
- `EMAIL` - Email addresses
- `INTELLECTUAL_PROPERTY` - Patents, trademarks, copyrights
- `IP_ADDRESS` - IPv4 and IPv6 addresses
- `METADATA` - Document and image metadata
- `PASSPORT` - Passport numbers
- `PERSON_NAME` - Person names
- `PHONE` - Phone numbers
- `SECRETS` - API keys, tokens, passwords
- `SOCIAL_MEDIA` - Social media profiles
- `SSN` - Social Security Numbers

### Available Profiles (in default config)

- `quick` - Fast security check (high confidence only)
- `thorough` - All confidence levels with text extraction
- `ci` - CI/CD integration (JUnit XML output)
- `security-audit` - Security team scanning (JSON output)
- `comprehensive` - Complete analysis (YAML output)
- `credit-card` - PCI compliance focused
- `passport` - Identity verification focused
- `intellectual-property` - IP detection focused
- `json-api` - Structured JSON for APIs
- `csv-export` - CSV for spreadsheet analysis
- `silent` - Minimal output for automation

## Creating a Custom Config File

To create your own config file, you can:

1. Copy the default config from the plugin:
   ```bash
   cp $(python -c "import automated_security_helper.plugin_modules.ash_ferret_plugins as p; print(p.__path__[0])")/ferret-config.yaml ./my-ferret-config.yaml
   ```

2. Or create a minimal config that only overrides what you need:
   ```yaml
   # my-ferret-config.yaml
   defaults:
     confidence_levels: high,medium
     checks: SECRETS,CREDIT_CARD,SSN
   
   validators:
     intellectual_property:
       internal_urls:
         - "http[s]?:\\/\\/.*\\.mycompany\\.com"
         - "http[s]?:\\/\\/internal\\..*"
   ```

## Output

The plugin outputs results in SARIF format, which is automatically aggregated with other ASH scanner results.

## Example Usage

```bash
# Run ASH with Ferret Scan enabled
ash --source-dir /path/to/code

# Run only Ferret Scan
ash --source-dir /path/to/code --scanners ferret-scan

# Run with a custom config file
ash --source-dir /path/to/code \
    --scanners ferret-scan \
    --config-overrides "scanners.ferret-scan.options.config_file=/path/to/custom.yaml"
```

## License

Apache-2.0
