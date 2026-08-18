#!/usr/bin/env python3
"""
Validates a GS1 credential JSON against its base schema and, if the issuer
has a recognizedIn reference, also validates it against the parent credential's
outputValidation schema (the generated schema).

Usage:
    python validate_credential.py <credential.json>
    python validate_credential.py gcp-sample.json
"""

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
SCHEMAS_DIR = REPO_ROOT / "schemas" / "recognized-entities"
SAMPLES_DIR = SCRIPT_DIR

TYPE_TO_SCHEMA = {
    "GS1PrefixLicenseCredential": "base/gs1-prefix-license-credential.json",
    "GS18PrefixLicenseCredential": "base/gs1-8prefix-license-credential.json",
    "GS1CompanyPrefixLicenseCredential": "base/gs1-company-prefix-license-credential.json",
    "GS1IdentificationKeyLicenseCredential": "base/gs1-identification-key-license-credential.json",
    "KeyCredential": "base/gs1-key-credential.json",
    "KeyAuthorizationCredential": "base/gs1-key-authorization-credential.json",
    "DataCredential": "base/gs1-data-credential.json",
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
            print(f"  [fetch] {url}")
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

    # Use file:// URIs anchored at SCHEMAS_DIR so relative $refs resolve
    base_uri = SCHEMAS_DIR.as_uri() + "/"

    for subdir in ["base", "generated"]:
        dirpath = SCHEMAS_DIR / subdir
        if not dirpath.exists():
            continue
        for fpath in dirpath.glob("*.json"):
            schema = load_json(fpath)
            resource = DRAFT202012.create_resource(schema)

            # Register by file:// URI (enables relative $ref resolution)
            file_uri = fpath.as_uri()
            registry = registry.with_resource(file_uri, resource)

            # Also register by relative path from SCHEMAS_DIR
            rel_from_schemas = f"{subdir}/{fpath.name}"
            registry = registry.with_resource(rel_from_schemas, resource)

            # Register by filename alone (for same-directory refs)
            registry = registry.with_resource(fpath.name, resource)

            # Register by $id if present
            if "$id" in schema:
                registry = registry.with_resource(schema["$id"], resource)

    return registry


def find_schema_path(credential):
    """Determine which base schema file validates this credential's type."""
    types = credential.get("type", [])
    if isinstance(types, str):
        types = [types]

    for t in types:
        if t in TYPE_TO_SCHEMA:
            return SCHEMAS_DIR / TYPE_TO_SCHEMA[t]
    return None


def find_output_validation_schemas(credential):
    """
    If the credential's issuer has a recognizedIn, find the parent credential
    and return all outputValidation schema paths from the parent's
    credentialSubject.recognizedTo.
    """
    issuer = credential.get("issuer", {})
    if isinstance(issuer, str):
        return []

    recognized_in = issuer.get("recognizedIn")
    if not recognized_in:
        return []

    parent_url = recognized_in.get("id", "")
    parent_file = url_to_local_path(parent_url)
    if not parent_file or not parent_file.exists():
        print(f"  [warn] Cannot find local file for recognizedIn: {parent_url}")
        return []

    parent = load_json(parent_file)
    subjects = parent.get("credentialSubject", [])
    if isinstance(subjects, dict):
        subjects = [subjects]

    schemas = []
    for subject in subjects:
        recognized_to = subject.get("recognizedTo")
        if not recognized_to:
            continue
        if isinstance(recognized_to, dict):
            recognized_to = [recognized_to]
        for action in recognized_to:
            ov = action.get("outputValidation")
            if not ov:
                continue
            if isinstance(ov, dict):
                ov = [ov]
            for validation in ov:
                schema_url = validation.get("id", "")
                schema_file = url_to_schema_path(schema_url)
                if schema_file and schema_file.exists():
                    schemas.append(schema_file)

    return schemas


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
    # Extract path after the repo base
    marker = "schemas/recognized-entities/"
    idx = url.find(marker)
    if idx == -1:
        return None
    rel = url[idx + len(marker):]
    candidate = SCHEMAS_DIR / rel
    return candidate


def validate(credential, schema_path, registry, label=""):
    """Run JSON Schema validation and report results."""
    schema = load_json(schema_path)
    rel_path = schema_path.relative_to(REPO_ROOT)

    # Use the schema's file:// URI so relative $refs resolve from its directory
    resolver = registry.resolver(base_uri=schema_path.as_uri())
    validator = Draft202012Validator(
        schema,
        registry=registry,
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )
    # Patch the resolver to use our base URI
    validator._resolver = resolver

    errors = list(validator.iter_errors(credential))
    prefix = f"  [{label}] " if label else "  "

    if not errors:
        print(f"{prefix}PASS  {rel_path}")
        return True
    else:
        print(f"{prefix}FAIL  {rel_path}  ({len(errors)} error(s))")
        for err in sorted(errors, key=lambda e: list(e.absolute_path)):
            path = ".".join(str(p) for p in err.absolute_path) or "(root)"
            print(f"{prefix}  - {path}: {err.message}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Validate a GS1 credential against its schema."
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
    print(f"Credential: {cred_path.relative_to(REPO_ROOT)}")

    types = credential.get("type", [])
    if isinstance(types, str):
        types = [types]
    print(f"  Types: {types}")

    registry = build_registry()
    all_passed = True

    # 1. Validate against the base schema (or override)
    if args.schema:
        schema_path = Path(args.schema).resolve()
    else:
        schema_path = find_schema_path(credential)

    if schema_path:
        if not validate(credential, schema_path, registry, label="base schema"):
            all_passed = False
    else:
        print("  [skip] No matching base schema found for types")

    # 2. Validate against parent's outputValidation schema(s)
    ov_schemas = find_output_validation_schemas(credential)
    if ov_schemas:
        ov_passed = False
        ov_results = []
        for ov_schema in ov_schemas:
            rel = ov_schema.relative_to(REPO_ROOT)
            passed = validate(credential, ov_schema, registry, label="outputValidation")
            ov_results.append((rel, passed))
            if passed:
                ov_passed = True
        if not ov_passed:
            print("  [outputValidation] No outputValidation schema matched")
            all_passed = False
    else:
        issuer = credential.get("issuer", {})
        if isinstance(issuer, dict) and issuer.get("recognizedIn"):
            print("  [skip] Parent found but no outputValidation schema matched")
        else:
            print("  [info] No recognizedIn — root of trust or non-RE credential")

    print()
    if all_passed:
        print("Result: ALL VALIDATIONS PASSED")
    else:
        print("Result: VALIDATION FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
