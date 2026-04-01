#!/bin/sh

# 이 스크립트는 저장소 훅 설치와 관리에 필요한 보조 작업을 담당한다.
set -e
mkdir -p .git/hooks
cp tools/git-hooks/prepare-commit-msg .git/hooks/prepare-commit-msg
chmod +x .git/hooks/prepare-commit-msg
echo "✅ Git hook installed"  