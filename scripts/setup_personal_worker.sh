#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
sudo apt-get update
sudo apt-get install -y python3 git nodejs cmake build-essential flex libfl-dev bison libboost-all-dev zlib1g-dev autoconf automake libtool pkg-config
cmake -S vendor/rcssserver-19.0.0 -B server-build -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$PWD/server-install"
TASK_BUILD_JOBS=$(nproc)
if [ "$TASK_BUILD_JOBS" -gt 8 ]; then TASK_BUILD_JOBS=8; fi
cmake --build server-build -j "$TASK_BUILD_JOBS"
cmake --install server-build
printf '\nReady. Select personal Ubuntu in the Arena site and copy the worker connection command.\n'
