# Free Render hosts ONLY the control plane, not the RCSS match.
FROM python:3.12-slim
RUN useradd -m -u 10001 arena && mkdir /app && chown arena:arena /app
WORKDIR /app
COPY --chown=arena:arena app.py cloud_app.py github_api.py runner.py analysis.py presets.py replay.py live.py performance.py team_build.py build_store.py ./
COPY --chown=arena:arena static ./static
COPY --chown=arena:arena preset_teams ./preset_teams
USER arena
ENV DATA_DIR=/tmp/arena-unused PORT=8000
EXPOSE 8000
CMD ["python3","cloud_app.py"]
