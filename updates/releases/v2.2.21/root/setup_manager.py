"""
SHADOW SUITE PRO — Setup Manager
Windows / Firefox & Camoufox / Automatic Dependency Repair

Compatible with the existing main.py:
    SetupWorker(install=False, parent=None)
    progress(int, str, str)
    done(bool, str, bool)
    configure_portable_browser()
    install_firefox_in_frozen_app()
"""

import importlib
import importlib.util
import logging
import os
import platform
import re
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.request

from pathlib import Path
from logging.handlers import RotatingFileHandler

from PySide6.QtCore import QThread, Signal


REQUIRED_PACKAGES = {
    "openpyxl": "openpyxl>=3.1,<4",
    "playwright": "playwright>=1.50,<2",
    "requests": "requests>=2.31,<3",
    "camoufox": "camoufox>=0.4",
}

MICROSOFT_VC_URL = (
    "https://aka.ms/vs/17/release/vc_redist.x64.exe"
)

VC_RUNTIME_DLLS = {
    "msvcp140.dll",
    "msvcp140_1.dll",
    "msvcp140_2.dll",
    "vcruntime140.dll",
    "vcruntime140_1.dll",
    "concrt140.dll",
    "vccorlib140.dll",
}

MAX_DOWNLOAD_SIZE = 80 * 1024 * 1024


def portable_root():
    return Path(__file__).resolve().parent.parent


ROOT = portable_root()

LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("SHADOW_SETUP")
logger.setLevel(logging.INFO)

if not logger.handlers:
    handler = RotatingFileHandler(
        LOG_DIR / "setup.log",
        maxBytes=2_000_000,
        backupCount=3,
        encoding="utf-8",
    )

    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)s | %(message)s"
        )
    )

    logger.addHandler(handler)


def configure_portable_temp():
    candidates = [
        ROOT / "temp",
        Path(tempfile.gettempdir()) / "shadow_suite_pro",
    ]
    failures = []
    for directory in candidates:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=directory, prefix="probe_", delete=True):
                pass
            os.environ["TEMP"] = str(directory)
            os.environ["TMP"] = str(directory)
            tempfile.tempdir = str(directory)
            logger.info("Portable TEMP/TMP configured: %s", directory)
            return directory
        except OSError as exc:
            failures.append(f"{directory}: {exc}")
    raise RuntimeError("No writable temporary directory: " + "; ".join(failures))


def configure_portable_browser():
    browser_dir = ROOT / "browsers"
    browser_dir.mkdir(parents=True, exist_ok=True)
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browser_dir)
    return browser_dir


def missing_python_packages():
    missing = []
    for module, package in REQUIRED_PACKAGES.items():
        try:
            if importlib.util.find_spec(module) is None:
                missing.append(package)
        except (ImportError, ValueError):
            missing.append(package)
    return missing


def test_camoufox_browser(timeout_ms=45000):
    """
    Launch Camoufox smoke test to confirm binaries and anti-bot hooks are working.
    """
    from camoufox.sync_api import Camoufox

    with Camoufox(headless=True) as browser:
        page = browser.new_page()
        page.goto("about:blank", timeout=15000)
        if page.url != "about:blank":
            raise RuntimeError("Camoufox browser smoke test failed.")


def test_firefox(timeout_ms=45000):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.firefox.launch(
            headless=True,
            timeout=timeout_ms,
        )
        try:
            page = browser.new_page()
            page.goto("about:blank", timeout=15000)
            if page.url != "about:blank":
                raise RuntimeError("Firefox smoke test failed.")
        finally:
            browser.close()


def verify_browsers_with_retry():
    launch_timeouts_ms = (45000, 60000)
    for attempt, timeout_ms in enumerate(launch_timeouts_ms, start=1):
        logger.info("Browser smoke test attempt %s/%s", attempt, len(launch_timeouts_ms))
        try:
            test_firefox(timeout_ms=timeout_ms)
            test_camoufox_browser(timeout_ms=timeout_ms)
            return
        except Exception as exc:
            message = str(exc).lower()
            timed_out = (
                "timeout" in type(exc).__name__.lower()
                or "timeout" in message
                or "timed out" in message
            )
            if not timed_out or attempt == len(launch_timeouts_ms):
                raise
            logger.warning(
                "Browser startup timed out on attempt %s; retrying in 2 seconds. Error: %s",
                attempt, exc,
            )
            time.sleep(2)


def missing_dlls_from_error(error_text):
    match = re.search(
        r"Full list of missing libraries:\s*(.*?)(?:\n\s*\n|$)",
        error_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return []
    names = re.findall(
        r"\b[a-zA-Z0-9_-]+\.dll\b",
        match.group(1),
        flags=re.IGNORECASE,
    )
    return sorted(set(name.lower() for name in names))


def powershell_path():
    system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    return str(system_root / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe")


def verify_microsoft_signature(file_path):
    path = str(file_path).replace("'", "''")
    script = (
        f"$s=Get-AuthenticodeSignature -LiteralPath '{path}';"
        "if ($s.Status -ne 'Valid') { exit 2 };"
        "if ($null -eq $s.SignerCertificate) { exit 3 };"
        "if ($s.SignerCertificate.Subject "
        "-notmatch '(^|,\\s*)O=Microsoft Corporation(,|$)') "
        "{ exit 4 };"
        "exit 0"
    )
    result = subprocess.run(
        [
            powershell_path(),
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        timeout=45,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode != 0:
        raise RuntimeError("Microsoft installer signature verification failed.")


def install_firefox_in_frozen_app():
    configure_portable_temp()
    configure_portable_browser()
    from playwright.__main__ import main as playwright_main
    sys.argv = ["playwright", "install", "firefox"]
    playwright_main()


class SetupWorker(QThread):

    progress = Signal(int, str, str)
    done = Signal(bool, str, bool)

    def __init__(self, install=False, parent=None):
        super().__init__(parent)
        self.install = install

    def report(self, percent, title, detail):
        logger.info("%s%% | %s | %s", percent, title, detail)
        self.progress.emit(percent, title, detail)

    def fail(self, message, repairable=False):
        logger.error(message)
        self.done.emit(False, message, repairable)

    def run_process(self, command, title, percent):
        self.report(percent, title, "Running installer...")
        configure_portable_temp()
        configure_portable_browser()
        child_env = os.environ.copy()
        result = subprocess.run(
            command,
            env=child_env,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=900,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        output = (result.stdout + "\n" + result.stderr).strip()
        if output:
            logger.info("%s output:\n%s", title, output[-5000:])
        if result.returncode != 0:
            raise RuntimeError(f"{title} failed (exit code {result.returncode}). {output[-300:]}")

    def install_packages(self, missing):
        runtime_python = ROOT / "runtime" / "python.exe"
        python = str(runtime_python if runtime_python.is_file() else Path(sys.executable))
        self.run_process(
            [python, "-m", "pip", "install", "--disable-pip-version-check", "--no-input", *missing],
            "Installing missing Python packages (including Camoufox)", 20,
        )
        importlib.invalidate_caches()

    def install_browsers(self):
        runtime_python = ROOT / "runtime" / "python.exe"
        python = str(runtime_python if runtime_python.is_file() else Path(sys.executable))

        # 1. Install Playwright standard Firefox
        self.report(50, "Installing Playwright Firefox...", "Downloading Firefox browser binaries...")
        self.run_process(
            [python, "-m", "playwright", "install", "firefox"],
            "Installing Playwright Firefox", 55,
        )

        # 2. Fetch Camoufox browser binaries
        self.report(65, "Installing Camoufox Engine...", "Downloading anti-detection Camoufox binaries...")
        self.run_process(
            [python, "-m", "camoufox", "fetch"],
            "Fetching Camoufox Binaries", 75,
        )

    def download_vc_runtime(self, destination):
        self.report(45, "Downloading Windows runtime...", "Downloading official Microsoft installer...")
        request = urllib.request.Request(
            MICROSOFT_VC_URL,
            headers={"User-Agent": "SHADOW-SUITE-Setup/1.0"},
        )
        with urllib.request.urlopen(request, timeout=45) as response:
            final_url = response.geturl()
            if not final_url.startswith("https://"):
                raise RuntimeError("Installer download did not use HTTPS.")
            downloaded = 0
            with open(destination, "wb") as output:
                while True:
                    chunk = response.read(1024 * 256)
                    if not chunk:
                        break
                    downloaded += len(chunk)
                    if downloaded > MAX_DOWNLOAD_SIZE:
                        raise RuntimeError("Installer download exceeded the allowed size.")
                    output.write(chunk)
        if downloaded < 100_000:
            raise RuntimeError("Microsoft installer download is incomplete.")
        self.report(55, "Verifying installer...", "Checking Microsoft's digital signature...")
        verify_microsoft_signature(destination)

    def repair_windows_runtime(self):
        if sys.platform != "win32":
            raise RuntimeError("This repair requires Windows.")
        if platform.machine().lower() not in ("amd64", "x86_64"):
            raise RuntimeError("This installer supports Windows x64 only.")

        configure_portable_temp()
        with tempfile.TemporaryDirectory(prefix="shadow_setup_") as directory:
            installer = Path(directory) / "vc_redist.x64.exe"
            self.download_vc_runtime(installer)
            self.report(65, "Repairing Windows runtime...", "Windows may request administrator approval...")
            path = str(installer).replace("'", "''")
            script = (
                f"$p=Start-Process -FilePath '{path}' "
                "-ArgumentList '/repair /quiet /norestart' "
                "-Verb RunAs -Wait -PassThru -ErrorAction Stop;"
                "exit $p.ExitCode"
            )
            result = subprocess.run(
                [
                    powershell_path(),
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    script,
                ],
                capture_output=True,
                text=True,
                timeout=900,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode not in (0, 3010):
                logger.warning("Repair returned %s; trying install.", result.returncode)
                script = (
                    f"$p=Start-Process -FilePath '{path}' "
                    "-ArgumentList '/install /quiet /norestart' "
                    "-Verb RunAs -Wait -PassThru -ErrorAction Stop;"
                    "exit $p.ExitCode"
                )
                result = subprocess.run(
                    [
                        powershell_path(),
                        "-NoProfile",
                        "-NonInteractive",
                        "-ExecutionPolicy",
                        "Bypass",
                        "-Command",
                        script,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=900,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            if result.returncode not in (0, 3010):
                raise RuntimeError(f"Microsoft Visual C++ repair failed (code {result.returncode}).")
            if result.returncode == 3010:
                raise RuntimeError("Microsoft Visual C++ was installed. Restart Windows, then click Recheck.")

        self.report(80, "Windows runtime repaired", "Rechecking browsers...")

    def run(self):
        try:
            logger.info("=" * 55)
            logger.info("SHADOW SUITE PRO — Setup started")
            logger.info("Windows: %s", platform.platform())
            logger.info("Python: %s", sys.version)

            self.report(5, "Checking requirements...", "Checking Python packages...")
            if sys.version_info < (3, 10):
                self.fail("Python 3.10 or newer is required.")
                return

            self.report(10, "Preparing environment...", "Repairing portable TEMP/TMP paths...")
            configure_portable_temp()
            configure_portable_browser()
            missing = missing_python_packages()

            if missing:
                if not self.install:
                    self.fail("Missing Python packages: " + ", ".join(missing), True)
                    return
                self.install_packages(missing)
                if missing_python_packages():
                    self.fail("Python packages are still missing.")
                    return

            self.report(35, "Checking browsers...", "Verifying Playwright Firefox & Camoufox...")
            need_browser_install = False

            try:
                from playwright.sync_api import sync_playwright
                with sync_playwright() as playwright:
                    if not Path(playwright.firefox.executable_path).is_file():
                        need_browser_install = True
            except Exception:
                need_browser_install = True

            try:
                import camoufox
            except ImportError:
                need_browser_install = True

            if need_browser_install:
                if not self.install:
                    self.fail("Firefox or Camoufox binaries missing. Click Install Now.", True)
                    return
                self.install_browsers()

            self.report(85, "Verifying browsers...", "Launching Firefox and Camoufox test...")
            try:
                verify_browsers_with_retry()
            except Exception as exc:
                error_text = str(exc)
                logger.error("Browser launch failure:\n%s", traceback.format_exc())
                missing_dlls = missing_dlls_from_error(error_text)

                vc_missing = [name for name in missing_dlls if name in VC_RUNTIME_DLLS]
                unknown = [name for name in missing_dlls if name not in VC_RUNTIME_DLLS]

                if unknown:
                    self.fail("Browser requires additional Windows libraries: " + ", ".join(unknown), False)
                    return

                if vc_missing:
                    if not self.install:
                        self.fail("Missing Microsoft Visual C++ libraries: " + ", ".join(vc_missing), True)
                        return
                    self.repair_windows_runtime()
                    verify_browsers_with_retry()
                else:
                    self.fail(f"Browser launch failed: {error_text[:200]}", False)
                    return

            self.report(100, "System Ready", "All browsers and Camoufox engines ready.")
            self.done.emit(True, "All requirements and Camoufox are installed and verified.", False)

        except Exception as exc:
            logger.error("Setup failed:\n%s", traceback.format_exc())
            self.fail(f"Setup failed: {str(exc)[:260]} Details: logs/setup.log", False)