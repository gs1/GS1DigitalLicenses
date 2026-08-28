# FieldMatch: A Proposed Output Validation Type for W3C Recognized Entities

## Problem

The W3C Recognized Entities 1.0 specification supports delegation chains where a credential's `recognizedTo` action authorizes a subject to issue child credentials, constrained by an `outputValidation` of type `JsonSchema`. However, JSON Schema cannot express **cross-document field constraints** — rules like "the child credential's `gs1DigitalLink` must extend this credential's `gs1DigitalLink`."

This creates three gaps in the GS1 trust chain model:

1. **Scope broadening**: A delegatee can declare an output validation schema that is broader than the scope granted by their parent. Nothing in JSON Schema prevents a party authorized for GTIN `00810159560115` from delegating authority over all GTINs.

2. **Per-instance scoping**: A party authorized to create batch/lot key credentials (arbitrary batch numbers) cannot be restricted to issuing data credentials only about batches they actually created — because the batch number is not known at delegation time.

3. **Schema proliferation**: Every credential in the chain requires a generated output validation schema that combines a base type check with a per-credential pattern match. These generated schemas are boilerplate whose only unique content is a pattern derived from a field in the parent credential.

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
| `outputField` | Object with `path` and `pattern` describing the constraint on the child credential |
| `outputField.path` | Dot-delimited path to the field in the child credential being validated |
| `outputField.pattern` | Regex pattern with `{sourceValue}` placeholder |

### Pattern Evaluation

At validation time, the verifier:

1. Resolves `sourceField` to a value in the parent credential
2. Replaces `{sourceValue}` in `outputField.pattern` with the regex-escaped source value
3. Matches the resulting regex against the value at `outputField.path` in the child credential

The `{sourceValue}` placeholder is always resolved dynamically from the live parent credential, never baked in at issuance time. This is what makes FieldMatch work for transitive delegation — the pattern template is fixed, but the value it constrains against is determined by whatever credential carries it.

### Common Patterns

| Pattern | Equivalent | Use case |
|---|---|---|
| `^{sourceValue}` | prefix | Child value starts with parent value (key→key scope narrowing) |
| `^{sourceValue}$` | exact | Child value equals parent value exactly (key→data binding) |
| `^{sourceValue}\d+` | prefix + digits | Child value extends parent value with additional digits (license→GCP) |
| `^0*{sourceValue}\d+$` | zero-padded prefix + digits | Child license value contains parent prefix with zero-padding (GCP→ID key license) |
| `^https://id\\.gs1\\.org/01/{sourceValue}` | AI-specific URL | Parent license value appears in a GTIN Digital Link URL |

### Evaluation Semantics

FieldMatch rules participate in the existing output validation semantics:

- **Within a `recognizedTo` action**: All output validations must pass (AND). A `JsonSchema` validates the credential's type and structure; a `FieldMatch` constrains its scope.
- **Across `recognizedTo` actions**: At least one action must fully pass (OR). This allows a single credential to authorize issuance of different credential types under separate actions.

## Examples

### License to GCP (prefix match on licenseValue)

A prefix license with `licenseValue: "08"` authorizes GCPs whose license value starts with "08":

```json
"recognizedTo": {
  "type": "RecognizedAction",
  "name": "GS1 Company Prefix Licenses",
  "action": "issue",
  "outputValidation": [
    {
      "type": "JsonSchema",
      "id": "https://.../base/gs1-company-prefix-license-credential.json"
    },
    {
      "type": "FieldMatch",
      "sourceField": "credentialSubject.licenseValue",
      "outputField": {
        "path": "credentialSubject.licenseValue",
        "pattern": "^{sourceValue}\\d+"
      }
    }
  ]
}
```

### GCP to Key Credential (license value in GTIN Digital Link)

A GCP with `licenseValue: "081015955"` authorizes key credentials whose Digital Link contains the company prefix under a GTIN AI. The pattern includes zero-padding to handle the 14-digit GTIN format:

```json
"recognizedTo": {
  "type": "RecognizedAction",
  "name": "GS1 Key Credentials",
  "action": "issue",
  "outputValidation": [
    {
      "type": "JsonSchema",
      "id": "https://.../base/gs1-key-credential.json"
    },
    {
      "type": "FieldMatch",
      "sourceField": "credentialSubject.licenseValue",
      "outputField": {
        "path": "credentialSubject.gs1DigitalLink",
        "pattern": "^https://id\\.gs1\\.org/(01|8006|8013|8010|414|417|8017|8018|255|00|253|401|402|8003|8004)/0*{sourceValue}"
      }
    }
  ]
}
```

The pattern `^https://id\.gs1\.org/(01|...)/0*081015955` matches `https://id.gs1.org/01/00810159550000` because the GTIN contains the zero-padded company prefix under an AI.

### GCP-MO with Multiple Actions (key credentials and ID key licenses)

A Member Organization GCP can authorize both key credential issuance and ID key license issuance using separate `recognizedTo` actions:

```json
"recognizedTo": [
  {
    "type": "RecognizedAction",
    "name": "GS1 Key Credentials",
    "action": "issue",
    "outputValidation": [
      {
        "type": "JsonSchema",
        "id": "https://.../base/gs1-key-credential.json"
      },
      {
        "type": "FieldMatch",
        "sourceField": "credentialSubject.licenseValue",
        "outputField": {
          "path": "credentialSubject.gs1DigitalLink",
          "pattern": "^https://id\\.gs1\\.org/(01|8006|8013|8010|414|417|8017|8018|255|00|253|401|402|8003|8004)/0*{sourceValue}"
        }
      }
    ]
  },
  {
    "type": "RecognizedAction",
    "name": "GS1 ID Key Licenses",
    "action": "issue",
    "outputValidation": [
      {
        "type": "JsonSchema",
        "id": "https://.../base/gs1-identification-key-license-credential.json"
      },
      {
        "type": "FieldMatch",
        "sourceField": "credentialSubject.licenseValue",
        "outputField": {
          "path": "credentialSubject.licenseValue",
          "pattern": "^0*{sourceValue}\\d+$"
        }
      }
    ]
  }
]
```

A child credential passes if it fully satisfies all validations in at least one action (OR across actions, AND within).

### ID Key License to Key Credential (GTIN-specific AI)

An ID key license with `licenseValue: "00810159560115"` and `identificationKeyType: "GTIN"` authorizes key credentials whose Digital Link uses the GTIN AI (`01`):

```json
"recognizedTo": {
  "type": "RecognizedAction",
  "name": "GS1 Key Credentials",
  "action": "issue",
  "outputValidation": [
    {
      "type": "JsonSchema",
      "id": "https://.../base/gs1-key-credential.json"
    },
    {
      "type": "FieldMatch",
      "sourceField": "credentialSubject.licenseValue",
      "outputField": {
        "path": "credentialSubject.gs1DigitalLink",
        "pattern": "^https://id\\.gs1\\.org/01/{sourceValue}"
      }
    }
  ]
}
```

Unlike the GCP pattern which allows any AI, the ID key license pattern is specific to the key's `identificationKeyType`. A GTIN license only authorizes Digital Links under AI `01`.

### Key Credential to Key Credential (prefix for scope narrowing)

A key credential with `gs1DigitalLink: "https://id.gs1.org/01/00810159560115"` authorizes batch/lot key credentials that extend the Digital Link:

```json
"recognizedTo": {
  "type": "RecognizedAction",
  "name": "GS1 Batch/Lot Key Credentials",
  "action": "issue",
  "outputValidation": [
    {
      "type": "JsonSchema",
      "id": "https://.../base/gs1-key-credential.json"
    },
    {
      "type": "FieldMatch",
      "sourceField": "credentialSubject.gs1DigitalLink",
      "outputField": {
        "path": "credentialSubject.gs1DigitalLink",
        "pattern": "^{sourceValue}"
      }
    }
  ]
}
```

The pattern `^https://id\.gs1\.org/01/00810159560115` matches `https://id.gs1.org/01/00810159560115/10/ABC123` because the batch Digital Link extends the GTIN Digital Link with a batch/lot AI.

### Key Credential to Data Credential (exact match binding)

A key credential with `gs1DigitalLink: "https://id.gs1.org/01/00810159550000"` authorizes data credentials whose `credentialSubject.id` exactly matches the Digital Link:

```json
"recognizedTo": {
  "type": "RecognizedAction",
  "name": "Product Data Credentials",
  "action": "issue",
  "outputValidation": [
    {
      "type": "JsonSchema",
      "id": "https://.../generated/00810159550000-dimension-and-image-data.json",
      "name": "Product Dimensions Data"
    },
    {
      "type": "FieldMatch",
      "sourceField": "credentialSubject.gs1DigitalLink",
      "outputField": {
        "path": "credentialSubject.id",
        "pattern": "^{sourceValue}$"
      }
    }
  ]
}
```

The `$` anchor enforces an exact match — the data credential must be about the specific product identified by the key credential, not a sub-path of it. The generated schema constrains which data fields are allowed (e.g., dimensions, images).

### Batch Key Credential to Data Credential (exact match + content constraint)

A batch key credential with `gs1DigitalLink: "https://id.gs1.org/01/00810159560115/10/ABC123"` authorizes data credentials only about that specific batch, with constrained data fields:

```json
"recognizedTo": {
  "type": "RecognizedAction",
  "name": "Batch Shipment Data Credentials",
  "action": "issue",
  "outputValidation": [
    {
      "type": "JsonSchema",
      "id": "https://.../generated/00810159560115-shipment-data.json",
      "name": "Batch Shipment Data"
    },
    {
      "type": "FieldMatch",
      "sourceField": "credentialSubject.gs1DigitalLink",
      "outputField": {
        "path": "credentialSubject.id",
        "pattern": "^{sourceValue}$"
      }
    }
  ]
}
```

This solves the per-instance scoping problem: the exact-match FieldMatch ensures the delegated party can only issue data credentials for the specific batch they hold a key credential for. The generated schema (with `additionalProperties: false`) constrains which data fields are allowed — a party authorized to assert shipment data cannot sneak in pricing data.

The batch number `ABC123` is not known at the time the GTIN key credential is issued — it's resolved dynamically from the batch key credential at validation time.

## Transitivity via Base Schema Enforcement

FieldMatch constraints are transitive by construction if every credential in the chain carries one. To enforce this, GS1 base schemas require that credentials include a specific FieldMatch in their `recognizedTo.outputValidation` using the JSON Schema `contains` keyword.

### Company Prefix License Base Schema

Requires that any `recognizedTo` action includes a FieldMatch linking the parent's `licenseValue` to the child's Digital Link:

```json
"$defs": {
  "GCPDigitalLinkFieldMatch": {
    "properties": {
      "type": { "const": "FieldMatch" },
      "sourceField": { "const": "credentialSubject.licenseValue" },
      "outputField": {
        "properties": {
          "path": { "const": "credentialSubject.gs1DigitalLink" }
        },
        "required": ["path", "pattern"]
      }
    },
    "required": ["type", "sourceField", "outputField"]
  }
}
```

The `recognizedTo` constraint handles both single-action (object) and multi-action (array) forms:

```json
"recognizedTo": {
  "oneOf": [
    {
      "type": "object",
      "properties": {
        "outputValidation": {
          "contains": { "$ref": "#/$defs/GCPDigitalLinkFieldMatch" }
        }
      }
    },
    {
      "type": "array",
      "contains": {
        "properties": {
          "outputValidation": {
            "contains": { "$ref": "#/$defs/GCPDigitalLinkFieldMatch" }
          }
        }
      }
    }
  ]
}
```

### Key Credential Base Schema

Defines two FieldMatch patterns for key credential delegation — one for key→key (prefix match on Digital Link) and one for key→data (exact match on `credentialSubject.id`):

```json
"$defs": {
  "KeyToKeyDelegationFieldMatch": {
    "description": "For key→key delegation: child's gs1DigitalLink must start with parent's",
    "properties": {
      "type": { "const": "FieldMatch" },
      "sourceField": { "const": "credentialSubject.gs1DigitalLink" },
      "outputField": {
        "properties": {
          "path": { "const": "credentialSubject.gs1DigitalLink" },
          "pattern": { "const": "^{sourceValue}" }
        },
        "required": ["path", "pattern"]
      }
    },
    "required": ["type", "sourceField", "outputField"]
  },
  "KeyToDataDelegationFieldMatch": {
    "description": "For key→data delegation: data credential's credentialSubject.id must exactly match the key's Digital Link",
    "properties": {
      "type": { "const": "FieldMatch" },
      "sourceField": { "const": "credentialSubject.gs1DigitalLink" },
      "outputField": {
        "properties": {
          "path": { "const": "credentialSubject.id" },
          "pattern": { "const": "^{sourceValue}$" }
        },
        "required": ["path", "pattern"]
      }
    },
    "required": ["type", "sourceField", "outputField"]
  }
}
```

The `recognizedTo` constraint requires each action to contain one of these:

```json
"recognizedTo": {
  "oneOf": [
    {
      "type": "object",
      "properties": {
        "outputValidation": {
          "contains": {
            "oneOf": [
              { "$ref": "#/$defs/KeyToKeyDelegationFieldMatch" },
              { "$ref": "#/$defs/KeyToDataDelegationFieldMatch" }
            ]
          }
        }
      }
    },
    {
      "type": "array",
      "contains": {
        "properties": {
          "outputValidation": {
            "contains": {
              "oneOf": [
                { "$ref": "#/$defs/KeyToKeyDelegationFieldMatch" },
                { "$ref": "#/$defs/KeyToDataDelegationFieldMatch" }
              ]
            }
          }
        }
      }
    }
  ]
}
```

This means a key credential that delegates without including the required FieldMatch will fail its own base schema validation. The pattern template is prescribed by the credential type — each level knows the shape of the relationship to its children — while the actual source value is resolved at validation time from the live credential.

No new spec mechanism is needed for transitivity. The existing JsonSchema `contains` keyword enforces that every credential carries FieldMatch forward.

## Impact on Generated Schemas

With FieldMatch, most generated output validation schemas become unnecessary. The credential itself carries the scope rule declaratively.

**Eliminated** — these are fully replaced by FieldMatch:

| Former generated schema | FieldMatch replacement |
|---|---|
| `008.json` | `^{sourceValue}\d+` on `licenseValue` → `licenseValue` |
| `081015955-key-credential.json` | `^https://id\\.gs1\\.org/(01|...)/0*{sourceValue}` on `licenseValue` → `gs1DigitalLink` |
| `081015956-id-key-license.json` | `^0*{sourceValue}\d+$` on `licenseValue` → `licenseValue` |
| `096-id-key-license.json` | `^0*{sourceValue}\d+$` on `licenseValue` → `licenseValue` |
| `096-key-credential.json` | `^https://id\\.gs1\\.org/01/{sourceValue}` on `licenseValue` → `gs1DigitalLink` |
| `00810159560115-key-credential.json` | `^https://id\\.gs1\\.org/01/{sourceValue}` on `licenseValue` → `gs1DigitalLink` |
| `00810159560115-batch-key-credential.json` | `^{sourceValue}` on `gs1DigitalLink` → `gs1DigitalLink` |

**Retained** — data content schemas that constrain which fields are allowed:

| Generated schema | Purpose |
|---|---|
| `00810159550000-dimension-and-image-data.json` | Constrains product data fields (dimensions, image) |
| `00810159560115-shipment-data.json` | Constrains shipment data fields (shipDate, shipmentWeight) with `additionalProperties: false` |

These validate content, not scope, and cannot be replaced by FieldMatch. The exact-match FieldMatch (`^{sourceValue}$`) works alongside these schemas: the generated schema says what data is allowed, the FieldMatch says which product/batch it's about.

## Security Properties

- **Scope narrowing is enforced**: Each level's FieldMatch constrains the child's field value relative to the parent's. A child cannot broaden scope because the parent's field value is fixed at issuance time.
- **Exact-match binding for data credentials**: The `^{sourceValue}$` pattern ensures a data credential is bound to the exact key credential that authorized it. A party with a batch key credential for ABC123 cannot assert data about batch XYZ789.
- **Content restriction via generated schemas**: Even with exact-match binding, a delegated party is constrained to the data fields specified in the generated schema. A party authorized for shipment data cannot include pricing data (`additionalProperties: false`).
- **Dynamic resolution**: The `{sourceValue}` placeholder is resolved at validation time from the live credential, not baked in at issuance. This means the same pattern template works for any value — a batch number, a GTIN, a company prefix — without knowing it in advance.
- **Transitive by construction**: Base schemas require specific FieldMatch patterns in `recognizedTo.outputValidation`, so every credential that delegates must carry scope narrowing forward. No additional spec mechanism is needed.
- **No custom verifier code**: FieldMatch is declarative. The verifier extracts two field values, substitutes one into a regex, and matches. No JSON Schema extensions required.
- **Digest-independent**: FieldMatch rules are inline in the credential. They don't reference external schema URIs that need digest pinning.

## Open Questions

1. **Array-valued credentialSubject**: When `credentialSubject` is an array, should the FieldMatch apply to all items or at least one?
2. **Nested field paths**: Should `sourceField` and `outputField.path` support array indexing, or only simple dot-delimited paths?
3. **Spec scope**: Should FieldMatch be proposed as an RE spec extension or as a GS1-specific output validation type?
4. **Regex safety**: Should the spec constrain which regex features are allowed in `pattern` to prevent ReDoS or overly complex patterns?
