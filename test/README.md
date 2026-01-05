# GS1 Template Testing

This directory contains a test suite for validating GS1 Mustache templates.

## Overview

The test suite validates that all Mustache templates in the `../templates/` directory can be successfully rendered with their corresponding JSON credential files from the `../jsons/` directory.

## Setup

Install dependencies:

```bash
npm install
```

## Running Tests

Run all template tests:

```bash
npm test
```

This will:
1. Load each Mustache template from `../templates/`
2. Render it with appropriate JSON files from `../jsons/`
3. Validate that rendering completes without errors
4. Save rendered SVG files to `./output/` directory

## Computing Template Digests

To compute cryptographic hashes (digestMultibase) for templates:

```bash
node compute-digests.mjs
```

This script:
1. Computes SHA-256 hashes for all SVG templates in `../templates/`
2. Encodes them as multibase (base64url-nopad with 'u' prefix)
3. Follows the W3C VC Render Method specification format
4. Outputs digestMultibase values for use in credential `renderMethod` properties

The digestMultibase provides cryptographic integrity verification for templates, protecting against tampering and display attacks. According to the W3C specification, the format is:
- Multibase prefix: `u` (base64url-nopad)
- Multihash: SHA-256 (0x12) with 32-byte output (0x20)
- Full format: `u` + base64url(0x12 + 0x20 + SHA256(template))

## Template Mappings

The test suite maps templates to JSON files as follows:

### gs1-sample-license-template.svg
Used for license credentials:
- gcp-sample.json
- gs1-prefix-license-sample.json
- gtin8-id-key-license-sample.json
- gtin8-prefix-sample.json
- id-key-license-sample.json

### gs1-sample-key-template.svg
Used for key credentials:
- gln-key-credential-sample.json
- gtin-key-credential-sample.json
- gtin-batch-key-credential-sample.json
- gtin-serial-key-credential-sample.json
- grai-key-credential-sample.json
- sscc-key-credential-sample.json

### gs1-sample-product-data-template.svg
Used for data credentials:
- product-data-credential-sample.json
- organization-data-credential-sample.json
- grai-data-credential-sample.json
- sscc-data-credential-sample.json

## Output

Rendered SVG files are saved to the `./output/` directory for manual inspection.

## Mustache Syntax

The templates use standard Mustache syntax:
- Variables: `{{variableName}}`
- Dotted names: `{{object.property.nested}}`
- Sections: `{{#section}}...{{/section}}`
- Inverted sections: `{{^section}}...{{/section}}`
- Comments: `{{! comment }}`

For more information, see: https://mustache.github.io/

