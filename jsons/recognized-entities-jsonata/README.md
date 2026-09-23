# Recognized Entities Sample Credentials (JSONata Variant)

These samples demonstrate the GS1 trust chain using the W3C Recognized Entities 1.0 specification, with **JSONata-generated schemas** for cross-document field constraints instead of the FieldMatch output validation type.

## How It Works

Where the FieldMatch variant uses a custom `type: "FieldMatch"` output validation, this variant uses `type: "Jsonata"` with a `generator` field pointing to a JSONata expression. Static schemas use `type: "JsonSchema"` with an `id` field as before:

```json
"outputValidation": [
  {
    "type": "JsonSchema",
    "id": "https://.../base/gs1-key-credential.json"
  },
  {
    "type": "Jsonata",
    "generator": "https://.../jsonata/idkey-to-key.jsonata"
  }
]
```

At validation time, the verifier:

1. Loads the JSONata expression from the `generator` URL
2. Evaluates it against the **parent credential** (the one containing the outputValidation)
3. Gets back a standard JSON Schema with concrete values baked in
4. Validates the **child credential** against that generated schema

The JSONata expression is static (one per credential type, not per instance), auditable, and enforceable by base schemas via `const` on the generator URL.

## Generators

| Generator | Transition | What it produces |
|---|---|---|
| `prefix-to-gcp.jsonata` | Prefix → GCP | Pattern: child licenseValue starts with parent prefix + digits |
| `8prefix-to-idkey.jsonata` | 8-Prefix → ID Key License | Pattern: zero-padded prefix + digits |
| `gcp-to-key.jsonata` | GCP → Key Credential | Pattern: Digital Link contains GCP under a GS1 AI |
| `gcp-to-idkey.jsonata` | GCP → ID Key License | Pattern: child licenseValue extends GCP |
| `idkey-to-key.jsonata` | ID Key License → Key Credential | Pattern: Digital Link uses AI 01 with licensed GTIN |
| `key-to-key.jsonata` | Key → Key (batch) | Pattern: child Digital Link starts with parent's + /10/ |
| `key-to-data.jsonata` | Key → Data | Pattern: exact match on Digital Link |

## Entities

- **GO** (GS1 Global Office) — `did:web:...fake_go_did` — Trusted root
- **MO** (GS1 Utopia, Member Organization) — `did:web:...fake_mo_did`
- **MC** (Healthy Tots, Member Company) — `did:web:...fake_mc_did`
- **Delegated** (Delegated Data Provider) — `did:web:...fake_delegated_did`

## Trust Chains

Same chain structure as the FieldMatch variant — see `../recognized-entities-field/README.md` for chain diagrams.

## Running

```bash
pip install jsonschema referencing jsonata-python
python validate_credential.py <credential.json>
```

## Error Samples

The `errors/` directory contains credentials that should fail validation:

- `key-credential-scope-broadening-sample.json` — child claims different GTIN
- `key-credential-wrong-type-sample.json` — issues wrong credential type
- `data-credential-cross-gtin-sample.json` — data credential for wrong GTIN
- `data-credential-skip-chain-sample.json` — skips key credential level
- `key-credential-no-fieldmatch-sample.json` — no generator in delegation
- `key-credential-extra-action-sample.json` — second action lacks generator
- `key-credential-widened-pattern-sample.json` — wrong generator URL
- `batch-data-credential-wrong-batch-sample.json` — data for wrong batch
- `batch-data-credential-wrong-data-sample.json` — unauthorized data fields
