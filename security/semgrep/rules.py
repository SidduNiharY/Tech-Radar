# Test cases for TechRadar custom Semgrep rules.
# Each rule has at least one ruleid case and one ok case.
# Note: This file is excluded from Ruff linting via pyproject.toml extend-exclude.

import ast
import json
import subprocess
import yaml

# --- 1. tr-no-trust-remote-code ---
# ruleid: tr-no-trust-remote-code
AutoModel.from_pretrained("x", trust_remote_code=True)
# ok: tr-no-trust-remote-code
AutoModel.from_pretrained("x", trust_remote_code=False)

# --- 2. tr-no-torch-load ---
# ruleid: tr-no-torch-load
torch.load(path)
# ok: tr-no-torch-load
safetensors.torch.load_file(path)

# --- 3. tr-no-pickle-load ---
# ruleid: tr-no-pickle-load
pickle.loads(b)
# ok: tr-no-pickle-load
json.loads(b)

# --- 4. tr-no-yaml-load ---
# ruleid: tr-no-yaml-load
yaml.load(s)
# ok: tr-no-yaml-load
yaml.safe_load(s)

# --- 5. tr-no-shell-true ---
# ruleid: tr-no-shell-true
subprocess.run(cmd, shell=True)
# ok: tr-no-shell-true
subprocess.run(["ls"])

# --- 6. tr-no-eval ---
# ruleid: tr-no-eval
eval(x)
# ruleid: tr-no-eval
exec(x)
# ok: tr-no-eval
ast.literal_eval(x)

# --- 7. tr-no-verify-false ---
# ruleid: tr-no-verify-false
httpx.Client(verify=False)
# ok: tr-no-verify-false
httpx.Client()
