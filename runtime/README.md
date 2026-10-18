# Prepared match and source-build environment

Matches and the website's source-build button use the same digest-pinned Ubuntu
24.04 image in `ghcr.io/tahalkhaftan/rcss-arena-runtime`. This is separate from
Render's SoccerWindow2 image; it does not change the native monitor or site UI.

`prepare-runtime.yml` computes a content key from the server source, Docker recipe,
image builder and `team_build.py` (including its exact library revisions). On a hit
it resolves the existing image digest without apt, compilation or a Docker build.
On a miss it builds and publishes the new environment. The first run takes longer;
later tests still wait for a runner and download the image. No fixed startup time
is promised. The image is also warmed and tested when relevant code is pushed.

The image contains RCSSServer **19.0.0**, Python, Node and build tools. APIs are
isolated and are never registered globally with ldconfig:

| Base | Pinned library | Prefix |
| --- | --- | --- |
| school | RCSS-IR/StarterLibRCSC-V2 `af506602e0c7f4872101a86c63e1a9f662602b8b` | `/opt/arena-libs/school/local/starter` |
| university | helios-base/librcsc `078d59ff85c336f94c021adac060ef6f2e63c575` | `/opt/arena-libs/university` |

Starter's CMake forces `$HOME/local/starter`, so only its image-build step gets
an isolated HOME. Uploaded teams use explicit configure/CMake prefixes, pkg-config
and runtime library paths for their selected base. A prepared manifest with the
wrong repository/revision is rejected. Each compiled ZIP includes its own library
aliases as ordinary files, so relocation does not depend on the image paths.
Personal workers without a prepared manifest keep building the exact pinned API
as before. Teams uploaded as binaries keep their existing bundled libraries.

Corresponding library sources are included in `/opt/arena-sources` in the image;
server source remains in this public repository. Team uploads, private results,
tokens and account settings are never baked into the image. Publishing uses the
workflow's own `GITHUB_TOKEN`; there is no new user PAT or Render setting to add.
The package may remain private; jobs authenticate to pull it with package-read
permission. Concurrent requests can reuse the same published image. Only preparation has
package-write permission; match/build jobs have package-read permission.

`Verify prepared match environment` builds both pinned official agent bases,
checks the relocated binaries with `ldd`, compares the packaged shared libraries
against the selected prefix, and completes real 6000-cycle preset matches. Its
first preparation publishes the runtime before tests consume it. Re-running the
workflow exercises the reuse path. To update dependencies, change the relevant
pins/source and let verification prepare a new digest before use.
