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

## Template Mappings

The test suite maps templates to JSON files as follows:

### gs1-sample-license-template.svg
Used for license credentials:
- gcp-sample.json
- gs1-prefix-license-sample.json
- gln-key-credential-sample.json (if license type)
- gtin8-id-key-license-sample.json
- gtin8-prefix-sample.json
- id-key-license-sample.json

### gs1-sample-key-template.svg
Used for key credentials:
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

