import crypto from 'crypto';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const templatesDir = path.join(__dirname, '../templates');

// Multibase base64url-nopad prefix
const MULTIBASE_BASE64URL_NOPAD = 'u';

// Multihash prefix for SHA-256 (0x12) and length (0x20 = 32 bytes)
const MULTIHASH_SHA256_PREFIX = Buffer.from([0x12, 0x20]);

function computeDigestMultibase(filePath) {
  const content = fs.readFileSync(filePath, 'utf-8');
  const hash = crypto.createHash('sha256').update(content).digest();
  
  // Concatenate multihash prefix with the hash
  const multihash = Buffer.concat([MULTIHASH_SHA256_PREFIX, hash]);
  
  // Encode with multibase 'u' (base64url-nopad)
  const base64url = multihash.toString('base64')
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=/g, '');
  
  return MULTIBASE_BASE64URL_NOPAD + base64url;
}

const templates = [
  'gs1-sample-license-template.svg',
  'gs1-sample-key-template.svg',
  'gs1-sample-product-data-template.svg'
];

console.log('Computing digestMultibase for templates:\n');

const digests = {};
templates.forEach(template => {
  const templatePath = path.join(templatesDir, template);
  const digest = computeDigestMultibase(templatePath);
  digests[template] = digest;
  console.log(`${template}:`);
  console.log(`  ${digest}\n`);
});

// Output as JSON for easy reference
console.log('\nJSON format:');
console.log(JSON.stringify(digests, null, 2));

