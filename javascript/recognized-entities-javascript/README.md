# GS1 License Validation — JavaScript Credential Validator

A single JavaScript credential validator for all GS1 license credential types per W3C Recognized Entities v1.0.

## Building

Prerequisites: [Node.js](https://nodejs.org/) (v18+)

```bash
cd javascript/recognized-entities-javascript/build
npm install
node compile-schemas.js
node bundle-validator.js
```

This produces `gs1-license-validation.mjs` in the parent directory.

After building, update the `digestMultibase` values in all sample credentials to match the new build:

```bash
# Compute the new digest (multihash-encoded SHA-256, base64url, multibase 'u' prefix)
NEW_DIGEST=$(python3 -c "
import hashlib, base64
from pathlib import Path
d = hashlib.sha256(Path('gs1-license-validation.mjs').read_bytes()).digest()
print('u' + base64.urlsafe_b64encode(bytes([0x12,0x20]) + d).decode().rstrip('='))
")
echo "New digest: $NEW_DIGEST"

# Replace the old digest in all sample credentials
OLD_DIGEST=$(grep -roh 'uEi[A-Za-z0-9_-]\{40,\}' \
  ../../jsons/recognized-entities-javascript/gcp-sample.json | head -1)
find ../../jsons/recognized-entities-javascript -name '*.json' \
  -exec sed -i "s/$OLD_DIGEST/$NEW_DIGEST/g" {} +
```

## What it does

The bundled validator combines:

1. **Compiled JSON Schema validation** (AJV standalone output) — structural validation of the 6 base credential types
2. **Cross-credential field checks** — verifies scope narrowing (e.g., GCP falls under prefix, GTIN falls under GCP)
3. **Chain continuity enforcement** — ensures every `recognizedTo` action references a JavaScript validator with an approved digest

## Testing

From the `jsons/recognized-entities-javascript/` directory:

```bash
# Run all happy-path samples
source runall.sh

# Run all error samples
source run_errs.sh

# Run a single credential
python3 validate_credential.py <credential.json>
```

Requires: `pip install jsonschema referencing quickjs`
