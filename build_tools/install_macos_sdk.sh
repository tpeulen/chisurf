#!/usr/bin/env bash
# Configure macOS builds on CI: build against the runner's current SDK and set
# the deployment target to conda-forge's default minimum (macOS 11.0).
#
# Apple's supported way to support older macOS versions is a newer SDK plus
# MACOSX_DEPLOYMENT_TARGET; no old SDK download or Xcode Info.plist edits are
# needed. 11.0 is also the minimum for Apple Silicon (macos-latest runners).
# See https://conda-forge.org/docs/maintainer/knowledge_base/#requiring-newer-macos-sdks
#
# Override with MACOSX_DEPLOYMENT_TARGET in the workflow env if needed.
set -euo pipefail

MACOSX_DEPLOYMENT_TARGET="${MACOSX_DEPLOYMENT_TARGET:-11.0}"
SDKROOT="$(xcrun --sdk macosx --show-sdk-path)"

echo "macOS SDK: ${SDKROOT} ($(xcrun --sdk macosx --show-sdk-version))"
echo "MACOSX_DEPLOYMENT_TARGET: ${MACOSX_DEPLOYMENT_TARGET}"

if [[ -n "${GITHUB_ENV:-}" ]]; then
  {
    echo "MACOSX_DEPLOYMENT_TARGET=${MACOSX_DEPLOYMENT_TARGET}"
    echo "SDKROOT=${SDKROOT}"
    echo "CMAKE_OSX_SYSROOT=${SDKROOT}"
  } >> "${GITHUB_ENV}"
fi
