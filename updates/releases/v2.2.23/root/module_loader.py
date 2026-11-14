
"""
SHADOW SUITE PRO — External Module Loader

Loads application modules from the directory
beside the Portable EXE.

Development:
    Uses the project source directory.

Portable:
    Uses the external tools/ and integrations/
    directories beside SHADOW_SUITE_PRO.exe.
"""

import importlib
import sys
from pathlib import Path


class ExternalModuleError(RuntimeError):
    pass


def application_root():
    return Path(__file__).resolve().parent.parent


ROOT = application_root()


def prepare_external_modules():
    """
    Configure external module search paths.

    External folders must exist beside the EXE.
    """

    required = {
        "root": ROOT / "root",
        "tools": ROOT / "tools",
        "integrations": ROOT / "integrations",
    }

    missing = [
        name
        for name, folder in required.items()
        if not folder.is_dir()
    ]

    if missing:
        raise ExternalModuleError(
            "Missing external module folders: "
            + ", ".join(missing)
            + f"\nExpected location: {ROOT}"
        )

    # Ensure external modules take priority over
    # bundled Python packages.
    for root_string in (str(ROOT), str(ROOT / "root")):
        if root_string in sys.path:
            sys.path.remove(root_string)
        sys.path.insert(0, root_string)

    importlib.invalidate_caches()

    return ROOT


def load_external_module(module_name):
    """
    Load an external module by its package name.

    Example:
        load_external_module("tools.checker")
    """

    if not (
        module_name.startswith("tools.")
        or module_name.startswith("integrations.")
        or module_name in {"root.setup_manager", "root.update_manager", "root.github_updater", "root.module_loader"}
    ):
        raise ExternalModuleError(
            f"External module not allowed: {module_name}"
        )

    prepare_external_modules()

    try:
        module = importlib.import_module(module_name)

    except Exception as exc:
        raise ExternalModuleError(
            f"Cannot load {module_name}: {exc}"
        ) from exc

    # Verify the loaded module really came
    # from the external application directory.
    origin = getattr(module, "__file__", None)

    if not origin:
        raise ExternalModuleError(
            f"Module has no source file: {module_name}"
        )

    origin_path = Path(origin).resolve()

    try:
        origin_path.relative_to(ROOT)

    except ValueError as exc:
        raise ExternalModuleError(
            f"Module was loaded outside the "
            f"Portable directory: {origin_path}"
        ) from exc

    return module


def load_checker_window():
    module = load_external_module(
        "tools.checker"
    )

    checker_class = getattr(
        module,
        "CheckerWindow",
        None,
    )

    if checker_class is None:
        raise ExternalModuleError(
            "CheckerWindow class was not found "
            "in tools/checker.py"
        )

    return checker_class
