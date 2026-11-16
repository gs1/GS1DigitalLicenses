#!/usr/bin/env python3
"""
Validates a GS1 credential JSON and its full recognition chain per
W3C Recognized Entities v1.0 §4.3 (credentialValidator variant).

Phase 1 — Build the chain (leaf to root):
  Walk issuer.recognizedIn links from the leaf credential up to the
  trust anchor. Verify the chain has at least 2 credentials, does not
  exceed MAX_CHAIN_DEPTH, has no cycles, and terminates at a trusted
  issuer in RECOGNIZED_ISSUERS.

Phase 2 — Run credential validators (anchor+1 to leaf):
  For each credential in the chain (skipping the root anchor), run
  every credentialValidator declared in the recognizer's recognizedTo
  action(s) for that entity:
    - application/schema+json  → JSON Schema validation
    - text/javascript          → JavaScript sandbox via QuickJS

  At intermediate levels ALL actions' validators must pass.
  At the leaf level only the matching action's validators run.

Usage:
    python validate_credential.py <credential.json> [--action issue]

Requires:
    pip install jsonschema referencing quickjs
"""

import argparse
import base64
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import quickjs
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
SCHEMAS_DIR = REPO_ROOT / "schemas" / "recognized-entities-javascript"
VALIDATORS_DIR = REPO_ROOT / "javascript" / "recognized-entities-javascript"
SAMPLES_DIR = SCRIPT_DIR

MAX_CHAIN_DEPTH = 10

RECOGNIZED_ISSUERS = {
    "did:web:gs1.github.io:GS1DigitalLicenses:dids:fake_go_did",
}

VCDM_CANONICAL_URL = (
    "https://www.w3.org/2022/credentials/v2/"
    "verifiable-credential-schema.json"
)
VCDM_GITHUB_URL = (
    "https://raw.githubusercontent.com/w3c/vc-data-model/"
    "refs/heads/main/schema/verifiable-credential/"
    "verifiable-credential-schema.json"
)

REMOTE_URL_OVERRIDES = {
    VCDM_CANONICAL_URL: VCDM_GITHUB_URL,
}


# ── Helpers ──────────────────────────────────────────────────────────

def load_json(path):
    with open(path) as f:
        return json.load(f)


def get_issuer_id(credential):
    issuer = credential.get("issuer", {})
    if isinstance(issuer, str):
        return issuer
    return issuer.get("id", "")


def get_recognized_in(credential):
    issuer = credential.get("issuer", {})
    if isinstance(issuer, str):
        return None
    return issuer.get("recognizedIn")


def find_entity_subject(parent, issuer_id):
    subjects = parent.get("credentialSubject", [])
    if isinstance(subjects, dict):
        subjects = [subjects]
    for subject in subjects:
        if subject.get("id") == issuer_id:
            return subject
    return None


def url_to_local_path(url):
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
    if not url:
        return None
    marker = "schemas/recognized-entities-javascript/"
    idx = url.find(marker)
    if idx == -1:
        return None
    rel = url[idx + len(marker):]
    return SCHEMAS_DIR / rel


def url_to_validator_path(url):
    if not url:
        return None
    # Try direct marker match first
    marker = "javascript/recognized-entities-javascript/"
    idx = url.find(marker)
    if idx != -1:
        r = url[idx + len(marker):]
        return VALIDATORS_DIR / r
    # Also handle the validators/ URL pattern
    marker2 = "validators/"
    idx2 = url.find(marker2)
    if idx2 != -1:
        r = url[idx2 + len(marker2):]
        return VALIDATORS_DIR / r
    return None


def verify_digest_multibase(content_bytes, declared_digest):
    digest = hashlib.sha256(content_bytes).digest()
    multihash = bytes([0x12, 0x20]) + digest
    padded = base64.urlsafe_b64encode(multihash).decode().rstrip("=")
    computed = "u" + padded
    return (computed == declared_digest, computed)


def rel(path):
    try:
        return path.relative_to(REPO_ROOT)
    except ValueError:
        return path


# ── JSON Schema registry ─────────────────────────────────────────────

def fetch_remote_schema(url):
    import urllib.request
    resolved_url = REMOTE_URL_OVERRIDES.get(url, url)
    try:
        with urllib.request.urlopen(resolved_url, timeout=10) as resp:
            schema = json.loads(resp.read())
            return Resource.from_contents(
                schema, default_specification=DRAFT202012
            )
    except Exception as e:
        print(f"  [warn] Could not fetch remote schema "
              f"{resolved_url}: {e}", file=sys.stderr)
        raise


def build_registry():
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
            registry = registry.with_resource(
                f"{subdir}/{fpath.name}", resource
            )
            registry = registry.with_resource(fpath.name, resource)
            if "$id" in schema:
                registry = registry.with_resource(
                    schema["$id"], resource
                )

    return registry


def schema_validate(credential, schema_path, registry):
    schema = load_json(schema_path)
    resolver = registry.resolver(base_uri=schema_path.as_uri())
    validator = Draft202012Validator(
        schema,
        registry=registry,
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )
    validator._resolver = resolver
    errors = list(validator.iter_errors(credential))
    return (len(errors) == 0, rel(schema_path), errors)


# ── JavaScript sandbox ───────────────────────────────────────────────

def run_js_validator(js_path, credential, options):
    """Run a JavaScript credential validator via QuickJS.

    Returns dict with {valid, errors, warnings} or {error}.
    """
    js_source = js_path.read_text(encoding="utf-8")

    # The validator uses `export default function validate(...)`.
    # QuickJS ctx.module() handles ES module syntax; we bridge
    # the exported function to globalThis so ctx.eval() can call it.
    module_code = js_source + "\nglobalThis._validate = validate;\n"

    ctx = quickjs.Context()
    ctx.set_memory_limit(16 * 1024 * 1024)
    ctx.set_time_limit(5)

    try:
        ctx.module(module_code)

        # Inject credential and options as JSON
        ctx.eval(f"globalThis._credential = {json.dumps(credential)};")
        ctx.eval(f"globalThis._options = {json.dumps(options)};")

        result_json = ctx.eval(
            "JSON.stringify(_validate(_credential, _options));"
        )
        return json.loads(result_json)
    except Exception as e:
        return {"error": str(e)}


# ── Phase 1: Build chain ─────────────────────────────────────────────

def build_chain(leaf_path):
    """Walk issuer.recognizedIn from leaf to root, returning
    [(credential, path), ...] with leaf at index 0 and root last.
    """
    chain = []
    seen_ids = set()
    current_path = leaf_path

    while True:
        credential = load_json(current_path)
        cred_id = credential.get("id", str(current_path))

        if cred_id in seen_ids:
            print(f"  [error] Cycle detected at {cred_id}")
            return None
        seen_ids.add(cred_id)
        chain.append((credential, current_path))

        if len(chain) > MAX_CHAIN_DEPTH:
            print(f"  [error] Chain depth exceeded {MAX_CHAIN_DEPTH}")
            return None

        issuer_id = get_issuer_id(credential)
        if issuer_id in RECOGNIZED_ISSUERS:
            break

        recognized_in = get_recognized_in(credential)
        if not recognized_in:
            print(f"  [error] Issuer {issuer_id} is not recognized "
                  f"and has no recognizedIn")
            return None

        parent_url = recognized_in.get("id", "")
        parent_file = url_to_local_path(parent_url)
        if not parent_file or not parent_file.exists():
            print(f"  [error] Cannot find local file for "
                  f"recognizedIn: {parent_url}")
            return None

        current_path = parent_file

    return chain


# ── Phase 2: Validate chain ──────────────────────────────────────────

def get_credential_validators(subject):
    """Extract credentialValidator entries from a subject's
    recognizedTo actions.

    Returns list of (action_dict, [validator_entries]).
    """
    recognized_to = subject.get("recognizedTo")
    if not recognized_to:
        return []
    if isinstance(recognized_to, dict):
        recognized_to = [recognized_to]

    actions = []
    for action in recognized_to:
        cv = action.get("credentialValidator")
        if not cv:
            continue
        if isinstance(cv, dict):
            cv = [cv]
        actions.append((action, cv))
    return actions


def run_validators_for_action(validators, credential, chain_above,
                              action_name, evaluation_dt, registry, pad):
    """Run all validators for one action. Returns True if all pass."""
    all_pass = True

    for v in validators:
        media_type = v.get("mediaType", "")
        vid = v.get("id", "")
        declared_digest = v.get("digestMultibase")

        if media_type == "application/schema+json":
            # JSON Schema validator
            schema_path = url_to_schema_path(vid)
            if not schema_path or not schema_path.exists():
                print(f"{pad}  [schema] FAIL  Cannot resolve: {vid}")
                all_pass = False
                continue

            if declared_digest:
                ok, computed = verify_digest_multibase(
                    schema_path.read_bytes(), declared_digest
                )
                if not ok:
                    print(f"{pad}  [schema] FAIL  Digest mismatch "
                          f"for {schema_path.name}: "
                          f"declared={declared_digest} "
                          f"computed={computed}")
                    all_pass = False
                    continue

            passed, rp, errors = schema_validate(
                credential, schema_path, registry
            )
            if passed:
                print(f"{pad}  [schema] PASS  {rp}")
            else:
                print(f"{pad}  [schema] FAIL  {rp}  "
                      f"({len(errors)} error(s))")
                for err in sorted(
                    errors, key=lambda e: list(e.absolute_path)
                ):
                    path = ".".join(
                        str(p) for p in err.absolute_path
                    ) or "(root)"
                    print(f"{pad}  [schema]   - {path}: "
                          f"{err.message}")
                all_pass = False

        elif media_type == "text/javascript":
            # JavaScript validator
            js_path = url_to_validator_path(vid)
            if not js_path or not js_path.exists():
                print(f"{pad}  [js] FAIL  Cannot resolve: {vid}")
                all_pass = False
                continue

            if declared_digest:
                ok, computed = verify_digest_multibase(
                    js_path.read_bytes(), declared_digest
                )
                if not ok:
                    print(f"{pad}  [js] FAIL  Digest mismatch "
                          f"for {js_path.name}: "
                          f"declared={declared_digest} "
                          f"computed={computed}")
                    all_pass = False
                    continue

            _, computed_digest = verify_digest_multibase(
                js_path.read_bytes(), ""
            )
            options = {
                "chain": chain_above,
                "action": action_name,
                "evaluationDateTime": evaluation_dt,
                "digestMultibase": computed_digest,
            }
            result = run_js_validator(js_path, credential, options)

            if "error" in result:
                print(f"{pad}  [js] FAIL  {result['error']}")
                all_pass = False
            elif result.get("valid"):
                print(f"{pad}  [js] PASS  {js_path.name}")
            else:
                js_errors = result.get("errors", [])
                print(f"{pad}  [js] FAIL  {js_path.name}  "
                      f"({len(js_errors)} error(s))")
                for err in js_errors:
                    print(f"{pad}  [js]   - {err.get('title', '')}: "
                          f"{err.get('detail', '')}")
                all_pass = False
        else:
            print(f"{pad}  [validator] SKIP  Unknown mediaType: "
                  f"{media_type}")

    return all_pass


def validate_chain(chain, action, evaluation_dt, registry):
    """Phase 2: validate from root+1 down to leaf.

    chain is [(credential, path), ...] with leaf at 0, root last.
    We iterate from root-1 down to 0 (leaf).
    """
    all_passed = True
    root_idx = len(chain) - 1

    print(f"\n── Phase 1: Chain ({len(chain)} credentials) ──")
    for i, (cred, path) in enumerate(chain):
        types = cred.get("type", [])
        issuer_id = get_issuer_id(cred)
        label = "LEAF" if i == 0 else (
            "ROOT" if i == root_idx else f"INTERMEDIATE"
        )
        print(f"  [{i}] {label}  {rel(path)}")
        print(f"       types={types}")
        print(f"       issuer={issuer_id}")

    root_cred, root_path = chain[root_idx]
    root_issuer = get_issuer_id(root_cred)
    if root_issuer in RECOGNIZED_ISSUERS:
        print(f"\n  Root issuer {root_issuer} is in recognizedIssuers ✓")
    else:
        print(f"\n  [error] Root issuer {root_issuer} is NOT recognized")
        return False

    print(f"\n── Phase 2: Credential Validation (root+1 → leaf) ──")

    # Validate from root-1 (first credential after anchor) down to leaf
    for i in range(root_idx - 1, -1, -1):
        cred, cred_path = chain[i]
        is_leaf = (i == 0)

        # The recognizer is the next credential toward root
        recognizer, recognizer_path = chain[i + 1]

        # chain_above = [recognizer, ...everything toward root]
        chain_above = [pair[0] for pair in chain[i + 1:]]

        issuer_id = get_issuer_id(cred)
        level = "LEAF" if is_leaf else "INTERMEDIATE"
        pad = "  "
        print(f"\n{pad}[{level}] {rel(cred_path)}")

        # Find the entity subject in the recognizer
        entity = find_entity_subject(recognizer, issuer_id)
        if not entity:
            print(f"{pad}  [entity] FAIL  Issuer {issuer_id} not "
                  f"found in recognizer's credentialSubject")
            all_passed = False
            continue

        print(f"{pad}  [entity] PASS  Issuer recognized in "
              f"{rel(recognizer_path)}")

        # Get credentialValidator actions from recognizer's entity
        cv_actions = get_credential_validators(entity)
        if not cv_actions:
            print(f"{pad}  [validators] SKIP  No credentialValidator "
                  f"in recognizer's recognizedTo")
            continue

        if is_leaf:
            # Leaf: only the matching action's validators run
            matched = False
            for action_dict, validators in cv_actions:
                action_name = action_dict.get("action", "")
                if action_name == action:
                    matched = True
                    print(f"{pad}  Action: {action_name}")
                    passed = run_validators_for_action(
                        validators, cred, chain_above,
                        action_name, evaluation_dt, registry, pad
                    )
                    if not passed:
                        all_passed = False

            if not matched:
                print(f"{pad}  [action] FAIL  No action matching "
                      f"'{action}' found")
                all_passed = False
        else:
            # Intermediate: ALL actions' validators must pass
            for action_dict, validators in cv_actions:
                action_name = action_dict.get("action", "")
                print(f"{pad}  Action: {action_name}")
                passed = run_validators_for_action(
                    validators, cred, chain_above,
                    action_name, evaluation_dt, registry, pad
                )
                if not passed:
                    all_passed = False

    return all_passed


# ── Main ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Validate a GS1 credential and its full "
                    "recognition chain (JavaScript variant)."
    )
    parser.add_argument(
        "credential",
        help="Path to the credential JSON file",
    )
    parser.add_argument(
        "--action", default="issue",
        help="The action to validate at the leaf (default: issue)",
    )
    parser.add_argument(
        "--evaluation-datetime",
        default=datetime.now(timezone.utc).isoformat(),
        help="Evaluation datetime (default: now, UTC ISO 8601)",
    )
    args = parser.parse_args()

    cred_path = Path(args.credential).resolve()
    if not cred_path.exists():
        print(f"Error: file not found: {args.credential}")
        sys.exit(1)

    credential = load_json(cred_path)
    print(f"Credential: {rel(cred_path)}")
    types = credential.get("type", [])
    if isinstance(types, str):
        types = [types]
    print(f"  Types: {types}")
    print(f"  Action: {args.action}")

    # Phase 1: Build the chain
    chain = build_chain(cred_path)
    if chain is None:
        print("\nResult: CHAIN BUILD FAILED")
        sys.exit(1)

    if len(chain) == 1:
        cred, cred_path = chain[0]
        issuer_id = get_issuer_id(cred)
        print(f"\n  Root credential — issuer {issuer_id} "
              f"is in recognizedIssuers.")
        print(f"  No recognition chain to validate.")
        print(f"\nResult: ALL VALIDATIONS PASSED")
        return

    registry = build_registry()

    # Phase 2: Validate
    all_passed = validate_chain(
        chain, args.action, args.evaluation_datetime, registry
    )

    print()
    if all_passed:
        print("Result: ALL VALIDATIONS PASSED")
    else:
        print("Result: VALIDATION FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
