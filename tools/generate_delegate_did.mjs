import * as jose from "jose";
import fs from "fs/promises";
import path from "path";

const newDidName = "fake_delegated_did";
const didBase = "did:web:gs1.github.io:GS1DigitalLicenses:dids";
const newDid = `${didBase}:${newDidName}`;

async function main() {
  const { publicKey, privateKey } = await jose.generateKeyPair("ES256");

  const publicJwk = await jose.exportJWK(publicKey);
  const privateJwk = await jose.exportJWK(privateKey);

  const kid = await jose.calculateJwkThumbprint(publicJwk, "sha256");
  const kidStr = await kid;

  publicJwk.kid = kidStr;
  publicJwk.alg = "ES256";

  privateJwk.kid = kidStr;
  privateJwk.alg = "ES256";

  const verificationMethodId = `${newDid}#${kidStr}`;

  const didDocument = {
    "@context": [
      "https://www.w3.org/ns/did/v1",
      "https://w3id.org/security/suites/jws-2020/v1",
      "https://w3id.org/security/jwk/v1",
      "https://www.w3.org/ns/credentials/v2",
    ],
    id: newDid,
    verificationMethod: [
      {
        id: verificationMethodId,
        type: "JsonWebKey",
        controller: newDid,
        publicKeyJwk: publicJwk,
      },
    ],
    authentication: [verificationMethodId],
    assertionMethod: [verificationMethodId],
    capabilityDelegation: [verificationMethodId],
    capabilityInvocation: [verificationMethodId],
  };

  // Output files
  const dir = `../dids/${newDidName}`;
  await fs.mkdir(dir, { recursive: true });

  await fs.writeFile(path.join(dir, "delegated_public_key_jwk.json"), JSON.stringify(publicJwk, null, 2));
  await fs.writeFile(path.join(dir, "delegated_private_key_jwk.json"), JSON.stringify(privateJwk, null, 2));
  await fs.writeFile(path.join(dir, "did.json"), JSON.stringify(didDocument, null, 2));

  console.log(`✅ Keys and DID document saved to ${dir}`);
}

main().catch(console.error);
