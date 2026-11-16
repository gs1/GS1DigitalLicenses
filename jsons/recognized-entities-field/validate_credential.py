#!/usr/bin/env python3
"""
Validates a GS1 credential JSON against its base schema and walks the
full recognized entity trust chain per W3C Recognized Entities 1.0 §4.1.

At each level of the chain:
  1. Validate the credential against its credentialSchema (base schema)
  2. Confirm the credential's issuer appears as a RecognizedEntity in the
     parent credential's credentialSubject
  3. Validate the credential against at least one outputValidation schema
     from the parent's recognizedTo actions
  4. Continue up until reaching a credential with no recognizedIn (root of trust)

Usage:
    python validate_credential.py <credential.json>
    python validate_credential.py gcp-sample.json
"""

import argparse
import json
import sys
import urllib.request
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
SCHEMAS_DIR = REPO_ROOT / "schemas" / "recognized-entities-field"
SAMPLES_DIR = SCRIPT_DIR

MAX_CHAIN_DEPTH = 10

TRUSTED_ISSUERS = {
    "did:web:gs1.github.io:GS1DigitalLicenses:dids:fake_go_did",
}

VCDM_CANONICAL_URL = "https://www.w3.org/2022/credentials/v2/verifiable-credential-schema.json"
VCDM_GITHUB_URL = "https://raw.githubusercontent.com/w3c/vc-data-model/refs/heads/main/schema/verifiable-credential/verifiable-credential-schema.json"

REMOTE_URL_OVERRIDES = {
    VCDM_CANONICAL_URL: VCDM_GITHUB_URL,
}


def fetch_remote_schema(url):
    """Fetch a JSON Schema from a remote URL, with overrides for known 404s."""
    resolved_url = REMOTE_URL_OVERRIDES.get(url, url)
    try:
        with urllib.request.urlopen(resolved_url, timeout=10) as resp:
            schema = json.loads(resp.read())
            return Resource.from_contents(schema, default_specification=DRAFT202012)
    except Exception as e:
        print(f"  [warn] Could not fetch remote schema {resolved_url}: {e}", file=sys.stderr)
        raise


def load_json(path):
    with open(path) as f:
        return json.load(f)


def build_registry():
    """Build a referencing Registry from all schema files for $ref resolution."""
    registry = Registry(retrieve=fetch_remote_schema)

    for subdir in ["base", "generated"]:
        dirpath = SCHEMAS_DIR / subdir
        if not dirpath.exists():
            continue
        for fpath in dirpath.glob("*.json"):
            schema = load_json(fpath)
            resource = DRAFT202012.create_resource(schema)

            file_uri = fpath.as_uri()
            registry = registry.with_resource(file_uri, resource)

            rel_from_schemas = f"{subdir}/{fpath.name}"
            registry = registry.with_resource(rel_from_schemas, resource)

            registry = registry.with_resource(fpath.name, resource)

            if "$id" in schema:
                registry = registry.with_resource(schema["$id"], resource)

    return registry


def find_schema_path(credential):
    """Resolve the credential's credentialSchema to a local file path."""
    cs = credential.get("credentialSchema")
    if not cs:
        return None
    if isinstance(cs, list):
        cs = cs[0]
    schema_url = cs.get("id", "")
    return url_to_schema_path(schema_url)


def url_to_local_path(url):
    """Map a sample JWT URL to a local JSON file path."""
    if not url:
        return None
    basename = url.rsplit("/", 1)[-1]
    if basename.endswith(".jwt"):
        basename = basename[:-4] + ".json"
    candidate = SAMPLES_DIR / basename
    if candidate.exists():
        return candidate
    return None


def url_to_schema_path(url):
    """Map a schema URL to a local schema file path."""
    if not url:
        return None
    marker = "schemas/recognized-entities-field/"
    idx = url.find(marker)
    if idx == -1:
        return None
    rel = url[idx + len(marker):]
    return SCHEMAS_DIR / rel


def get_issuer_id(credential):
    """Extract the issuer's id string from a credential."""
    issuer = credential.get("issuer", {})
    if isinstance(issuer, str):
        return issuer
    return issuer.get("id", "")


def get_recognized_in(credential):
    """Extract the recognizedIn reference from a credential's issuer, if any."""
    issuer = credential.get("issuer", {})
    if isinstance(issuer, str):
        return None
    return issuer.get("recognizedIn")


def find_entity_subject(parent, issuer_id):
    """Find the RecognizedEntity subject in parent whose id matches issuer_id."""
    subjects = parent.get("credentialSubject", [])
    if isinstance(subjects, dict):
        subjects = [subjects]
    for subject in subjects:
        if subject.get("id") == issuer_id:
            return subject
    return None


def resolve_field_path(obj, dotted_path):
    """Resolve a dot-delimited field path on an object. Returns (found, value)."""
    parts = dotted_path.split(".")
    current = obj
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return False, None
    return True, current


def evaluate_field_match(parent_credential, child_credential, rule):
    """Evaluate a FieldMatch rule. Returns (passed, description)."""
    import re as re_mod

    source_field = rule.get("sourceField", "")
    output_field_obj = rule.get("outputField", {})
    if isinstance(output_field_obj, str):
        output_path = output_field_obj
        pattern_template = "^{sourceValue}$"
    else:
        output_path = output_field_obj.get("path", "")
        pattern_template = output_field_obj.get("pattern", "^{sourceValue}$")

    found_src, src_val = resolve_field_path(parent_credential, source_field)
    found_out, out_val = resolve_field_path(child_credential, output_path)

    if not found_src:
        return False, f"sourceField '{source_field}' not found in parent"
    if not found_out:
        return False, f"outputField '{output_path}' not found in child"

    src_val = str(src_val)
    out_val = str(out_val)

    regex = pattern_template.replace("{sourceValue}", re_mod.escape(src_val))
    passed = bool(re_mod.search(regex, out_val))
    desc = f"/{regex}/ vs '{out_val}'"

    if not passed:
        desc = f"FAILED: {desc}"
    return passed, desc


def get_output_validations(subject):
    """Extract outputValidation rules from a subject's recognizedTo.

    Returns a list of (action_name, [validation_items]) tuples, grouped by action.
    Each validation_item is either:
      ("JsonSchema", schema_path) or ("FieldMatch", rule_dict)
    Within an action, all outputValidations must pass (AND).
    Across actions, at least one must fully pass (OR).
    """
    recognized_to = subject.get("recognizedTo")
    if not recognized_to:
        return []
    if isinstance(recognized_to, dict):
        recognized_to = [recognized_to]

    actions = []
    for action in recognized_to:
        ov = action.get("outputValidation")
        if not ov:
            continue
        if isinstance(ov, dict):
            ov = [ov]
        items = []
        action_name = "action"
        for validation in ov:
            val_type = validation.get("type", "JsonSchema")
            if val_type == "FieldMatch":
                items.append(("FieldMatch", validation))
            else:
                schema_url = validation.get("id", "")
                schema_file = url_to_schema_path(schema_url)
                if schema_file and schema_file.exists():
                    items.append(("JsonSchema", schema_file))
                else:
                    items.append(("UnresolvableSchema", schema_url))
                action_name = validation.get("name", action_name)
        if items:
            action_name = action.get("name", action_name)
            actions.append((action_name, items))
    return actions


def schema_validate(credential, schema_path, registry):
    """Validate credential against schema. Returns (passed, rel_path, errors)."""
    schema = load_json(schema_path)
    rel_path = schema_path.relative_to(REPO_ROOT)

    resolver = registry.resolver(base_uri=schema_path.as_uri())
    validator = Draft202012Validator(
        schema,
        registry=registry,
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )
    validator._resolver = resolver

    errors = list(validator.iter_errors(credential))
    return (len(errors) == 0, rel_path, errors)


def print_validation_result(passed, rel_path, errors, label, pad=""):
    """Print a single validation result with errors."""
    prefix = f"{pad}  [{label}]"
    if passed:
        print(f"{prefix} PASS  {rel_path}")
    else:
        print(f"{prefix} FAIL  {rel_path}  ({len(errors)} error(s))")
        for err in sorted(errors, key=lambda e: list(e.absolute_path)):
            path = ".".join(str(p) for p in err.absolute_path) or "(root)"
            print(f"{prefix}   - {path}: {err.message}")



def validate_chain(credential, cred_path, registry, depth=0):
    """
    Validate a credential and walk the full trust chain per RE §4.1.

    Returns True if the entire chain validates successfully.
    """
    if depth > MAX_CHAIN_DEPTH:
        print(f"  [error] Chain depth exceeded {MAX_CHAIN_DEPTH}")
        return False

    pad = "  " * depth
    rel_cred = cred_path.relative_to(REPO_ROOT)
    types = credential.get("type", [])
    if isinstance(types, str):
        types = [types]

    if depth > 0:
        print(f"{pad}Chain[{depth}]: {rel_cred}")
        print(f"{pad}  Types: {types}")

    all_passed = True

    # Step 1: Validate against the base schema (credentialSchema)
    schema_path = find_schema_path(credential)
    if schema_path:
        passed, rel_path, errors = schema_validate(credential, schema_path, registry)
        print_validation_result(passed, rel_path, errors, "base schema", pad)
        if not passed:
            all_passed = False
    else:
        print(f"{pad}  [base schema] FAIL  No credentialSchema found or schema URL not resolvable")
        all_passed = False

    # Check if the issuer is in the trusted set (§4.1 step 4)
    issuer_id = get_issuer_id(credential)
    if issuer_id in TRUSTED_ISSUERS:
        print(f"{pad}  [trust] Issuer {issuer_id} is trusted")
        return all_passed

    # Step 2-4: Walk the recognizedIn chain
    recognized_in = get_recognized_in(credential)
    if not recognized_in:
        print(f"{pad}  [error] Issuer {issuer_id} is not trusted and has no recognizedIn")
        return False

    parent_url = recognized_in.get("id", "")
    parent_file = url_to_local_path(parent_url)
    if not parent_file or not parent_file.exists():
        print(f"{pad}  [error] Cannot find local file for recognizedIn: {parent_url}")
        return False

    parent = load_json(parent_file)

    # Step 2: Confirm the issuer appears as a RecognizedEntity in the parent
    entity_subject = find_entity_subject(parent, issuer_id)
    if not entity_subject:
        print(f"{pad}  [entity] FAIL  Issuer {issuer_id} not found in parent credentialSubject")
        all_passed = False
    else:
        print(f"{pad}  [entity] PASS  Issuer recognized in {parent_file.relative_to(REPO_ROOT)}")

        # Step 3: Validate against parent's outputValidation rules
        # Within a recognizedTo action: all outputValidations must pass (AND)
        # Across recognizedTo actions: at least one must fully pass (OR)
        ov_actions = get_output_validations(entity_subject)
        if ov_actions:
            any_action_passed = False
            for action_name, items in ov_actions:
                action_all_pass = True
                action_output = []
                for val_type, val_data in items:
                    if val_type == "UnresolvableSchema":
                        action_all_pass = False
                        action_output.append(("UnresolvableSchema", False, val_data, None))
                    elif val_type == "JsonSchema":
                        passed, rel_path, errors = schema_validate(credential, val_data, registry)
                        if not passed:
                            action_all_pass = False
                        action_output.append(("JsonSchema", passed, rel_path, errors))
                    elif val_type == "FieldMatch":
                        passed, desc = evaluate_field_match(parent, credential, val_data)
                        if not passed:
                            action_all_pass = False
                        of = val_data.get("outputField", {})
                        if isinstance(of, str):
                            of_path, of_pattern = of, "^{sourceValue}$"
                        else:
                            of_path = of.get("path", "")
                            of_pattern = of.get("pattern", "^{sourceValue}$")
                        label = f"FieldMatch({of_pattern}) {val_data.get('sourceField')} → {of_path}"
                        action_output.append(("FieldMatch", passed, label, desc))
                if action_all_pass:
                    any_action_passed = True
                for entry in action_output:
                    kind = entry[0]
                    passed = entry[1]
                    if kind == "UnresolvableSchema":
                        schema_url = entry[2]
                        print(f"{pad}  [outputValidation] FAIL  Cannot resolve schema: {schema_url}")
                    elif kind == "JsonSchema":
                        _, _, rel_path, errors = entry
                        if passed:
                            print(f"{pad}  [outputValidation] PASS  {rel_path}")
                        elif any_action_passed:
                            print(f"{pad}  [outputValidation] ---   {rel_path}")
                        else:
                            print(f"{pad}  [outputValidation] FAIL  {rel_path}  ({len(errors)} error(s))")
                            for err in sorted(errors, key=lambda e: list(e.absolute_path)):
                                path = ".".join(str(p) for p in err.absolute_path) or "(root)"
                                print(f"{pad}  [outputValidation]   - {path}: {err.message}")
                    elif kind == "FieldMatch":
                        _, _, label, desc = entry
                        if passed:
                            print(f"{pad}  [outputValidation] PASS  {label}")
                        elif any_action_passed:
                            print(f"{pad}  [outputValidation] ---   {label}")
                        else:
                            print(f"{pad}  [outputValidation] FAIL  {label}")
                            print(f"{pad}  [outputValidation]   - {desc}")
            if not any_action_passed:
                print(f"{pad}  [outputValidation] No recognizedTo action fully matched")
                all_passed = False
        else:
            print(f"{pad}  [outputValidation] FAIL  No outputValidation rules found in parent's recognizedTo")
            all_passed = False

    # Step 4: Recurse — validate the parent credential up the chain
    if not validate_chain(parent, parent_file, registry, depth + 1):
        all_passed = False

    return all_passed


def main():
    parser = argparse.ArgumentParser(
        description="Validate a GS1 credential and its full RE trust chain."
    )
    parser.add_argument(
        "credential",
        help="Path to the credential JSON file",
    )
    parser.add_argument(
        "--schema",
        help="Override: path to the schema to validate against (skips auto-detection)",
    )
    args = parser.parse_args()

    cred_path = Path(args.credential).resolve()
    if not cred_path.exists():
        print(f"Error: file not found: {args.credential}")
        sys.exit(1)

    credential = load_json(cred_path)
    rel_cred = cred_path.relative_to(REPO_ROOT)
    print(f"Credential: {rel_cred}")

    types = credential.get("type", [])
    if isinstance(types, str):
        types = [types]
    print(f"  Types: {types}")

    registry = build_registry()

    if args.schema:
        # Manual override: just validate against the given schema
        schema_path = Path(args.schema).resolve()
        passed, rel_path, errors = schema_validate(credential, schema_path, registry)
        print_validation_result(passed, rel_path, errors, "schema")
        if not passed:
            print("\nResult: VALIDATION FAILED")
            sys.exit(1)
        print("\nResult: ALL VALIDATIONS PASSED")
        return

    all_passed = validate_chain(credential, cred_path, registry)

    print()
    if all_passed:
        print("Result: ALL VALIDATIONS PASSED")
    else:
        print("Result: VALIDATION FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
