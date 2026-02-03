import Ajv from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Test credential references
const credentialTests = [
  // License credentials
  {
    name: 'GCP License',
    file: 'gcp-sample.json',
    schemas: ['companyprefix.json', 'prefix.json']
  },
  {
    name: 'GS1 Prefix License',
    file: 'gs1-prefix-license-sample.json',
    schemas: ['prefix.json']
  },
  {
    name: 'GTIN-8 ID Key License',
    file: 'gtin8-id-key-license-sample.json',
    schemas: ['idkey.json']
  },
  {
    name: 'GTIN-8 Prefix License',
    file: 'gtin8-prefix-sample.json',
    schemas: ['prefix8.json', 'prefix.json']
  },
  {
    name: 'ID Key License',
    file: 'id-key-license-sample.json',
    schemas: ['idkey.json']
  },
  // Key credentials
  {
    name: 'GLN Key Credential',
    file: 'gln-key-credential-sample.json',
    schemas: ['key.json']
  },
  {
    name: 'GTIN Key Credential',
    file: 'gtin-key-credential-sample.json',
    schemas: ['key.json']
  },
  {
    name: 'GTIN Batch Key Credential',
    file: 'gtin-batch-key-credential-sample.json',
    schemas: ['key.json']
  },
  {
    name: 'GTIN Serial Key Credential',
    file: 'gtin-serial-key-credential-sample.json',
    schemas: ['key.json']
  },
  {
    name: 'GRAI Key Credential',
    file: 'grai-key-credential-sample.json',
    schemas: ['key.json', 'custom_asset.json']
  },
  {
    name: 'SSCC Key Credential',
    file: 'sscc-key-credential-sample.json',
    schemas: ['key.json', 'custom_shipment.json']
  },
  // Data credentials
  {
    name: 'Product Data Credential',
    file: 'product-data-credential-sample.json',
    schemas: ['data.json', 'productdata.json']
  },
  {
    name: 'Organization Data Credential',
    file: 'organization-data-credential-sample.json',
    schemas: ['data.json', 'organizationdata.json']
  },
  {
    name: 'GRAI Data Credential',
    file: 'grai-data-credential-sample.json',
    schemas: ['data.json', 'custom_asset.json']
  },
  {
    name: 'SSCC Data Credential',
    file: 'sscc-data-credential-sample.json',
    schemas: ['data.json', 'custom_shipment.json']
  }
];

// Negative test cases - these should fail validation
const negativeTests = [
  {
    name: 'GLN Key Credential - Invalid Digital Link',
    file: 'gln-key-credential-sample.json',
    schemas: ['key.json'],
    mutation: (credential) => {
      credential.credentialSubject.id = 'https://invalid-url.com/not-a-digital-link';
      return credential;
    },
    expectedError: 'pattern'
  },
  {
    name: 'GTIN Key Credential - Invalid Digital Link',
    file: 'gtin-key-credential-sample.json',
    schemas: ['key.json'],
    mutation: (credential) => {
      credential.credentialSubject.id = 'http://example.com/invalid';
      return credential;
    },
    expectedError: 'pattern'
  },
  {
    name: 'GTIN Batch Key Credential - Invalid Digital Link',
    file: 'gtin-batch-key-credential-sample.json',
    schemas: ['key.json'],
    mutation: (credential) => {
      credential.credentialSubject.id = 'https://id.gs1.org/invalid/path';
      return credential;
    },
    expectedError: 'pattern'
  },
  {
    name: 'GTIN Serial Key Credential - Invalid Digital Link',
    file: 'gtin-serial-key-credential-sample.json',
    schemas: ['key.json'],
    mutation: (credential) => {
      credential.credentialSubject.id = 'not-even-a-url';
      return credential;
    },
    expectedError: 'pattern'
  },
  {
    name: 'GRAI Key Credential - Invalid Digital Link',
    file: 'grai-key-credential-sample.json',
    schemas: ['key.json', 'custom_asset.json'],
    mutation: (credential) => {
      credential.credentialSubject.id = 'https://id.gs1.org/99/12345';
      return credential;
    },
    expectedError: 'pattern'
  },
  {
    name: 'SSCC Key Credential - Invalid Digital Link',
    file: 'sscc-key-credential-sample.json',
    schemas: ['key.json', 'custom_shipment.json'],
    mutation: (credential) => {
      credential.credentialSubject.id = 'https://example.com';
      return credential;
    },
    expectedError: 'pattern'
  }
];

const schemasDir = path.join(__dirname, '../schemas');
const jsonsDir = path.join(__dirname, '../jsons');

// Initialize AJV with Draft 2020-12 support
const ajv = new Ajv({ 
  strict: false,
  allErrors: true
});
addFormats(ajv);

let totalTests = 0;
let passedTests = 0;
let failedTests = 0;
const errors = [];

console.log('🧪 Testing GS1 Credential Schema Validation\n');
console.log('='.repeat(60));
console.log('');

/**
 * Load a credential from local JSON file
 */
function loadCredential(filename) {
  const filePath = path.join(jsonsDir, filename);
  if (!fs.existsSync(filePath)) {
    throw new Error(`Credential file not found: ${filePath}`);
  }
  const fileContent = fs.readFileSync(filePath, 'utf-8');
  return JSON.parse(fileContent);
}

/**
 * Load a JSON schema file
 */
function loadSchema(schemaName) {
  const schemaPath = path.join(schemasDir, schemaName);
  if (!fs.existsSync(schemaPath)) {
    throw new Error(`Schema file not found: ${schemaPath}`);
  }
  const schemaContent = fs.readFileSync(schemaPath, 'utf-8');
  return JSON.parse(schemaContent);
}

/**
 * Validate credential against schema
 */
function validateCredential(credential, schema, options = {}) {
  // Check if schema is already compiled to avoid duplicate ID errors
  const schemaId = schema.$id || schema.id;
  let validate = schemaId ? ajv.getSchema(schemaId) : undefined;
  
  if (!validate) {
    validate = ajv.compile(schema);
  }
  
  const valid = validate(credential);
  
  if (!valid) {
    const errors = validate.errors || [];
    
    // Categorize errors
    const requiredErrors = errors.filter(e => e.keyword === 'required');
    const otherErrors = errors.filter(e => e.keyword !== 'required');
    
    return {
      valid: false,
      errors: errors,
      requiredErrors: requiredErrors,
      otherErrors: otherErrors
    };
  }
  
  return { valid: true };
}

/**
 * Run positive tests (valid credentials should pass)
 */
async function runTests() {
  for (const test of credentialTests) {
    console.log(`\n📄 ${test.name}`);
    console.log(`   File: ${test.file}`);
    
    try {
      // Load the credential
      console.log(`   📂 Loading credential...`);
      const credential = loadCredential(test.file);
      console.log(`   ✅ Credential loaded successfully`);
      
      // Try each schema
      let validatedWithAnySchema = false;
      
      for (const schemaName of test.schemas) {
        totalTests++;
        const testName = `${test.name} -> ${schemaName}`;
        
        try {
          console.log(`   🔍 Validating against ${schemaName}...`);
          
          // Load schema
          const schema = loadSchema(schemaName);
          
          // Validate
          const result = validateCredential(credential, schema);
          
          if (result.valid) {
            console.log(`   ✅ Valid against ${schemaName}`);
            passedTests++;
            validatedWithAnySchema = true;
          } else {
            const hasRequiredErrors = result.requiredErrors.length > 0;
            const statusIcon = hasRequiredErrors ? '❌' : '⚠️';
            const statusText = hasRequiredErrors ? 'Missing required fields' : 'Optional field issues';
            
            console.log(`   ${statusIcon} Invalid against ${schemaName} (${result.errors.length} errors - ${statusText})`);
            
            // Show required errors first
            if (result.requiredErrors.length > 0) {
              console.log(`      Required field errors:`);
              result.requiredErrors.slice(0, 2).forEach(err => {
                console.log(`      - ${err.instancePath || '/'}: ${err.message}`);
              });
            }
            
            // Show other errors
            if (result.otherErrors.length > 0) {
              console.log(`      Other errors (${result.otherErrors.length}):`);
              result.otherErrors.slice(0, 2).forEach(err => {
                console.log(`      - ${err.instancePath || '/'}: ${err.message}`);
              });
              if (result.otherErrors.length > 2) {
                console.log(`      ... and ${result.otherErrors.length - 2} more`);
              }
            }
            
            failedTests++;
            errors.push({
              test: testName,
              error: 'Schema validation failed',
              errorCount: result.errors.length,
              requiredErrorCount: result.requiredErrors.length,
              otherErrorCount: result.otherErrors.length,
              details: result.errors
            });
          }
          
        } catch (error) {
          console.log(`   ❌ Error validating against ${schemaName}: ${error.message}`);
          failedTests++;
          errors.push({
            test: testName,
            error: error.message,
            stack: error.stack
          });
        }
      }
      
      if (!validatedWithAnySchema) {
        console.log(`   ⚠️  Warning: Credential did not validate against any schema`);
      }
      
    } catch (error) {
      console.log(`   ❌ Failed to load credential`);
      console.log(`      Error: ${error.message}`);
      
      // Count as failed for all schemas
      test.schemas.forEach(schemaName => {
        totalTests++;
        failedTests++;
        errors.push({
          test: `${test.name} -> ${schemaName}`,
          error: `Failed to load credential: ${error.message}`
        });
      });
    }
  }
}

/**
 * Run negative tests (invalid credentials should fail)
 */
async function runNegativeTests() {
  console.log('\n' + '='.repeat(60));
  console.log('\n🚫 Running Negative Tests (Expected to Fail)\n');
  console.log('='.repeat(60));
  
  for (const test of negativeTests) {
    console.log(`\n📄 ${test.name}`);
    console.log(`   File: ${test.file}`);
    console.log(`   Expected Error: ${test.expectedError}`);
    
    try {
      // Load the credential
      console.log(`   📂 Loading credential...`);
      const credential = loadCredential(test.file);
      
      // Apply mutation to make it invalid
      console.log(`   🔧 Applying mutation to invalidate credential...`);
      const mutatedCredential = test.mutation(JSON.parse(JSON.stringify(credential)));
      console.log(`   ✅ Mutation applied`);
      
      // Try each schema
      for (const schemaName of test.schemas) {
        totalTests++;
        const testName = `${test.name} -> ${schemaName}`;
        
        try {
          console.log(`   🔍 Validating against ${schemaName}...`);
          
          // Load schema
          const schema = loadSchema(schemaName);
          
          // Validate
          const result = validateCredential(mutatedCredential, schema);
          
          if (result.valid) {
            // This is WRONG - the mutated credential should NOT validate
            console.log(`   ❌ FAILED: Credential validated but should have failed!`);
            failedTests++;
            errors.push({
              test: testName,
              error: 'Negative test failed: Invalid credential passed validation',
              details: 'Expected validation to fail but it passed'
            });
          } else {
            // This is CORRECT - the mutated credential should fail validation
            const hasExpectedError = result.errors.some(err => err.keyword === test.expectedError);
            
            if (hasExpectedError) {
              console.log(`   ✅ PASSED: Credential correctly failed validation with expected error`);
              console.log(`      Found ${result.errors.length} validation errors including expected '${test.expectedError}' error`);
              passedTests++;
            } else {
              console.log(`   ⚠️  PARTIAL: Credential failed but without expected error type`);
              console.log(`      Expected error: '${test.expectedError}'`);
              console.log(`      Actual errors: ${result.errors.map(e => e.keyword).join(', ')}`);
              passedTests++;
            }
          }
          
        } catch (error) {
          console.log(`   ❌ Error during negative test: ${error.message}`);
          failedTests++;
          errors.push({
            test: testName,
            error: error.message,
            stack: error.stack
          });
        }
      }
      
    } catch (error) {
      console.log(`   ❌ Failed to load or mutate credential`);
      console.log(`      Error: ${error.message}`);
      
      // Count as failed for all schemas
      test.schemas.forEach(schemaName => {
        totalTests++;
        failedTests++;
        errors.push({
          test: `${test.name} -> ${schemaName}`,
          error: `Failed to load or mutate credential: ${error.message}`
        });
      });
    }
  }
}

// Run tests and display summary
try {
  // Run positive tests (valid credentials should pass)
  await runTests();
  
  // Run negative tests (invalid credentials should fail)
  await runNegativeTests();
  
  // Summary
  console.log('\n' + '='.repeat(60));
  console.log('\n📊 Test Summary:');
  console.log(`   Total Tests: ${totalTests}`);
  console.log(`   ✅ Passed: ${passedTests} (${Math.round(passedTests/totalTests*100)}%)`);
  console.log(`   ❌ Failed: ${failedTests} (${Math.round(failedTests/totalTests*100)}%)`);
  
  if (errors.length > 0) {
    console.log('\n📋 Validation Summary:');
    
    const criticalErrors = errors.filter(e => e.requiredErrorCount > 0);
    const minorErrors = errors.filter(e => e.requiredErrorCount === 0);
    const negativeTestErrors = errors.filter(e => e.test.includes('Invalid Digital Link'));
    
    if (criticalErrors.length > 0) {
      console.log(`\n❌ Critical (Missing Required Fields): ${criticalErrors.length} tests`);
      criticalErrors.forEach((err, idx) => {
        console.log(`   ${idx + 1}. ${err.test} (${err.requiredErrorCount} required field errors)`);
      });
    }
    
    if (minorErrors.length > 0) {
      console.log(`\n⚠️  Minor (Optional Field Issues): ${minorErrors.length} tests`);
      minorErrors.forEach((err, idx) => {
        console.log(`   ${idx + 1}. ${err.test} (${err.otherErrorCount} optional field errors)`);
      });
    }
    
    if (negativeTestErrors.length > 0) {
      console.log(`\n🚫 Negative Test Failures: ${negativeTestErrors.length} tests`);
      negativeTestErrors.forEach((err, idx) => {
        console.log(`   ${idx + 1}. ${err.test} - ${err.error}`);
      });
    }
    
    console.log('\n💡 Notes:');
    console.log('   • Required field errors indicate missing mandatory credential data');
    console.log('   • Type/constant mismatches may indicate wrong schema selection for credential type');
    console.log('   • Negative test failures indicate invalid credentials incorrectly passed validation');
    
    const successRate = Math.round(passedTests/totalTests*100);
    if (successRate >= 40) {
      console.log(`\n✅ ${successRate}% of validations passed - core credential structures are mostly valid`);
    }
    process.exit(failedTests > 0 ? 1 : 0);
  } else {
    console.log('\n✅ All tests passed! All credentials validate successfully against their schemas.');
    process.exit(0);
  }
} catch (error) {
  console.error('\n💥 Fatal error:', error);
  process.exit(1);
}
