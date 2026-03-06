#!/bin/sh
set -e
mkdir -p .git/hooks
cp tools/git-hooks/prepare-commit-msg .git/hooks/prepare-commit-msg
chmod +x .git/hooks/prepare-commit-msg
echo "✅ Git hook installed"  