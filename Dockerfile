# Simulation stays on GitHub/Ubuntu. Render runs the control plane and one
# on-demand native SoccerWindow2 desktop. No GPU or paid Render plan required.
FROM python:3.12-slim-bookworm AS native-build
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates cmake make g++ qtbase5-dev libboost-system-dev zlib1g-dev && rm -rf /var/lib/apt/lists/*
WORKDIR /source
RUN git init librcsc && cd librcsc && git remote add origin https://github.com/helios-base/librcsc.git && git fetch --depth 1 origin 65e139327751f2f45d9b5a03b1f59fb5ca700cd2 && git checkout --detach FETCH_HEAD
RUN cmake -S librcsc -B librcsc-build -DCMAKE_INSTALL_PREFIX=/opt/rcss-native -DCMAKE_INSTALL_LIBDIR=lib -DHAVE_NETINET_IN_H=ON && cmake --build librcsc-build -j2 && cmake --install librcsc-build && install -m 644 librcsc/rcsc/time/time_stamp.h /opt/rcss-native/include/rcsc/time/
RUN git init soccerwindow2 && cd soccerwindow2 && git remote add origin https://github.com/helios-base/soccerwindow2.git && git fetch --depth 1 origin 1207fd2e7633b7de56f1618db23fca0338f27414 && git checkout --detach FETCH_HEAD
COPY native/ /arena-patch/native/
COPY scripts/patch_native_bridge.py /arena-patch/scripts/patch_native_bridge.py
RUN python3 /arena-patch/scripts/patch_native_bridge.py /source/soccerwindow2
RUN cmake -S soccerwindow2 -B sw-build -DCMAKE_INSTALL_PREFIX=/opt/rcss-native -DLIBRCSC_INSTALL_DIR=/opt/rcss-native && cmake --build sw-build -j2 && install -m 755 sw-build/soccerwindow2 sw-build/src/sswindow2 /opt/rcss-native/bin/
RUN git init novnc && cd novnc && git remote add origin https://github.com/novnc/noVNC.git && git fetch --depth 1 origin a8dfd6a3ea3c74244f5ebdaa5a7f1023007a7820 && git checkout --detach FETCH_HEAD && rm -rf .git
RUN mkdir /sources && tar --exclude=.git -czf /sources/librcsc-source.tar.gz librcsc && tar --exclude=.git -czf /sources/soccerwindow2-source.tar.gz soccerwindow2

FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends xvfb openbox x11vnc websockify xdotool x11-utils x11-apps libqt5widgets5 libqt5network5 libboost-system1.74.0 libgl1 fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
COPY --from=native-build /opt/rcss-native /opt/rcss-native
COPY --from=native-build /source/novnc /opt/novnc
RUN useradd -m -u 10001 arena && mkdir /app && chown arena:arena /app
WORKDIR /app
COPY --chown=arena:arena app.py cloud_app.py accounts.py billing.py account_store.py player_rcg.py personal_bridge.py github_api.py runner.py offline_logs.py debug_logs.py dataset.py analysis.py presets.py replay.py live.py performance.py team_build.py build_store.py native_desktop.py native_tunnel.py native_assets.py ./
COPY --chown=arena:arena static ./static
COPY --from=native-build /sources ./static/native/source
COPY --chown=arena:arena preset_teams ./preset_teams
USER arena
ENV DATA_DIR=/tmp/arena-unused PORT=8000 PATH=/opt/rcss-native/bin:$PATH LD_LIBRARY_PATH=/opt/rcss-native/lib
EXPOSE 8000
CMD ["python3","cloud_app.py"]
