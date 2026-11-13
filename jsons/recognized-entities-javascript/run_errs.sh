for f in errors/*-sample.json; do python3 validate_credential.py "$f"; echo; done
