
"""
SHADOW SUITE PRO
Proxy Runtime — Independent HTTPS Diagnostics
"""

from dataclasses import dataclass
from urllib.parse import urlsplit, unquote
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import requests


IP_CHECK_URL = "https://api.ipify.org?format=json"


@dataclass(frozen=True)
class ProxyRecord:
    host: str
    port: int
    username: str = ""
    password: str = ""
    scheme: str = ""

    @property
    def label(self):
        return f"{self.host}:{self.port}"

    def requests_url(self, scheme):
        from urllib.parse import quote

        credentials = ""

        if self.username:
            credentials = (
                quote(self.username, safe="")
                + ":"
                + quote(self.password, safe="")
                + "@"
            )

        return (
            f"{scheme}://{credentials}"
            f"{self.host}:{self.port}"
        )

    def playwright_config(self, scheme):
        config = {
            "server": (
                f"{scheme}://{self.host}:{self.port}"
            )
        }

        if self.username:
            config["username"] = self.username
            config["password"] = self.password

        return config


def parse_line(line):
    raw = line.strip()

    if not raw or raw.startswith("#"):
        return None

    if "://" in raw:
        parsed = urlsplit(raw)

        if not parsed.hostname or not parsed.port:
            raise ValueError("Invalid proxy URL")

        return ProxyRecord(
            host=parsed.hostname,
            port=parsed.port,
            username=unquote(parsed.username or ""),
            password=unquote(parsed.password or ""),
            scheme=parsed.scheme.lower(),
        )

    parts = raw.split(":", 3)

    if len(parts) not in (2, 4):
        raise ValueError(
            "Expected HOST:PORT or HOST:PORT:USER:PASS"
        )

    host = parts[0].strip()
    port = int(parts[1])

    if not host or not 1 <= port <= 65535:
        raise ValueError("Invalid host or port")

    return ProxyRecord(
        host=host,
        port=port,
        username=parts[2] if len(parts) == 4 else "",
        password=parts[3] if len(parts) == 4 else "",
    )


def verify(proxy, timeout=7):
    """
    A GOOD result requires a successful HTTPS request
    and a valid public exit-IP response.

    HTTP 403 from a website is not treated as proof
    that the proxy itself is broken.
    """

    if proxy.scheme:
        candidates = [proxy.scheme]
    else:
        candidates = [
            "http",
            "socks5h",
            "https",
        ]

    failures = []

    for scheme in candidates:
        try:
            address = proxy.requests_url(scheme)

            response = requests.get(
                IP_CHECK_URL,
                proxies={
                    "http": address,
                    "https": address,
                },
                timeout=timeout,
                allow_redirects=False,
            )

            response.raise_for_status()

            exit_ip = response.json().get("ip", "")

            if not exit_ip:
                raise ValueError("Missing exit IP")

            from ipaddress import ip_address
            parsed_ip = ip_address(exit_ip)

            if not parsed_ip.is_global:
                raise ValueError("Non-public exit IP")

            return {
                "status": "GOOD",
                "protocol": scheme,
                "exit_ip": exit_ip,
                "proxy": proxy,
                "reason": "HTTPS verification successful",
            }

        except Exception as exc:
            failures.append(
                f"{scheme}: {type(exc).__name__}"
            )

    return {
        "status": "BAD",
        "protocol": "",
        "exit_ip": "",
        "proxy": proxy,
        "reason": "; ".join(failures),
    }


class ProxyRuntime:
    """
    Emits verification results one by one.

    Each successful proxy is reported immediately,
    without waiting for the entire TXT file to finish.
    """

    def __init__(
        self,
        on_result,
        on_progress=None,
        max_workers=5,
    ):
        self.on_result = on_result
        self.on_progress = on_progress
        self.max_workers = max(1, min(max_workers, 8))
        self.stop_event = threading.Event()

    def stop(self):
        self.stop_event.set()

    def scan(self, lines):
        proxies = []
        invalid = []

        for index, line in enumerate(lines, 1):
            try:
                proxy = parse_line(line)

                if proxy:
                    proxies.append((index, proxy))

            except Exception as exc:
                invalid.append({
                    "status": "BAD",
                    "protocol": "",
                    "exit_ip": "",
                    "proxy": None,
                    "line": index,
                    "reason": f"Invalid format: {exc}",
                })

        for result in invalid:
            if self.stop_event.is_set():
                return

            self.on_result(result)

        total = len(proxies) + len(invalid)
        completed = len(invalid)

        if self.on_progress:
            self.on_progress(completed, total)

        with ThreadPoolExecutor(
            max_workers=self.max_workers
        ) as executor:

            futures = {
                executor.submit(verify, proxy): index
                for index, proxy in proxies
            }

            for future in as_completed(futures):
                if self.stop_event.is_set():
                    executor.shutdown(
                        wait=False,
                        cancel_futures=True,
                    )
                    return

                index = futures[future]

                try:
                    result = future.result()

                except Exception as exc:
                    result = {
                        "status": "BAD",
                        "protocol": "",
                        "exit_ip": "",
                        "proxy": None,
                        "reason": type(exc).__name__,
                    }

                result["line"] = index
                completed += 1

                self.on_result(result)

                if self.on_progress:
                    self.on_progress(completed, total)
