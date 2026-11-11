"""Picks the adapter from SERVICE_NAME, which every slot in infra/k8s/base/pipeline/services.yaml sets."""
import os
import sys

service = os.environ.get("SERVICE_NAME", "")
if service.startswith("collector-"):
    from .collector import run
elif service == "normaliser":
    from .normaliser import run
elif service == "matcher":
    from .matcher import run
else:
    sys.exit(f"SERVICE_NAME must be collector-<store>, normaliser or matcher, not {service!r}")
sys.exit(run())
