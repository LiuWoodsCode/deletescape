import ast
import os
import sys
import sysconfig
import pkgutil
from pathlib import Path

ROOT = Path(".").resolve()

print(f"Scanning Python files in: {ROOT}")
print()

# --- Get stdlib modules ---
stdlib_path = sysconfig.get_paths()["stdlib"]
stdlib_modules = {m.name for m in pkgutil.iter_modules([stdlib_path])}
stdlib_modules.update(sys.builtin_module_names)

# --- Get installed third-party packages ---
installed_packages = {m.name for m in pkgutil.iter_modules()}

# --- Get local project modules ---
local_modules = set()
for py_file in ROOT.rglob("*.py"):
    if py_file.name == "__init__.py":
        continue
    local_modules.add(py_file.stem)

# --- Parse imports safely using AST ---
found_imports = set()

for py_file in ROOT.rglob("*.py"):
    try:
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
    except Exception:
        continue  # skip broken files

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found_imports.add(alias.name.split(".")[0])

        elif isinstance(node, ast.ImportFrom):
            if node.module:
                found_imports.add(node.module.split(".")[0])

print("Modules used in project:")
for mod in sorted(found_imports):
    print(" -", mod)

print()
print("Analyzing dependencies...")
print()

non_builtin = []

for mod in sorted(found_imports):
    if mod in stdlib_modules:
        continue
    if mod in local_modules:
        continue
    non_builtin.append(mod)

if not non_builtin:
    print("All modules appear to be built-in or local.")
else:
    print("Third-party / external modules detected:")
    for mod in non_builtin:
        status = "Installed" if mod in installed_packages else "NOT INSTALLED"
        print(f" - {mod}  ({status})")