#!/usr/bin/env bash
# Stamp one version into every manifest that carries it.
#   bash scripts/set-version.sh 1.2.3      (a leading "v" is stripped)
# release.yml re-runs this with the tag's version and fails on `git diff`,
# so a tag can never ship with manifests that disagree with it.
set -euo pipefail

version="${1:?usage: $0 <version>}"
version="${version#v}"
cd "$(dirname "$0")/.."

# Release-version policy. Returns 0 if "$1" may be released.
is_valid_version() {
  # TODO(you): decide the prerelease policy (see chat). Strict X.Y.Z until then.
  [[ $1 =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]
}

# Validation runs before any sed, so the input can't inject sed expressions.
is_valid_version "$version" || { echo "invalid release version: '$version'" >&2; exit 1; }

sed -i -E "s/^version = \"[^\"]*\"/version = \"$version\"/" \
  server/pyproject.toml apps/desktop/src-tauri/Cargo.toml
# Cargo.lock: only the app crate's own entry, never a dependency's.
sed -i -E "/^name = \"financebuddy\"$/{n;s/^version = \"[^\"]*\"/version = \"$version\"/}" \
  apps/desktop/src-tauri/Cargo.lock
# First "version" key only (-i implies per-file ranges in GNU sed).
sed -i -E "0,/\"version\": \"[^\"]*\"/s//\"version\": \"$version\"/" \
  apps/desktop/src-tauri/tauri.conf.json
# npm also keeps package-lock.json in sync.
for app in apps/web apps/desktop; do
  (cd "$app" && npm version "$version" --no-git-tag-version --allow-same-version >/dev/null)
done

echo "$version"
