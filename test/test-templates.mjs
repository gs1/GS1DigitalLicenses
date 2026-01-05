import Mustache from 'mustache';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Template to JSON file mappings
const templateMappings = {
  'gs1-sample-license-template.svg': [
    'gcp-sample.json',
    'gs1-prefix-license-sample.json',
    'gln-key-credential-sample.json',
    'gtin8-id-key-license-sample.json',
    'gtin8-prefix-sample.json',
    'id-key-license-sample.json'
  ],
  'gs1-sample-key-template.svg': [
    'gtin-key-credential-sample.json',
    'gtin-batch-key-credential-sample.json',
    'gtin-serial-key-credential-sample.json',
    'grai-key-credential-sample.json',
    'sscc-key-credential-sample.json'
  ],
  'gs1-sample-product-data-template.svg': [
    'product-data-credential-sample.json',
    'organization-data-credential-sample.json',
    'grai-data-credential-sample.json',
    'sscc-data-credential-sample.json'
  ]
};

const templatesDir = path.join(__dirname, '../templates');
const jsonsDir = path.join(__dirname, '../jsons');
const outputDir = path.join(__dirname, 'output');

// Create output directory if it doesn't exist
if (!fs.existsSync(outputDir)) {
  fs.mkdirSync(outputDir, { recursive: true });
}

let totalTests = 0;
let passedTests = 0;
let failedTests = 0;
const errors = [];

console.log('🧪 Testing GS1 Mustache Templates\n');
console.log('='.repeat(60));

// Process each template
for (const [templateFile, jsonFiles] of Object.entries(templateMappings)) {
  const templatePath = path.join(templatesDir, templateFile);
  
  console.log(`\n📄 Template: ${templateFile}`);
  
  // Check if template exists
  if (!fs.existsSync(templatePath)) {
    console.error(`   ❌ Template file not found: ${templatePath}`);
    failedTests++;
    errors.push(`Template not found: ${templateFile}`);
    continue;
  }
  
  const template = fs.readFileSync(templatePath, 'utf-8');
  
  // Test each JSON file with this template
  for (const jsonFile of jsonFiles) {
    totalTests++;
    const jsonPath = path.join(jsonsDir, jsonFile);
    const testName = `${templateFile} + ${jsonFile}`;
    
    try {
      // Check if JSON file exists
      if (!fs.existsSync(jsonPath)) {
        throw new Error(`JSON file not found: ${jsonPath}`);
      }
      
      // Load and parse JSON
      const jsonContent = fs.readFileSync(jsonPath, 'utf-8');
      const data = JSON.parse(jsonContent);
      
      // Render template with Mustache
      const rendered = Mustache.render(template, data);
      
      // Check if rendering produced output
      if (!rendered || rendered.trim().length === 0) {
        throw new Error('Rendering produced empty output');
      }
      
      // Save rendered output
      const outputFileName = `${path.basename(jsonFile, '.json')}_rendered.svg`;
      const outputPath = path.join(outputDir, outputFileName);
      fs.writeFileSync(outputPath, rendered);
      
      console.log(`   ✅ ${jsonFile}`);
      passedTests++;
      
    } catch (error) {
      console.log(`   ❌ ${jsonFile}`);
      console.log(`      Error: ${error.message}`);
      failedTests++;
      errors.push({
        test: testName,
        error: error.message,
        stack: error.stack
      });
    }
  }
}

// Summary
console.log('\n' + '='.repeat(60));
console.log('\n📊 Test Summary:');
console.log(`   Total Tests: ${totalTests}`);
console.log(`   ✅ Passed: ${passedTests}`);
console.log(`   ❌ Failed: ${failedTests}`);

if (failedTests > 0) {
  console.log('\n❌ Errors:');
  errors.forEach((err, idx) => {
    if (typeof err === 'string') {
      console.log(`   ${idx + 1}. ${err}`);
    } else {
      console.log(`   ${idx + 1}. ${err.test}`);
      console.log(`      ${err.error}`);
    }
  });
  process.exit(1);
} else {
  console.log('\n✅ All tests passed!');
  console.log(`\n📁 Rendered SVG files saved to: ${outputDir}`);
  process.exit(0);
}

