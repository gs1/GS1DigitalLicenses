// --- Predecessor digests: older versions of this file still accepted ---
const ACCEPTED_PREDECESSOR_DIGESTS = [
  // Add previous version digests here during version transitions.
  // Example: "uEiCOzcc-36fMCwOGzEqVAUnRtVcwC5wgJEy1eRpyA4IkYQ"
];

// --- Schema validator dispatch by credential type ---
const SCHEMA_VALIDATOR_MAP = {
  'GS1PrefixLicenseCredential': _schemaValidators.validatePrefixLicense,
  'GS18PrefixLicenseCredential': _schemaValidators.validate8PrefixLicense,
  'GS1CompanyPrefixLicenseCredential': _schemaValidators.validateCompanyPrefixLicense,
  'GS1IdentificationKeyLicenseCredential': _schemaValidators.validateIdKeyLicense,
  'GS1KeyCredential': _schemaValidators.validateKeyCredential,
  'DataCredential': _schemaValidators.validateDataCredential,
};

export default function validate(credential, options) {
  const errors = [];
  const warnings = [];

  const knownOptions = new Set([
    'chain', 'action', 'evaluationDateTime', 'digestMultibase'
  ]);
  for(const name of Object.keys(options)) {
    if(!knownOptions.has(name)) {
      const error = new Error(`Unrecognized option "${name}".`);
      error.type =
        'https://www.w3.org/TR/vc-data-model#UNRECOGNIZED_OPTION_ERROR';
      throw error;
    }
  }

  const {chain, digestMultibase} = options;
  if(!Array.isArray(chain) || chain.length === 0) {
    errors.push({
      type: 'https://id.gs1.org/validators#MISSING_CHAIN',
      title: 'Missing recognition chain',
      detail: 'This validator requires the recognition chain.'
    });
    return {valid: false, errors, warnings};
  }

  // Build the set of accepted digests: current (from verifier) + predecessors
  const acceptedDigests = new Set(ACCEPTED_PREDECESSOR_DIGESTS);
  if(digestMultibase) {
    acceptedDigests.add(digestMultibase);
  }

  // --- Step 1: Schema validation ---
  const childTypes = asArray(credential.type);
  const schemaValidator = findSchemaValidator(childTypes);
  if(schemaValidator) {
    const schemaValid = schemaValidator(credential);
    if(!schemaValid) {
      const schemaErrors = (schemaValidator.errors || []).map(e => ({
        type: 'https://id.gs1.org/validators#SCHEMA_VALIDATION_ERROR',
        title: 'Schema validation failed',
        detail: `${e.instancePath || '/'}: ${e.message}`
      }));
      errors.push(...schemaErrors);
      return {valid: false, errors, warnings};
    }
  }

  // --- Step 2: Cross-credential field validation ---
  const parent = chain[0];
  const issuerId = getId(credential.issuer);
  const entity = findEntity(parent, issuerId);

  if(!entity) {
    errors.push({
      type: 'https://id.gs1.org/validators#ENTITY_NOT_FOUND',
      title: 'Recognized entity not found',
      detail: `Issuer ${issuerId} not found in parent credentialSubject.`
    });
    return {valid: false, errors, warnings};
  }

  const parentTypes = asArray(parent.type);
  const childSubject = asObject(credential.credentialSubject);
  const entitySubject = entity;

  if(hasType(parentTypes, 'GS1PrefixLicenseCredential') &&
     hasType(childTypes, 'GS1CompanyPrefixLicenseCredential')) {
    validatePrefixToGcp(entitySubject, childSubject, errors);
  } else if(hasType(parentTypes, 'GS18PrefixLicenseCredential') &&
            hasType(childTypes, 'GS1IdentificationKeyLicenseCredential')) {
    validate8PrefixToIdKey(entitySubject, childSubject, errors);
  } else if(hasType(parentTypes, 'GS1CompanyPrefixLicenseCredential') &&
            hasType(childTypes, 'GS1KeyCredential')) {
    validateGcpToKey(entitySubject, childSubject, errors);
  } else if(hasType(parentTypes, 'GS1CompanyPrefixLicenseCredential') &&
            hasType(childTypes, 'GS1IdentificationKeyLicenseCredential')) {
    validateGcpToIdKey(entitySubject, childSubject, errors);
  } else if(hasType(parentTypes, 'GS1IdentificationKeyLicenseCredential') &&
            hasType(childTypes, 'GS1KeyCredential')) {
    validateIdKeyToKey(entitySubject, childSubject, errors);
  } else if(hasType(parentTypes, 'GS1KeyCredential') &&
            hasType(childTypes, 'GS1KeyCredential')) {
    validateKeyToKey(entitySubject, childSubject, errors);
  } else if(hasType(parentTypes, 'GS1KeyCredential') &&
            hasType(childTypes, 'DataCredential')) {
    validateKeyToData(entitySubject, childSubject, errors);
  } else {
    errors.push({
      type: 'https://id.gs1.org/validators#UNKNOWN_TRANSITION',
      title: 'Unknown credential transition',
      detail: `No validation rule for parent types [${parentTypes}] ` +
              `to child types [${childTypes}].`
    });
  }

  // --- Step 3: Chain continuity check ---
  if(errors.length === 0 && acceptedDigests.size > 0) {
    validateChainContinuity(entitySubject, acceptedDigests, errors, warnings);
    validateChainContinuity(childSubject, acceptedDigests, errors, warnings);
  }

  return {valid: errors.length === 0, errors, warnings};
}

// --- Chain continuity ---

function validateChainContinuity(entity, acceptedDigests, errors, warnings) {
  const recognizedTo = entity.recognizedTo;
  if(!recognizedTo) return;

  const actions = asArray(recognizedTo);
  for(const action of actions) {
    if(!action.credentialValidator) {
      errors.push({
        type: 'https://id.gs1.org/validators#CHAIN_CONTINUITY_ERROR',
        title: 'Chain continuity broken',
        detail: 'A recognized action omits the credentialValidator entirely. ' +
                'Every delegated action must reference a JavaScript validator ' +
                'with an approved digest.'
      });
      continue;
    }
    const validators = asArray(action.credentialValidator);

    const hasApprovedValidator = validators.some(v =>
      v.mediaType === 'text/javascript' && acceptedDigests.has(v.digestMultibase)
    );

    if(!hasApprovedValidator) {
      errors.push({
        type: 'https://id.gs1.org/validators#CHAIN_CONTINUITY_ERROR',
        title: 'Chain continuity broken',
        detail: 'The recognized action\'s credentialValidator does not ' +
                'include a JavaScript validator with an approved digest. ' +
                'Accepted digests: ' +
                [...acceptedDigests].join(', ')
      });
    }
  }
}

// --- Cross-credential validation rules ---

function validatePrefixToGcp(entity, child, errors) {
  const prefix = entity.licenseValue;
  const gcp = child.licenseValue;
  if(typeof prefix !== 'string' || typeof gcp !== 'string') {
    errors.push(missingField('licenseValue'));
    return;
  }
  if(!gcp.startsWith(prefix) || gcp.length <= prefix.length ||
     !isDigits(gcp.slice(prefix.length))) {
    errors.push({
      type: 'https://id.gs1.org/validators#PREFIX_MISMATCH',
      title: 'GCP does not extend prefix',
      detail: `GCP "${gcp}" does not start with prefix "${prefix}" ` +
              `followed by additional digits.`
    });
  }
}

function validate8PrefixToIdKey(entity, child, errors) {
  const prefix = entity.licenseValue;
  const idKey = child.licenseValue;
  if(typeof prefix !== 'string' || typeof idKey !== 'string') {
    errors.push(missingField('licenseValue'));
    return;
  }
  const pattern = new RegExp('^0+' + prefix + '\\d+$');
  if(!pattern.test(idKey)) {
    errors.push({
      type: 'https://id.gs1.org/validators#PREFIX_MISMATCH',
      title: 'ID key does not extend 8-prefix',
      detail: `ID key "${idKey}" does not match pattern ` +
              `0+${prefix}\\d+ (zero-padded 8-prefix plus digits).`
    });
  }
}

function validateGcpToKey(entity, child, errors) {
  const gcp = entity.licenseValue;
  const link = child.gs1DigitalLink;
  if(typeof gcp !== 'string') {
    errors.push(missingField('licenseValue'));
    return;
  }
  if(typeof link !== 'string') {
    errors.push(missingField('gs1DigitalLink'));
    return;
  }
  const pattern = new RegExp(
    '^https://id\\.gs1\\.org/' +
    '(01|8006|8013|8010|414|417|8017|8018|255|00|253|401|402|8003|8004)/' +
    '0*' + gcp + '\\d+'
  );
  if(!pattern.test(link)) {
    errors.push({
      type: 'https://id.gs1.org/validators#PREFIX_MISMATCH',
      title: 'Digital Link key does not contain GCP',
      detail: `Digital Link "${link}" does not contain GCP "${gcp}" ` +
              `under a recognized GS1 AI.`
    });
  }
}

function validateGcpToIdKey(entity, child, errors) {
  const gcp = entity.licenseValue;
  const idKey = child.licenseValue;
  if(typeof gcp !== 'string' || typeof idKey !== 'string') {
    errors.push(missingField('licenseValue'));
    return;
  }
  const pattern = new RegExp('^0*' + gcp + '\\d+$');
  if(!pattern.test(idKey)) {
    errors.push({
      type: 'https://id.gs1.org/validators#PREFIX_MISMATCH',
      title: 'ID key license does not extend GCP',
      detail: `ID key "${idKey}" does not match pattern ` +
              `0*${gcp}\\d+ (zero-padded GCP plus digits).`
    });
  }
}

function validateIdKeyToKey(entity, child, errors) {
  const idKey = entity.licenseValue;
  const link = child.gs1DigitalLink;
  if(typeof idKey !== 'string') {
    errors.push(missingField('licenseValue'));
    return;
  }
  if(typeof link !== 'string') {
    errors.push(missingField('gs1DigitalLink'));
    return;
  }
  const expected = 'https://id.gs1.org/01/' + idKey;
  if(!link.startsWith(expected)) {
    errors.push({
      type: 'https://id.gs1.org/validators#PREFIX_MISMATCH',
      title: 'Digital Link does not match licensed ID key',
      detail: `Digital Link "${link}" does not start with ` +
              `"${expected}".`
    });
  }
}

function validateKeyToKey(entity, child, errors) {
  const parentLink = entity.gs1DigitalLink;
  const childLink = child.gs1DigitalLink;
  if(typeof parentLink !== 'string') {
    errors.push(missingField('parent gs1DigitalLink'));
    return;
  }
  if(typeof childLink !== 'string') {
    errors.push(missingField('child gs1DigitalLink'));
    return;
  }
  if(!childLink.startsWith(parentLink + '/10/')) {
    errors.push({
      type: 'https://id.gs1.org/validators#SCOPE_MISMATCH',
      title: 'Key credential does not narrow scope',
      detail: `Child Digital Link "${childLink}" does not start with ` +
              `parent "${parentLink}/10/".`
    });
  }
}

function validateKeyToData(entity, child, errors) {
  const parentLink = entity.gs1DigitalLink;
  const childId = child.id;
  if(typeof parentLink !== 'string') {
    errors.push(missingField('parent gs1DigitalLink'));
    return;
  }
  if(typeof childId !== 'string') {
    errors.push(missingField('child credentialSubject.id'));
    return;
  }
  if(childId !== parentLink) {
    errors.push({
      type: 'https://id.gs1.org/validators#SCOPE_MISMATCH',
      title: 'Data credential does not match key',
      detail: `Data subject id "${childId}" does not match ` +
              `key Digital Link "${parentLink}".`
    });
  }
}

// --- Helpers ---

function findSchemaValidator(types) {
  for(const [typeName, validator] of Object.entries(SCHEMA_VALIDATOR_MAP)) {
    if(types.includes(typeName)) return validator;
  }
  return null;
}

function getId(value) {
  return typeof value === 'string' ? value : value?.id;
}

function asArray(value) {
  return Array.isArray(value) ? value : [value];
}

function asObject(value) {
  return Array.isArray(value) ? value[0] : value;
}

function hasType(types, typeName) {
  return types.includes(typeName);
}

function isDigits(str) {
  return /^\d+$/.test(str);
}

function findEntity(parent, issuerId) {
  const subjects = [].concat(parent.credentialSubject);
  return subjects.find(s => s.id === issuerId);
}

function missingField(fieldName) {
  return {
    type: 'https://id.gs1.org/validators#MISSING_FIELD',
    title: 'Missing required field',
    detail: `Required field "${fieldName}" is missing or not a string.`
  };
}
