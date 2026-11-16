  for f in *-sample.json; do python3 validate_credential.py "$f"; python3 render_credential.py "$f" ; echo; done
