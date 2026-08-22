import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
# Modules that must never be installable/auto-installable on UAT builds:
DESTRUCTIVE = ("clear_data", "eg_cancel_stock_move", "deltatech_no_quick_create")
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


def global_relational_field_patches(module_dir):
    """Detect JS assets that include-patch the core legacy relational fields
    to mutate quick_create behavior globally.

    deltatech_no_quick_create used to force ``quick_create`` off onto the
    shared FieldMany2One prototype, removing standard create/name_create
    flows from every backend view; this guard keeps that class of blanket
    mutation out of the repository. Detection is purely structural
    (require + .include + forcing pattern): no content-based exemptions
    exist, so adding explanatory comments cannot bypass it.
    """
    offenders = []
    forcing = re.compile(r"quick_create\s*:\s*false|no_quick_create\s*:\s*true", re.IGNORECASE)
    js_files = sorted((module_dir / "static").rglob("*.js")) if (module_dir / "static").exists() else []
    for js_path in js_files:
        try:
            text = js_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        lowered = text.lower()
        if (
            "relational_fields" in lowered
            and ".include(" in lowered
            and forcing.search(text)
        ):
            offenders.append(
                str(js_path.relative_to(module_dir)).replace("\\", "/"))
    return offenders


patch_offenders = []
for module in sorted(parsed):
    patch_offenders += global_relational_field_patches(REPO_ROOT / module)
check(
    "no global quick_create JS patch on relational fields",
    not patch_offenders,
    ", ".join(patch_offenders),
)

print("%d manifest(s) scanned" % len(parsed))
if failures:
    print("RESULT: FAIL (%d)" % len(failures))
    sys.exit(1)
print("RESULT: PASS")
