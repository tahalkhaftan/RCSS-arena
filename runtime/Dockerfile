# Match/build workers only. This is independent of Render's graphical monitor.
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates git python3 nodejs cmake build-essential flex libfl-dev bison \
    libboost-all-dev zlib1g-dev autoconf automake libtool pkg-config \
    && rm -rf /var/lib/apt/lists/*
COPY vendor/rcssserver-19.0.0 /tmp/arena-image-build/server
COPY team_build.py /opt/arena-runtime/team_build.py
COPY runtime/build_runtime.py /opt/arena-runtime/build_runtime.py
RUN python3 /opt/arena-runtime/build_runtime.py && rm -rf /tmp/arena-image-build
ENV RCSSSERVER=/opt/arena-server/bin/rcssserver \
    LD_LIBRARY_PATH=/opt/arena-server/lib \
    ARENA_PREBUILT_LIBRARIES=/opt/arena-libs/manifest.json
# Neither librcsc prefix is exported globally. Selection happens per team.
WORKDIR /workspace
