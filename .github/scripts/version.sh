#!/usr/bin/env bash
# Version of this build, written into ytmpd/__init__.py (shown in Settings) and given to `flet build`.
#   number: numeric version: "0.2.0" from tag v0.2.0, or __version__ for a manual run
#   label:  for file names: "0.2.0", or "0.1.0-dev.42" for manual run number 42
set -euo pipefail
if [[ "${GITHUB_REF:-}" == refs/tags/v* ]]; then
  label="${GITHUB_REF_NAME#v}"
  number="${label%%-*}"
else
  number="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' ytmpd/__init__.py)"
  label="$number-dev.${GITHUB_RUN_NUMBER:-0}"
fi
sed -i "s/^__version__ = .*/__version__ = \"$label\"/" ytmpd/__init__.py
echo "number=$number" >> "$GITHUB_OUTPUT"
echo "label=$label" >> "$GITHUB_OUTPUT"
echo "Version $label (build $number)"
