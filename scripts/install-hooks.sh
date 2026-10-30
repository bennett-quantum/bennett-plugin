#!/usr/bin/env bash
set -euo pipefail
root="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
ln -sf ../../scripts/pre-push "$root/.git/hooks/pre-push"
chmod +x "$root/scripts/pre-push"
echo "installed pre-push hook"
