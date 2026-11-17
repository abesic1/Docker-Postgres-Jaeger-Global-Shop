"""Step 1 check: specs are valid OpenAPI, and each app serves the same paths and methods as its spec."""
import sys, yaml
from openapi_spec_validator import validate
sys.path.insert(0, "users"); import importlib.util

def load(name):
    spec = importlib.util.spec_from_file_location(name, f"{name}/main.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def shape(paths):
    return {(p.replace("{user_id}", "{userId}").replace("{order_id}", "{orderId}"), m.lower())
            for p, ops in paths.items() for m in ops if m.lower() in ("get","post","put","delete")}

for name in ("users", "orders"):
    spec = yaml.safe_load(open(f"{name}/openapi.yaml")); validate(spec)
    app = load(name).app
    assert shape(spec["paths"]) == shape(app.openapi()["paths"]), name
    print(name, "spec valid and matches the app")
