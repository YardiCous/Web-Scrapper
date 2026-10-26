# Serves one dummy store at a pinned commit. scripts/images.sh passes SITE_REPO and SITE_REF
# (the image tag in k8s/base/kustomization.yaml).
FROM nginx:1.30.6-alpine
ARG SITE_REPO
ARG SITE_REF
ADD ${SITE_REPO}.git#${SITE_REF} /usr/share/nginx/html/
RUN cd /usr/share/nginx/html && rm -rf .github scripts tests README.md .gitignore
