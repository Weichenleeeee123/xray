"""Bounded public-page reader. Resolve, validate AND pin every connection/redirect.

No browser cookies, gateway authorization, environment proxies, login or scripts.
Failures are returned as acquisition states, never as absence of company evidence.
"""
import http.client
import ipaddress
import re
import socket
import ssl
import time
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from app.sources.web import redact


class UnsafeURL(ValueError):
    pass


def canonical_url(url: str) -> str:
    try:
        p = urlsplit(url)
        port = p.port
    except (ValueError, TypeError) as exc:
        raise UnsafeURL('invalid_url') from exc
    if (p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password
            or port not in (None, 80, 443) or re.search(r'[\s\\\x00-\x1f]', url)):
        raise UnsafeURL('unsupported_url')
    host = p.hostname.lower().rstrip('.').encode('idna').decode('ascii')
    if host == 'localhost' or host.endswith(('.localhost', '.local', '.internal')):
        raise UnsafeURL('private_host')
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if not public_ip(address):
            raise UnsafeURL('private_address')
    netloc = f'[{host}]' if ':' in host else host
    if port and port != (443 if p.scheme == 'https' else 80):
        netloc += f':{port}'
    # Keep content-bearing query params (app id, article id, version, language...)
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
             if not k.lower().startswith('utm_') and k.lower() not in ('gclid', 'fbclid', 'msclkid')]
    return urlunsplit((p.scheme, netloc, p.path or '/', urlencode(query), ''))


def public_ip(address) -> bool:
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped:
            return public_ip(address.ipv4_mapped)
        # Disallow transition/tunnel ranges rather than trusting embedded IPv4 targets.
        if address.sixtofour or address.teredo or address in ipaddress.ip_network('64:ff9b::/96'):
            return False
    return address.is_global and not (address.is_multicast or address.is_unspecified or address.is_reserved)


def resolve_public(url: str, resolver=socket.getaddrinfo) -> tuple[str, int, str]:
    p = urlsplit(canonical_url(url))
    port = p.port or (443 if p.scheme == 'https' else 80)
    addresses = [entry[4][0] for entry in resolver(p.hostname, port, type=socket.SOCK_STREAM)]
    if not addresses or any(not public_ip(ipaddress.ip_address(a)) for a in addresses):
        raise UnsafeURL('private_dns_answer')
    return p.hostname, port, addresses[0]


def public_text(text: str) -> str:
    text = redact(text)
    text = re.sub(r'(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)', '（个人联系方式略）', text)
    text = re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '（邮箱略）', text)
    return text


class PageHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ignore = 0
        self.parts, self.links, self.meta = [], [], {}
        self.anchor = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ('script', 'style', 'noscript', 'svg'):
            self.ignore += 1
        if tag == 'meta':
            key = attrs.get('property') or attrs.get('name') or ''
            if key in ('article:published_time', 'article:modified_time', 'date', 'publishdate'):
                self.meta[key] = attrs.get('content', '')
        if self.ignore:
            return
        if tag == 'a':
            self.anchor = [attrs.get('href', ''), '']
        if tag in ('p', 'div', 'br', 'li', 'h1', 'h2', 'article', 'section'):
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript', 'svg'):
            self.ignore = max(0, self.ignore - 1)
        if tag == 'a' and self.anchor:
            self.links.append(tuple(self.anchor))
            self.anchor = None

    def handle_data(self, data):
        if not self.ignore:
            self.parts.append(data)
            if self.anchor:
                self.anchor[1] += data


@dataclass
class PageRead:
    url: str
    state: str = 'failed'
    text: str = ''
    links: list[tuple[str, str]] = field(default_factory=list)
    published_at: str | None = None
    updated_at: str | None = None
    reason: str | None = None


def date_value(value: str | None) -> str | None:
    from datetime import date
    match = re.match(r'^(\d{4})[-年./](\d{1,2})[-月./](\d{1,2})', (value or '').strip())
    try:
        return date(*map(int, match.groups())).isoformat() if match else None
    except ValueError:
        return None


class PageReader:
    def __init__(self, *, max_chars=12000, max_bytes=1_000_000, redirects=3,
                 resolver=socket.getaddrinfo, exchange=None):
        self.max_chars, self.max_bytes, self.redirects = max_chars, max_bytes, redirects
        self.resolver = resolver
        self.exchange = exchange or self._exchange  # test seam, receives the already validated IP

    def _exchange(self, url, host, port, address, timeout):
        # HTTPConnection receives a pre-connected socket; it never resolves host again.
        p = urlsplit(url)
        conn = http.client.HTTPConnection(host, port, timeout=timeout)
        deadline = time.monotonic() + timeout
        sock = socket.create_connection((address, port), timeout=timeout)
        try:
            if p.scheme == 'https':
                sock = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
            conn.sock = sock
            conn.request('GET', urlunsplit(('', '', p.path or '/', p.query, '')),
                         headers={'Host': p.netloc, 'User-Agent': 'QierResearch/1.0 (public evidence reader)',
                                  'Accept': 'text/html,application/xhtml+xml,text/plain', 'Accept-Encoding': 'identity'})
            response = conn.getresponse()
            headers = {k.lower(): v for k, v in response.getheaders()}
            if response.status != 200:
                return response.status, headers, b''
            kind = headers.get('content-type', '').lower().split(';')[0]
            if kind not in ('text/html', 'text/plain', 'application/xhtml+xml'):
                return response.status, headers, b''
            chunks, size = [], 0
            while size <= self.max_bytes:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('page deadline')
                sock.settimeout(remaining)
                chunk = response.read1(min(16384, self.max_bytes + 1 - size))
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
            return response.status, headers, b''.join(chunks)
        finally:
            conn.close()
            sock.close()

    def read(self, url: str, *, timeout=8.0) -> PageRead:
        deadline = time.monotonic() + timeout
        current = url
        try:
            for _ in range(self.redirects + 1):
                current = canonical_url(current)
                host, port, address = resolve_public(current, self.resolver)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return PageRead(current, reason='timeout')
                status, headers, body = self.exchange(current, host, port, address, remaining)
                if status in (301, 302, 303, 307, 308):
                    if not headers.get('location'):
                        return PageRead(current, reason='redirect_without_location')
                    current = urljoin(current, headers['location'])
                    continue  # validate and pin again, including same-host redirects
                if status != 200:
                    return PageRead(current, reason=f'http_{status}')
                kind = headers.get('content-type', '').lower().split(';')[0]
                if kind not in ('text/html', 'application/xhtml+xml', 'text/plain'):
                    return PageRead(current, reason='unsupported_content_type')
                if headers.get('content-encoding', 'identity').lower() not in ('identity', ''):
                    return PageRead(current, reason='unsupported_encoding')
                partial = len(body) > self.max_bytes
                charset = re.search(r'charset=["\x27]?([\w-]+)', headers.get('content-type', ''), re.I)
                encoding = charset.group(1) if charset else 'utf-8'
                if not charset:
                    meta = re.search(rb'charset=["\x27]?([\w-]+)', body[:4096], re.I)
                    if meta:
                        encoding = meta.group(1).decode('ascii')
                text = body[:self.max_bytes].decode(encoding, errors='replace')
                if (re.search(r'<input\b[^>]*type\s*=\s*["\x27]?password', text, re.I)
                    or re.search(r'<title>[^<]*(?:验证码|安全验证|captcha|access denied|sign in)', text, re.I)):
                    return PageRead(current, reason='login_or_challenge')
                parser = PageHTML()
                if kind != 'text/plain':
                    parser.feed(text)
                    text = '\n'.join(line.strip() for line in ''.join(parser.parts).splitlines() if line.strip())
                text = public_text(text)
                partial = partial or len(text) > self.max_chars
                text = text[:self.max_chars]
                if not text.strip():
                    return PageRead(current, reason='empty_or_script_only')
                links = [(urljoin(current, href), public_text(label).strip()) for href, label in parser.links
                         if re.search(r'关于|产品|动态|新闻|about|product|news', label, re.I)][:20]
                return PageRead(current, 'partial' if partial else 'full', text, links,
                    date_value(parser.meta.get('article:published_time') or parser.meta.get('publishdate') or parser.meta.get('date')),
                    date_value(parser.meta.get('article:modified_time')), 'size_limit' if partial else None)
            return PageRead(current, reason='redirect_limit')
        except (OSError, ValueError, http.client.HTTPException, UnicodeError, LookupError) as exc:
            return PageRead(url, reason='blocked_url' if isinstance(exc, UnsafeURL) else type(exc).__name__)
