# FieldMatch: A Proposed Output Validation Type for W3C Recognized Entities

## Problem

The W3C Recognized Entities 1.0 specification supports delegation chains where a credential's `recognizedTo` action authorizes a subject to issue child credentials, constrained by an `outputValidation` of type `JsonSchema`. However, JSON Schema cannot express **cross-document field constraints** — rules like "the child credential's `gs1DigitalLink` must extend this credential's `gs1DigitalLink`."

Without cross-document constraints, every credential in a delegation chain requires a generated output validation schema with instance-specific patterns baked in. This creates two problems:

1. **Schema proliferation**: Every credential instance needs its own generated schema whose only unique content is a pattern derived from a field in the parent credential.

2. **Transitivity cannot be enforced**: A base schema can require that a specific FieldMatch pattern template is present (via JSON Schema `const`), because the template is the same for every instance of that credential type. A base schema cannot require a specific generated schema URL, because each instance has a different URL. Without base schema enforcement, nothing guarantees that every credential in the chain carries scope-narrowing constraints forward — any link that omits the constraint breaks the chain.

## Proposal

Introduce `FieldMatch` as a new output validation type alongside `JsonSchema`. A `FieldMatch` rule declares that a field in the child credential must match a regex pattern derived from a field in the parent credential.

```json
{
  "type": "FieldMatch",
  "sourceField": "credentialSubject.gs1DigitalLink",
  "outputField": {
    "path": "credentialSubject.gs1DigitalLink",
    "pattern": "^{sourceValue}"
  }
}
```

### Fields

| Field | Description |
|---|---|
| `type` | `"FieldMatch"` |
| `sourceField` | Dot-delimited path to the field in the current (parent) credential |
| `outputField.path` | Dot-delimited path to the field in the child credential being validated |
| `outputField.pattern` | Regex pattern with `{sourceValue}` placeholder, resolved at validation time |

### Evaluation

At validation time, the verifier:

1. Resolves `sourceField` to a value in the parent credential
2. Replaces `{sourceValue}` in `outputField.pattern` with the regex-escaped source value
3. Matches the resulting regex against the value at `outputField.path` in the child credential

The `{sourceValue}` placeholder is resolved dynamically from the live parent credential, never baked in at issuance time.

### Semantics

FieldMatch rules participate in the existing output validation semantics:

- **Within a `recognizedTo` action**: All output validations must pass (AND). A `JsonSchema` validates type and structure; a `FieldMatch` constrains scope.
- **Across `recognizedTo` actions**: At least one action must fully pass (OR).

## Example: Transitive Scope Narrowing in a GS1 Delegation Chain

Consider a 3-level delegation: an ID key license authorizes a key credential, which authorizes a batch key credential, which authorizes a data credential. Each level carries a FieldMatch that narrows scope, and the base schema at each level enforces that the FieldMatch is present.

**Level 1 — ID key license** (`licenseValue: "00810159560115"`) authorizes key credentials:

```json
"outputValidation": [
  { "type": "JsonSchema", "id": "https://.../base/gs1-key-credential.json" },
  {
    "type": "FieldMatch",
    "sourceField": "credentialSubject.licenseValue",
    "outputField": {
      "path": "credentialSubject.gs1DigitalLink",
      "pattern": "^https://id\\.gs1\\.org/01/{sourceValue}"
    }
  }
]
```

At validation, `{sourceValue}` resolves to `00810159560115`. The child key credential's `gs1DigitalLink` must match `^https://id\.gs1\.org/01/00810159560115`. A child claiming a different GTIN fails.

**Level 2 — Key credential** (`gs1DigitalLink: "https://id.gs1.org/01/00810159560115"`) authorizes batch key credentials:

```json
"outputValidation": [
  { "type": "JsonSchema", "id": "https://.../base/gs1-key-credential.json" },
  {
    "type": "FieldMatch",
    "sourceField": "credentialSubject.gs1DigitalLink",
    "outputField": {
      "path": "credentialSubject.gs1DigitalLink",
      "pattern": "^{sourceValue}/10/"
    }
  }
]
```

The child batch key credential's `gs1DigitalLink` must start with the parent's value plus `/10/` (the batch/lot AI). A child claiming a different GTIN or omitting the batch path fails.

**Level 3 — Batch key credential** (`gs1DigitalLink: "https://id.gs1.org/01/00810159560115/10/ABC123"`) authorizes data credentials:

```json
"outputValidation": [
  { "type": "JsonSchema", "id": "https://.../base/sample-shipment-data-credential.json" },
  {
    "type": "FieldMatch",
    "sourceField": "credentialSubject.gs1DigitalLink",
    "outputField": {
      "path": "credentialSubject.id",
      "pattern": "^{sourceValue}$"
    }
  }
]
```

The data credential's `credentialSubject.id` must exactly match the batch key credential's Digital Link. A data credential about a different batch fails.

**Why this is transitive**: The key credential base schema requires (via `const`) that every key credential with a `recognizedTo` includes a FieldMatch with pattern `^{sourceValue}` or `^{sourceValue}$`. Because the pattern template is the same for every instance — only the resolved value changes — one base schema rule enforces scope narrowing across all credentials of that type. No link in the chain can omit the constraint.

### Common Patterns

| Pattern | Use case |
|---|---|
| `^{sourceValue}/10/` | Key→key: child must narrow to batch/lot level |
| `^{sourceValue}$` | Key→data: child must exactly match the parent's identifier |
| `^{sourceValue}\d+` | License→GCP: child must extend the prefix with additional digits |
| `^0*{sourceValue}\d+$` | GCP→license: child license value extends GCP with zero-padding |
| `^https://id\\.gs1\\.org/01/{sourceValue}` | License→key: GTIN must appear in canonical Digital Link |

## Transitivity via Base Schema Enforcement

FieldMatch constraints are transitive by construction when base schemas require them. Because the pattern template is fixed per credential type (only the resolved value changes), a base schema can enforce it universally using JSON Schema `const` or `pattern`:

```json
"KeyToKeyDelegationFieldMatch": {
  "properties": {
    "type": { "const": "FieldMatch" },
    "sourceField": { "const": "credentialSubject.gs1DigitalLink" },
    "outputField": {
      "properties": {
        "path": { "const": "credentialSubject.gs1DigitalLink" },
        "pattern": { "pattern": "^\\^\\{sourceValue\\}" }
      },
      "required": ["path", "pattern"]
    }
  },
  "required": ["type", "sourceField", "outputField"]
}
```

The base schema then requires this FieldMatch in every `recognizedTo` action via `contains`. This guarantees that every credential in the chain carries a scope-narrowing constraint forward — no link can omit the constraint and break the chain.

This is impossible with generated schemas: each instance has a unique schema URL, so no base schema rule can universally require "the right generated schema is present."

## Summary

| Concern | FieldMatch | Generated schemas only |
|---|---|---|
| Schema proliferation | One pattern template per credential type | One generated schema per credential instance |
| Transitivity enforcement | Base schema requires pattern template via `const` | Cannot enforce — each instance has a unique URL |
| Dynamic resolution | `{sourceValue}` resolved at validation time | Pattern baked in at generation time |
| Content restriction | Handled by separate data schemas | Same |
| Custom verifier code | None — regex match only | None |

## Work Group Considerations

* This presupposes an AND condition on multiple outputValidations and an OR condition on multiple RecognizedActions.  Is this sufficient for other use cases
* The dot notation in the field names may need consideration for arrays
