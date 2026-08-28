# FieldMatch: A Proposed Output Validation Type for W3C Recognized Entities

## Problem

The W3C Recognized Entities 1.0 specification supports delegation chains where a credential's `recognizedTo` action authorizes a subject to issue child credentials, constrained by an `outputValidation` of type `JsonSchema`. However, JSON Schema cannot express **cross-document field constraints** — rules like "the child credential's `gs1DigitalLink` must extend this credential's `gs1DigitalLink`."

This creates three gaps in the GS1 trust chain model:

1. **Scope broadening**: A delegatee can declare an output validation schema that is broader than the scope granted by their parent. Nothing in JSON Schema prevents a party authorized for GTIN `00810159560115` from delegating authority over all GTINs.

2. **Per-instance scoping**: A party authorized to create batch/lot key credentials (arbitrary batch numbers) cannot be restricted to issuing data credentials only about batches they actually created — because the batch number is not known at delegation time.

3. **Schema proliferation**: Every credential in the chain requires a generated output validation schema that combines a base type check with a per-credential pattern match. These generated schemas are boilerplate whose only unique content is a pattern derived from a field in the parent credential.

## Proposal

Introduce `FieldMatch` as a new output validation type alongside `JsonSchema`. A `FieldMatch` rule declares that a specific field in the child credential must match a field in the parent credential.

```json
{
  "type": "FieldMatch",
  "sourceField": "credentialSubject.gs1DigitalLink",
  "outputField": "credentialSubject.gs1DigitalLink",
  "match": "prefix"
}
```

### Fields

| Field | Description |
|---|---|
| `type` | `"FieldMatch"` |
| `sourceField` | JSON path to the field in the current (parent) credential |
| `outputField` | JSON path to the field in the child credential being validated |
| `match` | Match mode: `prefix`, `exact`, or `contains` |

### Match Modes

- **`prefix`**: The child's `outputField` value must start with the parent's `sourceField` value. Used for scope narrowing (e.g., Digital Link path extension).
- **`exact`**: The child's `outputField` value must equal the parent's `sourceField` value. Used for strict scoping (e.g., data credential must reference the exact same identifier).
- **`contains`**: The child's `outputField` value must contain the parent's `sourceField` value as a substring. Used for cross-field relationships (e.g., a GS1 Digital Link URI must contain the licensed company prefix).

### Evaluation

FieldMatch rules participate in the existing output validation semantics:

- **Within a `recognizedTo` action**: All output validations must pass (AND). A `JsonSchema` validates the credential's type and structure; a `FieldMatch` constrains its scope.
- **Across `recognizedTo` actions**: At least one action must fully pass (OR). This allows a single credential to authorize issuance of different credential types under separate actions.

## Examples

### License to GCP (prefix match on licenseValue)

A prefix license with `licenseValue: "08"` authorizes GCPs whose license value starts with "08":

```json
"recognizedTo": {
  "type": "RecognizedAction",
  "action": "issue",
  "outputValidation": [
    {
      "type": "JsonSchema",
      "id": "https://.../base/gs1-company-prefix-license-credential.json"
    },
    {
      "type": "FieldMatch",
      "sourceField": "credentialSubject.licenseValue",
      "outputField": "credentialSubject.licenseValue",
      "match": "prefix"
    }
  ]
}
```

**Replaces**: generated schema `008.json`.

### GCP to Key Credential (contains match across field types)

A GCP with `licenseValue: "081015955"` authorizes key credentials whose Digital Link contains the company prefix:

```json
"recognizedTo": {
  "type": "RecognizedAction",
  "action": "issue",
  "outputValidation": [
    {
      "type": "JsonSchema",
      "id": "https://.../base/gs1-key-credential.json"
    },
    {
      "type": "FieldMatch",
      "sourceField": "credentialSubject.licenseValue",
      "outputField": "credentialSubject.gs1DigitalLink",
      "match": "contains"
    }
  ]
}
```

**Replaces**: generated schema `081015955-key-credential.json`.

### Key Credential to Batch Key Credential (prefix match for scope narrowing)

A key credential with `gs1DigitalLink: "https://id.gs1.org/01/00810159560115"` authorizes batch/lot key credentials that extend the Digital Link:

```json
"recognizedTo": {
  "type": "RecognizedAction",
  "action": "issue",
  "outputValidation": [
    {
      "type": "JsonSchema",
      "id": "https://.../base/gs1-key-credential.json"
    },
    {
      "type": "FieldMatch",
      "sourceField": "credentialSubject.gs1DigitalLink",
      "outputField": "credentialSubject.gs1DigitalLink",
      "match": "prefix"
    }
  ]
}
```

**Replaces**: generated schema `00810159560115-batch-key-credential.json`.

### Batch Key Credential to Data Credential (prefix match for per-batch scoping)

A batch key credential with `gs1DigitalLink: "https://id.gs1.org/01/00810159560115/10/ABC123"` authorizes data credentials only about that specific batch:

```json
"recognizedTo": [
  {
    "type": "RecognizedAction",
    "action": "issue",
    "outputValidation": [
      {
        "type": "JsonSchema",
        "id": "https://.../generated/batch-shipping-data.json",
        "name": "Batch Shipping Data"
      },
      {
        "type": "FieldMatch",
        "sourceField": "credentialSubject.gs1DigitalLink",
        "outputField": "credentialSubject.id",
        "match": "prefix"
      }
    ]
  }
]
```

This solves the per-instance scoping problem: the delegated party can only issue data credentials for the specific batch/lot they hold a key credential for. The data content schema (`batch-shipping-data.json`) constrains which fields are allowed (e.g., `shipDate`, `shipmentWeight`).

## Impact on Generated Schemas

With FieldMatch, most generated output validation schemas become unnecessary. The credential itself carries the scope rule declaratively.

| Current generated schema | FieldMatch replacement |
|---|---|
| `008.json` | `prefix` on `licenseValue` → `licenseValue` |
| `081015955-key-credential.json` | `contains` on `licenseValue` → `gs1DigitalLink` |
| `081015956-id-key-license.json` | `prefix` on `licenseValue` → `licenseValue` |
| `096-id-key-license.json` | `prefix` on `licenseValue` → `licenseValue` |
| `096-key-credential.json` | `contains` on `licenseValue` → `gs1DigitalLink` |
| `00810159560115-key-credential.json` | `contains` on `licenseValue` → `gs1DigitalLink` |
| `00810159560115-batch-key-credential.json` | `prefix` on `gs1DigitalLink` → `gs1DigitalLink` |
| `00810159560115-data-credential.json` | `prefix` on `gs1DigitalLink` → `id` |

**Retained**: Data content schemas (e.g., `00810159550000-dimension-and-image-data.json`) that constrain which data fields are allowed. These validate content, not scope, and cannot be replaced by FieldMatch.

## Security Properties

- **Scope narrowing is enforced**: Each level's FieldMatch constrains the child's field value relative to the parent's. A child cannot broaden scope because the parent's field value is fixed at issuance time.
- **No custom verifier code**: FieldMatch is declarative. The verifier reads two field values, applies a string comparison. No JSON Schema extensions, no regex containment checks.
- **Transitive by construction**: If every key credential's `recognizedTo` includes a `prefix` FieldMatch on `gs1DigitalLink`, scope narrows at every hop automatically.
- **Digest-independent**: Unlike the scope schema approach, FieldMatch rules don't reference external schema URIs that need digest pinning. The rule is inline in the credential.

## Open Questions

1. **Array-valued credentialSubject**: When `credentialSubject` is an array, should the FieldMatch apply to all items or at least one?
2. **Nested field paths**: Should `sourceField`/`outputField` support array indexing, or only simple dot-delimited paths?
3. **Spec scope**: Should FieldMatch be proposed as an RE spec extension or as a GS1-specific output validation type?
