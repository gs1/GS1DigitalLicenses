# Recognized Entities Sample Credentials (JavaScript Variant)

These samples demonstrate the GS1 trust chain using the W3C Recognized Entities 1.0 specification. Cross-document checks use the JavaScript credential validator.

## Legacy chain link

A credential that has a parent carries the legacy GS1 chain property on `credentialSubject`, set to the same URL as `issuer.recognizedIn.id`.

- Licenses and key credentials use `extendsCredential`.
- Data credentials use `keyAuthorization`.

One issued credential can be followed by either a recognized-entities verifier (`recognizedIn`) or a legacy verifier (`extendsCredential` or `keyAuthorization`). Prefix licenses are the trust root and have no parent link.
