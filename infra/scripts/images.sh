#!/usr/bin/env bash
# build | import | push for the images this repo builds. Image refs and tags are read from the
# rendered manifests, so k8s/base/kustomization.yaml is the only place a tag is set.
. "$(dirname "$0")/lib.sh"
need docker kubectl
cmd=${1:?usage: images.sh build|import|push}

refs() {
  render | grep -Eo "ghcr.io/$GHCR_OWNER/[a-z0-9-]+:[A-Za-z0-9._-]+" | sort -u
}

# Sets DOCKERFILE, CTX and BUILD_ARGS for images built here; fails for anything else (e.g. a teammate's image).
build_spec() {
  BUILD_ARGS=""
  case "$1" in
    cdc-tools) DOCKERFILE="$INFRA_DIR/images/tools/Dockerfile"; CTX="$INFRA_DIR" ;;
    *) return 1 ;;
  esac
}

ours=""
for ref in $(refs); do
  name=${ref#ghcr.io/$GHCR_OWNER/}
  name=${name%%:*}
  if build_spec "$name"; then ours="$ours $ref"; fi
done
[ -n "$ours" ] || die "no buildable images referenced by overlay $OVERLAY"

case "$cmd" in
  build)
    for ref in $ours; do
      name=${ref#ghcr.io/$GHCR_OWNER/}; build_spec "${name%%:*}"
      log "docker build $ref"
      # shellcheck disable=SC2086
      docker build -t "$ref" -f "$DOCKERFILE" $BUILD_ARGS "$CTX"
    done
    ;;
  import)
    need k3d
    # shellcheck disable=SC2086
    k3d image import -c "$CLUSTER" $ours
    ;;
  push)
    docker buildx inspect cdc >/dev/null 2>&1 || docker buildx create --name cdc --driver docker-container >/dev/null
    platforms=$(docker buildx inspect --bootstrap cdc | grep -i '^platforms:' || true)
    case "$platforms" in
      *linux/amd64*linux/arm64*|*linux/arm64*linux/amd64*) ;;
      *) die "buildx cannot build both linux/amd64 and linux/arm64; run: docker run --privileged --rm tonistiigi/binfmt --install amd64,arm64" ;;
    esac
    for ref in $ours; do
      name=${ref#ghcr.io/$GHCR_OWNER/}; build_spec "${name%%:*}"
      log "docker buildx build --push $ref (linux/amd64,linux/arm64)"
      # shellcheck disable=SC2086
      docker buildx build --builder cdc --platform linux/amd64,linux/arm64 \
        -t "$ref" -f "$DOCKERFILE" $BUILD_ARGS --push "$CTX"
    done
    ;;
  *) die "usage: images.sh build|import|push" ;;
esac
