# Recognized Entities Sample Credentials

These samples demonstrate the GS1 trust chain using the W3C Recognized Entities 1.0 specification.

## Entities

- **GO** (GS1 Global Office) — `did:web:...fake_go_did` — Trusted root
- **MO** (GS1 Utopia, Member Organization) — `did:web:...fake_mo_did`
- **MC** (Healthy Tots, Member Company) — `did:web:...fake_mc_did`
- **Delegated** (Delegated Data Provider) — `did:web:...fake_delegated_did`

## Trust Chains

### Chain 1: Prefix License -> GCP -> GS1 Key Credential

```
GO (trusted root)
 |
 |  gs1-prefix-license-sample.json
 |  GS1PrefixLicenseCredential, prefix "08"
 |  output: GS1CompanyPrefixLicenseCredentials (008.json)
 v
MO
 |
 |  gcp-sample.json
 |  GS1CompanyPrefixLicenseCredential, GCP "081015955"
 |  output: GS1KeyCredentials (081015955-key-credential.json)
 v
MC (Healthy Tots)
 |
 |  gtin-key-credential-sample.json
 |  GS1KeyCredential, GTIN 00810159550000
 |  subject = MC (self), no delegation
 v
 (end — key assertion only)
```

### Chain 2: Prefix License -> GCP -> GS1 Key Credential with Delegation -> Data Credential

```
GO (trusted root)
 |
 |  gs1-prefix-license-sample.json
 |  GS1PrefixLicenseCredential, prefix "08"
 v
MO
 |
 |  gcp-sample.json
 |  GS1CompanyPrefixLicenseCredential, GCP "081015955"
 v
MC (Healthy Tots)
 |
 |  gtin-key-credential-with-delegation-sample.json
 |  GS1KeyCredential, GTIN 00810159550000
 |  subject = Delegated Data Provider
 |  recognizedTo: issue product data (00810159550000-dimension-and-image-data.json)
 v
Delegated Data Provider
 |
 |  product-data-credential-sample.json
 |  DataCredential, GTIN 00810159550000
 |  product dimensions and image data
 v
 (end — data about the GTIN)
```

### Chain 3: Prefix License -> Self-Held GCP -> ID Key License -> GS1 Key Credential

```
GO (trusted root)
 |
 |  gs1-prefix-license-sample.json
 |  GS1PrefixLicenseCredential, prefix "08"
 v
MO
 |
 |  gcp-mo-sample.json
 |  GS1CompanyPrefixLicenseCredential, GCP "081015956" (self-held)
 |  output: GS1IdentificationKeyLicenseCredentials (081015956-id-key-license.json)
 v
MO (to itself, then issues to MC)
 |
 |  id-key-license-sample.json
 |  GS1IdentificationKeyLicenseCredential, GTIN 00810159560111
 |  output: GS1KeyCredentials (00810159560111-key-credential.json)
 v
MC (Healthy Tots)
 |
 |  gtin-key-credential-chain3-sample.json
 |  GS1KeyCredential, GTIN 00810159560111
 |  subject = MC (self), no delegation
 v
 (end — key assertion only)
```

### Chain 4: GTIN-8 Prefix License -> ID Key License -> GS1 Key Credential

```
GO (trusted root)
 |
 |  gs1-8prefix-license-sample.json
 |  GS18PrefixLicenseCredential, prefix "96"
 |  output: GS1IdentificationKeyLicenseCredentials (096-id-key-license.json)
 v
MO
 |
 |  id8-key-license-sample.json
 |  GS1IdentificationKeyLicenseCredential, GTIN-8 00000009612345
 |  output: GS1KeyCredentials (096-key-credential.json)
 v
MC (Healthy Tots)
 |
 |  gtin8-key-credential-sample.json
 |  GS1KeyCredential, GTIN-8 00000009612345
 |  subject = MC (self), no delegation
 v
 (end — key assertion only)
```
