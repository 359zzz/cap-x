#!/usr/bin/env bash
# Clone the OpenArm v2.0 description into cap-x/third_party and symlink it to ~/.capx.
# Run this on the IPC (the machine physically connected to OpenArm).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
URDF_DIR="${REPO_ROOT}/third_party/openarm_description"
USER_URDF_DIR="${HOME}/.capx/openarm/urdf"

echo "============================================"
echo "OpenArm URDF setup"
echo "============================================"

if [ -d "${URDF_DIR}/.git" ]; then
    echo "URDF repo already exists at ${URDF_DIR}; pulling latest..."
    git -C "${URDF_DIR}" pull --ff-only
else
    echo "Cloning enactic/openarm_description..."
    mkdir -p "$(dirname "${URDF_DIR}")"
    git clone https://github.com/enactic/openarm_description.git "${URDF_DIR}"
fi

# The repo contains output.urdf (generated from xacro). Use it if present.
URDF_FILE="${URDF_DIR}/output.urdf"
if [ ! -f "${URDF_FILE}" ]; then
    echo "ERROR: ${URDF_FILE} not found. The repository may have changed layout."
    echo "Look for a *.urdf file under ${URDF_DIR} and set CAPX_OPENARM_URDF accordingly."
    exit 1
fi

echo "Found URDF: ${URDF_FILE}"

# Symlink to ~/.capx so the runtime can find it without knowing the repo path.
mkdir -p "${USER_URDF_DIR}"
ln -sf "${URDF_FILE}" "${USER_URDF_DIR}/openarm_v20.urdf"

echo ""
echo "Done. Set this environment variable in your launch shell:"
echo "  export CAPX_OPENARM_URDF=\"${URDF_FILE}\""
echo ""
echo "Or rely on the default search order (first CAPX_OPENARM_URDF,"
echo "then ~/.capx/openarm/urdf/openarm_v20.urdf)."
