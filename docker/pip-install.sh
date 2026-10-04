#!/bin/sh
# Build-time helper. If an `extra_ca` build secret (PEM) is provided, pip trusts it in addition to
# the default bundle. TLS verification is never disabled, and the secret is not stored in the image.
set -eu
if [ -s /run/secrets/extra_ca ]; then
  bundle="$(mktemp)"
  cat "$(python -c 'import pip._vendor.certifi as c; print(c.where())')" /run/secrets/extra_ca > "$bundle"
  pip install --cert "$bundle" "$@"
  rm -f "$bundle"
else
  pip install "$@"
fi
