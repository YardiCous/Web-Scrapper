SHELL := /bin/bash

# lite = 1 Kafka broker (fits 8 GB); default = 3 brokers, RF 3 (needs ~12 GB for Docker).
PROFILE ?= lite
OVERLAY ?= local-$(PROFILE)
CLUSTER ?= cdc
# Lowercase GitHub user/org that owns the ghcr.io images.
GHCR_OWNER ?= yardicous
HTTP_PORT ?= 8080
# Python env for the evaluation scripts (they run on this machine, not in the cluster).
VENV ?= .venv
N ?= 1000
RATE ?= 100
ARGS ?=

export PROFILE OVERLAY CLUSTER GHCR_OWNER HTTP_PORT

.PHONY: help up down status smoke deploy images push ttl-refresh load venv graphs experiments \n	exp-broker-kill exp-consumer-kill exp-keda-burst exp-coldstart

help:
	@echo "make up       create or update the local cluster and deploy everything (PROFILE=$(PROFILE))"
	@echo "make down     delete the local cluster"
	@echo "make status   pods, topics and consumer-group lag"
	@echo "make smoke    run the smoke-test Job against the running cluster"
	@echo "make deploy   re-apply manifests only (after editing k8s/)"
	@echo "make images   build our images and import them into k3d"
	@echo "make push     build multi-arch images and push them to ghcr.io/$(GHCR_OWNER)"
	@echo "make ttl-refresh   run the TTL refresh CronJob once, now"
	@echo "make load N=1000 RATE=100   publish N synthetic listings to listings.raw"
	@echo "make experiments   run all four experiments (CSV in eval/results/)"
	@echo "make exp-consumer-kill | exp-keda-burst | exp-coldstart | exp-broker-kill  [ARGS=...]"
	@echo "make graphs   turn eval/results/*.csv into PNGs"

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

ttl-refresh:
	@kubectl -n pipeline create job ttl-refresh-$$(date +%s) --from=cronjob/ttl-refresh

load:
	@python3 eval/load.py --count $(N) --rate $(RATE)

venv: $(VENV)/.installed

$(VENV)/.installed: eval/requirements.txt
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install -q -r eval/requirements.txt
	@touch $@

exp-consumer-kill: venv
	$(VENV)/bin/python eval/exp_consumer_kill.py $(ARGS)

exp-keda-burst: venv
	$(VENV)/bin/python eval/exp_keda_burst.py $(ARGS)

exp-coldstart: venv
	$(VENV)/bin/python eval/exp_knative_coldstart.py $(ARGS)

exp-broker-kill: venv
	$(VENV)/bin/python eval/exp_broker_kill.py $(ARGS)

# Broker kill last: it is the most disruptive.
experiments: exp-consumer-kill exp-keda-burst exp-coldstart exp-broker-kill

graphs: venv
	$(VENV)/bin/python eval/plot.py
