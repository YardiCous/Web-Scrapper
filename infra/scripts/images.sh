#!/usr/bin/env bash
# build | import | push for the images this repo builds. Image refs and tags are read from the
# rendered manifests, so k8s/base/kustomization.yaml is the only place a tag is set.
. "$(dirname "$0")/lib.sh"
need docker kubectl
cmd=${1:?usage: images.sh build|import|push}
REPO_DIR=$(cd "$INFRA_DIR/.." && pwd)

refs() {
  render | grep -Eo "ghcr.io/$GHCR_OWNER/[a-z0-9-]+:[A-Za-z0-9._-]+" | sort -u
}

# Sets DOCKERFILE, CTX and BUILD_ARGS for an image built here, given "name:tag"; fails for anything
# else (e.g. a teammate's image, which is pulled from the registry instead).
# Store images are tagged with the full commit SHA of the site repo they serve.
build_spec() {
  local name=${1%%:*} tag=${1#*:}
  DOCKERFILE="$INFRA_DIR/images/tools/Dockerfile"; CTX="$INFRA_DIR"; BUILD_ARGS=""
  case "$name" in
    cdc-tools) BUILD_ARGS="--target tools" ;;
    cdc-placeholder) BUILD_ARGS="--target placeholder" ;;
    # The team's code, from the rest of this repository.
    scorer) DOCKERFILE="$REPO_DIR/scorer/Dockerfile"; CTX="$REPO_DIR/scorer" ;;
    cdc-adapters) DOCKERFILE="$REPO_DIR/adapters/Dockerfile"; CTX="$REPO_DIR" ;;
    store-a|store-b|store-c)
      case "$name" in
        store-a) repo=https://github.com/Paegnium/dummysite ;;
        store-b) repo=https://github.com/Paegnium/dummysite2 ;;
        store-c) repo=https://github.com/Paegnium/dummysite3 ;;
      esac
      DOCKERFILE="$INFRA_DIR/images/site/Dockerfile"; CTX="$INFRA_DIR/images/site"
      BUILD_ARGS="--build-arg SITE_REPO=$repo --build-arg SITE_REF=$tag" ;;
    *) return 1 ;;
  esac
}

ours=""
for ref in $(refs); do
  if build_spec "${ref#ghcr.io/$GHCR_OWNER/}"; then ours="$ours $ref"; fi
done
[ -n "$ours" ] || die "no buildable images referenced by overlay $OVERLAY"

case "$cmd" in
  build)
    for ref in $ours; do
      build_spec "${ref#ghcr.io/$GHCR_OWNER/}"
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
      build_spec "${ref#ghcr.io/$GHCR_OWNER/}"
      log "docker buildx build --push $ref (linux/amd64,linux/arm64)"
      # shellcheck disable=SC2086
      docker buildx build --builder cdc --platform linux/amd64,linux/arm64 \
        -t "$ref" -f "$DOCKERFILE" $BUILD_ARGS --push "$CTX"
    done
    ;;
  *) die "usage: images.sh build|import|push" ;;
esac
