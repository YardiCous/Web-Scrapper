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

# Sets DOCKERFILE and CTX for an image built here, given "name:tag"; fails for anything
# else (e.g. a teammate's image, which is pulled from the registry instead).
build_spec() {
  local name=${1%%:*}
  CTX="$REPO_DIR"
  case "$name" in
    cdc-collector|cdc-normaliser|cdc-matcher|cdc-scorer|cdc-gateway|cdc-frontend|cdc-storage|cdc-maintenance)
      DOCKERFILE="$REPO_DIR/services/${name#cdc-}/Dockerfile" ;;
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
      docker build -t "$ref" -f "$DOCKERFILE" "$CTX"
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
      docker buildx build --builder cdc --platform linux/amd64,linux/arm64 \
        -t "$ref" -f "$DOCKERFILE" --push "$CTX"
    done
    ;;
  *) die "usage: images.sh build|import|push" ;;
esac
