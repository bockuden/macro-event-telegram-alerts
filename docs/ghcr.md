# GitHub Container Registry

Every pushed release tag matching `v*` runs the publication workflow. It first
executes Ruff, formatting, mypy, and pytest, then builds the image from that
same tag and publishes it to:

```text
ghcr.io/bockuden/macro-event-telegram-alerts
```

The workflow uses its repository-scoped `GITHUB_TOKEN`; no personal access
token or registry credential is stored in this repository. It attaches OCI
source, version, revision, description, and MIT license metadata, makes the
linked package public, and verifies an anonymous pull plus a container smoke
test.

## Use a released image

For a release such as `v0.1.0`, set the service image in `compose.yaml` and
remove its local `build` block:

```yaml
services:
  macro-event-telegram-alerts:
    image: ghcr.io/bockuden/macro-event-telegram-alerts:v0.1.0
```

Then pull and start it without a local build:

```bash
docker compose pull
docker compose up -d
```

Use the version tag as the normal installation reference. For an immutable
deployment, replace the tag with the digest recorded by the release workflow:

```text
ghcr.io/bockuden/macro-event-telegram-alerts@sha256:release-digest
```

`latest` is only a convenience tag and is not the reproducible installation
baseline.
