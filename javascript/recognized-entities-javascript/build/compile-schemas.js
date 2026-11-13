/**
 * Compiles GS1 base JSON Schemas into standalone JavaScript validation
 * functions using AJV's standalone code generation.
 *
 * Usage: node compile-schemas.js
 * Output: ../compiled-schemas.js (ES module with named exports)
 */

const Ajv2020 = require('ajv/dist/2020');
const addFormats = require('ajv-formats');
const standaloneCode = require('ajv/dist/standalone');
const fs = require('fs');
const path = require('path');

const SCHEMA_DIR = path.resolve(
  __dirname,
  '../../../schemas/recognized-entities-javascript/base'
);
const OUTPUT_FILE = path.resolve(__dirname, '../compiled-schemas.cjs');

// The W3C VCDM base schema — a minimal stub that AJV can resolve refs
// against. We only need the structure to be valid; the real VCDM validation
// happens at the VC layer before the RE validator runs.
const VCDM_STUB = {
  $id: 'https://www.w3.org/2022/credentials/v2/verifiable-credential-schema.json',
  $schema: 'https://json-schema.org/draft/2020-12/schema',
  title: 'VerifiableCredential (stub)',
  type: 'object'
};

// Load all base schemas from the directory
function loadSchemas() {
  const schemas = [];
  for(const file of fs.readdirSync(SCHEMA_DIR)) {
    if(!file.endsWith('.json')) continue;
    const content = fs.readFileSync(path.join(SCHEMA_DIR, file), 'utf-8');
    const schema = JSON.parse(content);
    // AJV needs $id as an absolute URI for $ref resolution between schemas.
    // Our schemas use short $id values; map them to file-based URIs.
    if(schema.$id && !schema.$id.startsWith('http')) {
      schema.$id = `file:///${schema.$id}`;
    }
    schemas.push({file, schema});
  }
  return schemas;
}

// Fix $ref values to use the same file:/// prefix
function fixRefs(obj) {
  if(obj === null || typeof obj !== 'object') return;
  if(Array.isArray(obj)) {
    obj.forEach(fixRefs);
    return;
  }
  for(const [key, value] of Object.entries(obj)) {
    if(key === '$ref' && typeof value === 'string') {
      if(value.startsWith('https://www.w3.org/')) {
        // leave VCDM ref as-is
      } else if(!value.startsWith('file:///') && !value.startsWith('#')) {
        // Convert relative refs like "gs1-common.json#/$defs/Org"
        // to "file:///gs1-common#/$defs/Org"
        const [file, fragment] = value.split('#');
        const base = file.replace(/\.json$/, '');
        obj[key] = `file:///${base}${fragment ? '#' + fragment : ''}`;
      }
    } else {
      fixRefs(value);
    }
  }
}

function main() {
  const allSchemas = loadSchemas();

  // Fix all $ref values
  for(const {schema} of allSchemas) {
    fixRefs(schema);
  }

  const ajv = new Ajv2020({
    code: {source: true, esm: false, optimize: true},
    allErrors: true,
    strict: false,
    formats: {
      // Inline URI format check — keeps compiled output self-contained
      uri: /^[a-zA-Z][a-zA-Z0-9+\-.]*:[^\s]*$/,
      'date-time': /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$/
    },
    schemas: [VCDM_STUB]
  });

  // Add all schemas to AJV
  for(const {file, schema} of allSchemas) {
    try {
      ajv.addSchema(schema);
    } catch(e) {
      console.error(`Error adding schema ${file}: ${e.message}`);
      process.exit(1);
    }
  }

  // Compile the five credential-type schemas we need as validators
  const targets = {
    validatePrefixLicense: 'file:///gs1-prefix-license-credential',
    validate8PrefixLicense: 'file:///gs1-8prefix-license-credential',
    validateCompanyPrefixLicense: 'file:///gs1-company-prefix-license-credential',
    validateIdKeyLicense: 'file:///gs1-identification-key-license-credential',
    validateKeyCredential: 'file:///gs1-key-credential',
    validateDataCredential: 'file:///gs1-data-credential',
  };

  // Validate that all targets compile
  for(const [name, id] of Object.entries(targets)) {
    const validate = ajv.getSchema(id);
    if(!validate) {
      console.error(`Schema not found: ${id} (for ${name})`);
      process.exit(1);
    }
    console.log(`✓ Compiled: ${name} → ${id}`);
  }

  // Generate standalone code
  const code = standaloneCode(ajv, targets);

  fs.writeFileSync(OUTPUT_FILE, code, 'utf-8');
  console.log(`\nStandalone validation code written to: ${OUTPUT_FILE}`);
  console.log(`Size: ${(code.length / 1024).toFixed(1)} KB`);
}

main();
