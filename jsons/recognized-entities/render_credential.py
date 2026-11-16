#!/usr/bin/env python3
"""
Renders a GS1 credential JSON using its renderMethod SVG mustache template.

Usage:
    python render_credential.py <credential.json>
    python render_credential.py gcp-sample.json
    python render_credential.py gcp-sample.json -o output.svg

Requires: pip install chevron
"""

import argparse
import json
import os
import sys
import webbrowser
import tempfile
from pathlib import Path

try:
    import chevron
except ImportError:
    print("Error: chevron is required. Install with: pip install chevron", file=sys.stderr)
    sys.exit(1)


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent

URL_PREFIX = "https://gs1.github.io/GS1DigitalLicenses/"


def url_to_local_path(url: str) -> Path:
    if url.startswith(URL_PREFIX):
        relative = url[len(URL_PREFIX):]
        return REPO_ROOT / relative
    return None


def flatten_subject(credential: dict) -> dict:
    subject = credential.get("credentialSubject", {})
    if isinstance(subject, list) and len(subject) > 0:
        subject = subject[0]
    return {**credential, "credentialSubject": subject}


def main():
    parser = argparse.ArgumentParser(description="Render a credential using its SVG mustache template")
    parser.add_argument("credential", help="Path to credential JSON file")
    parser.add_argument("-o", "--output", help="Output SVG file path (default: opens in browser)")
    args = parser.parse_args()

    cred_path = Path(args.credential)
    if not cred_path.is_absolute():
        cred_path = SCRIPT_DIR / cred_path

    if not cred_path.exists():
        print(f"Error: credential file not found: {cred_path}", file=sys.stderr)
        sys.exit(1)

    with open(cred_path) as f:
        credential = json.load(f)

    render_methods = credential.get("renderMethod", [])
    if not render_methods:
        print("Error: credential has no renderMethod", file=sys.stderr)
        sys.exit(1)

    template_url = render_methods[0].get("template", {}).get("id")
    if not template_url:
        print("Error: renderMethod has no template id", file=sys.stderr)
        sys.exit(1)

    template_path = url_to_local_path(template_url)
    if not template_path or not template_path.exists():
        print(f"Error: template not found locally: {template_url}", file=sys.stderr)
        if template_path:
            print(f"  Expected at: {template_path}", file=sys.stderr)
        sys.exit(1)

    with open(template_path) as f:
        template_svg = f.read()

    data = flatten_subject(credential)

    rendered = chevron.render(template_svg, data)

    if args.output:
        out_path = Path(args.output)
        with open(out_path, "w") as f:
            f.write(rendered)
        print(f"Rendered SVG written to: {out_path}")
    else:
        with tempfile.NamedTemporaryFile(suffix=".svg", delete=False, mode="w") as f:
            f.write(rendered)
            tmp_path = f.name
        print(f"Opening rendered SVG in browser: {tmp_path}")
        webbrowser.open(f"file://{tmp_path}")


if __name__ == "__main__":
    main()
