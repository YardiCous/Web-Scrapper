SHELL := /bin/bash

# lite = 1 Kafka broker (fits 8 GB); default = 3 brokers, RF 3 (needs ~12 GB for Docker).
PROFILE ?= lite
OVERLAY ?= local-$(PROFILE)
CLUSTER ?= cdc
# Lowercase GitHub user/org that owns the ghcr.io images.
GHCR_OWNER ?= yardicous
HTTP_PORT ?= 8080

export PROFILE OVERLAY CLUSTER GHCR_OWNER HTTP_PORT

.PHONY: help up down status smoke deploy images push

help:
	@echo "make up       create or update the local cluster and deploy everything (PROFILE=$(PROFILE))"
	@echo "make down     delete the local cluster"
	@echo "make status   pods, topics and consumer-group lag"
	@echo "make smoke    run the smoke-test Job against the running cluster"
	@echo "make deploy   re-apply manifests only (after editing k8s/)"
	@echo "make images   build our images and import them into k3d"
	@echo "make push     build multi-arch images and push them to ghcr.io/$(GHCR_OWNER)"

up:
	@bash scripts/up.sh

down:
	@bash scripts/down.sh

status:
	@bash scripts/status.sh

smoke:
	@bash scripts/smoke.sh

deploy:
	@bash scripts/deploy.sh

images:
	@bash scripts/images.sh build
	@bash scripts/images.sh import

push:
	@bash scripts/images.sh push
