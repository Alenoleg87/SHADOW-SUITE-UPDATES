"""SHADOW Proxy Runtime V3 — bounded, streaming proxy diagnostics.

A GOOD result proves a working HTTPS request and public exit IP at test time.
It does not guarantee future availability or access to other websites.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from ipaddress import ip_address
from urllib.parse import urlsplit, unquote, quote
import threading
import time
import requests

ENDPOINTS = (
    ("ipify", "https://api64.ipify.org?format=json", "ip"),
    ("httpbin", "https://httpbin.org/ip", "origin"),
)
WORKERS = 5
TIMEOUT_SECONDS = 10


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
        auth = ""
        if self.username:
            auth = f"{quote(self.username, safe='')}:{quote(self.password, safe='')}@"
        host = f"[{self.host}]" if ':' in self.host and not self.host.startswith('[') else self.host
        return f"{scheme}://{auth}{host}:{self.port}"

    def playwright_config(self, scheme):
        # Playwright uses socks5, while requests uses socks5h for proxy-side DNS.
        browser_scheme = "socks5" if scheme == "socks5h" else scheme
        host = f"[{self.host}]" if ':' in self.host and not self.host.startswith('[') else self.host
        config = {"server": f"{browser_scheme}://{host}:{self.port}"}
        if self.username:
            config.update(username=self.username, password=self.password)
        return config


def parse_line(line):
    raw = line.strip()
    if not raw or raw.startswith('#'):
        return None
    if '://' in raw:
        parsed = urlsplit(raw)
        if not parsed.hostname or parsed.port is None:
            raise ValueError('Invalid proxy URL')
        scheme = parsed.scheme.lower()
        if scheme not in ('http', 'https', 'socks5', 'socks5h'):
            raise ValueError('Unsupported proxy protocol')
        return ProxyRecord(parsed.hostname, parsed.port, unquote(parsed.username or ''),
                           unquote(parsed.password or ''), scheme)
    parts = raw.split(':', 3)
    if len(parts) not in (2, 4):
        raise ValueError('Expected HOST:PORT or HOST:PORT:USER:PASS')
    host = parts[0].strip()
    port = int(parts[1])
    if not host or not 1 <= port <= 65535:
        raise ValueError('Invalid host/port')
    return ProxyRecord(host, port, parts[2] if len(parts) == 4 else '',
                       parts[3] if len(parts) == 4 else '')


def _exit_ip(payload, key):
    value = payload.get(key, '')
    # httpbin may return comma-separated forwarded addresses; don't accept ambiguity.
    if not isinstance(value, str) or ',' in value:
        return ''
    try:
        candidate = ip_address(value.strip())
        return str(candidate) if candidate.is_global else ''
    except ValueError:
        return ''


def _error_category(exc):
    if isinstance(exc, requests.exceptions.Timeout):
        return 'TIMEOUT'
    if isinstance(exc, requests.exceptions.ProxyError):
        message = str(exc).lower()
        if any(term in message for term in ('407', 'authentication', 'auth failed')):
            return 'AUTH_FAILED'
        return 'PROXY_ERROR'
    if isinstance(exc, requests.exceptions.SSLError):
        return 'TLS_ERROR'
    if isinstance(exc, requests.exceptions.ConnectionError):
        return 'NETWORK_ERROR'
    if isinstance(exc, requests.exceptions.RequestException):
        return 'HTTP_ERROR'
    return 'CHECK_FAILED'


def verify(proxy, timeout=TIMEOUT_SECONDS, stop_event=None):
    candidates = [proxy.scheme] if proxy.scheme else ['http', 'socks5h', 'https']
    candidates = ['socks5h' if x == 'socks5' else x for x in candidates]
    failures = []
    for scheme in candidates:
        if stop_event is not None and stop_event.is_set():
            break
        address = proxy.requests_url(scheme)
        observations = []
        errors = []
        with requests.Session() as session:
            session.trust_env = False
            session.proxies.update({'http': address, 'https': address})
            for name, url, key in ENDPOINTS:
                if stop_event is not None and stop_event.is_set():
                    break
                # Each endpoint gets a bounded retry only for transient failures.
                for attempt in range(2):
                    start = time.monotonic()
                    try:
                        response = session.get(url, timeout=(timeout, timeout),
                                               allow_redirects=False)
                        if response.status_code == 407:
                            errors.append(f'{name}:AUTH_FAILED')
                            break
                        if response.status_code != 200:
                            errors.append(f'{name}:HTTP_{response.status_code}')
                            break
                        ip = _exit_ip(response.json(), key)
                        if not ip:
                            errors.append(f'{name}:INVALID_EXIT_IP')
                            break
                        observations.append((name, ip, round((time.monotonic()-start)*1000)))
                        break
                    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
                        if attempt == 0:
                            continue
                        errors.append(f'{name}:{_error_category(exc)}')
                    except (requests.exceptions.RequestException, ValueError) as exc:
                        errors.append(f'{name}:{_error_category(exc)}')
                        break
        if observations:
            names = ','.join(o[0] for o in observations)
            ips = list(dict.fromkeys(o[1] for o in observations))
            reason = f'HTTPS exit IP confirmed via {names} ({len(observations)}/2 endpoints)'
            if len(ips) > 1:
                reason += '; rotating/different exit IPs observed'
            if errors:
                reason += '; other checks: ' + ', '.join(errors)
            return {'status': 'GOOD', 'protocol': scheme, 'exit_ip': ips[0],
                    'proxy': proxy, 'reason': reason,
                    'response_ms': min(o[2] for o in observations),
                    'checks_passed': len(observations)}
        failures.append(f'{scheme}: ' + ', '.join(errors or ['NO_RESULT']))
    # No positive proof is not the same as proof that a proxy is dead.
    category = 'AUTH_FAILED' if failures and all('AUTH_FAILED' in f for f in failures) else 'INCONCLUSIVE'
    return {'status': category, 'protocol': '', 'exit_ip': '', 'proxy': proxy,
            'reason': '; '.join(failures) or 'Stopped', 'response_ms': None,
            'checks_passed': 0}


class ProxyRuntime:
    """Emit each final proxy result as soon as its worker completes."""
    def __init__(self, on_result, on_progress=None, max_workers=WORKERS, proxy_pool=None):
        self.on_result = on_result
        self.proxy_pool = proxy_pool
        self.on_progress = on_progress
        self.max_workers = WORKERS  # fixed at five, independent of browser threads
        self.stop_event = threading.Event()

    def stop(self):
        self.stop_event.set()

    def _publish(self, result):
        # Pool receives GOOD before the GUI is notified.
        if (self.proxy_pool is not None and result.get('status') == 'GOOD'
                and result.get('proxy') is not None):
            self.proxy_pool.add_verified(result['proxy'], result['protocol'], result['exit_ip'])
        self.on_result(result)

    def scan(self, lines):
        unique = {}
        initial = []
        for index, line in enumerate(lines, 1):
            try:
                proxy = parse_line(line)
                if proxy is None:
                    continue
                key = (proxy.host.lower(), proxy.port, proxy.username, proxy.password, proxy.scheme)
                if key in unique:
                    initial.append({'status': 'SKIPPED', 'protocol': '', 'exit_ip': '',
                                    'proxy': proxy, 'line': index, 'reason': 'Duplicate in this scan'})
                else:
                    unique[key] = (index, proxy)
            except (ValueError, TypeError):
                initial.append({'status': 'BAD', 'protocol': '', 'exit_ip': '',
                                'proxy': None, 'line': index, 'reason': 'Invalid proxy format'})
        total = len(initial) + len(unique)
        completed = 0
        for result in initial:
            if self.stop_event.is_set():
                return
            self._publish(result)
            completed += 1
            if self.on_progress:
                self.on_progress(completed, total)
        if self.on_progress:
            self.on_progress(completed, total)
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(verify, proxy, TIMEOUT_SECONDS, self.stop_event): (idx, proxy)
                       for idx, proxy in unique.values()}
            for future in as_completed(futures):
                if self.stop_event.is_set():
                    for pending in futures:
                        pending.cancel()
                    break
                index, proxy = futures[future]
                try:
                    result = future.result()
                except Exception as exc:
                    result = {'status': 'INCONCLUSIVE', 'protocol': '', 'exit_ip': '',
                              'proxy': proxy, 'reason': f'Worker error: {type(exc).__name__}'}
                result['line'] = index
                self._publish(result)
                completed += 1
                if self.on_progress:
                    self.on_progress(completed, total)
