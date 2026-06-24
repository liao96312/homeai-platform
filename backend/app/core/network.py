from ipaddress import ip_address, ip_network
from urllib.parse import urlsplit


def normalize_proxy_rules(values: list[str] | tuple[str, ...] | None) -> list[str]:
    return [str(value).strip() for value in values or [] if str(value).strip()]


def is_trusted_proxy(remote_host: str, trusted_proxy_ips: list[str] | tuple[str, ...] | None) -> bool:
    if not remote_host or remote_host == "unknown":
        return False
    rules = normalize_proxy_rules(trusted_proxy_ips)
    if not rules:
        return False
    try:
        remote_ip = ip_address(remote_host)
    except ValueError:
        return remote_host in rules

    for rule in rules:
        try:
            if "/" in rule:
                if remote_ip in ip_network(rule, strict=False):
                    return True
            elif remote_ip == ip_address(rule):
                return True
        except ValueError:
            if remote_host == rule:
                return True
    return False


def strip_ip_port(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return value
    if value.startswith("["):
        try:
            parsed = urlsplit(f"tcp://{value}")
            return parsed.hostname or value
        except ValueError:
            return value
    if value.count(":") == 1:
        host, port = value.rsplit(":", 1)
        if host and port.isdigit():
            return host
    return value


def forwarded_client_ip(remote_host: str, forwarded_for: str | None, trusted_proxy_ips: list[str] | tuple[str, ...] | None) -> str:
    if not is_trusted_proxy(remote_host, trusted_proxy_ips):
        return remote_host
    first_hop = strip_ip_port((forwarded_for or "").split(",")[0])
    if not first_hop:
        return remote_host
    try:
        return str(ip_address(first_hop))
    except ValueError:
        return remote_host
