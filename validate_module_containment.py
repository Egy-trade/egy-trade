import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
DESTRUCTIVE = ("clear_data", "eg_cancel_stock_move")
failures = []


def check(label, ok, detail=""):
    print(("PASS" if ok else "FAIL") + ": " + label + ((" :: " + detail) if detail else ""))
    if not ok:
        failures.append(label)


def load_manifest(path):
    return ast.literal_eval(path.read_text(encoding="utf-8"))


check(
    "no repository-root __manifest__.py",
    not (REPO_ROOT / "__manifest__.py").exists(),
)

manifests = sorted(REPO_ROOT.glob("*/__manifest__.py"))
parsed = {}
for path in manifests:
    module = path.parent.name
    try:
        parsed[module] = load_manifest(path)
    except Exception as exc:
        failures.append("manifest parse: " + module)
        print("FAIL: manifest parses via ast.literal_eval :: %s (%s)" % (module, exc))

for module in DESTRUCTIVE:
    manifest = parsed.get(module)
    if manifest is None:
        continue
    check(module + " installable is False", manifest.get("installable", True) is False)
    check(module + " auto_install is False", manifest.get("auto_install", False) is False)

for module, manifest in parsed.items():
    if module in DESTRUCTIVE or manifest.get("installable", True) is not True:
        continue
    deps = [d for d in manifest.get("depends", []) if isinstance(d, str)]
    bad = [d for d in deps if d in DESTRUCTIVE]
    check(
        "no installable dependency on destructive modules",
        not bad,
        ("%s depends on %s" % (module, bad)) if bad else "",
    )

print("%d manifest(s) scanned" % len(parsed))
if failures:
    print("RESULT: FAIL (%d)" % len(failures))
    sys.exit(1)
print("RESULT: PASS")
