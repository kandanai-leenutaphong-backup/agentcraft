"""Where a request is allowed to go, decided before a credential is fetched.

WHY THIS IS A MODULE AND NOT AN `if` IN THE TRANSPORT
-----------------------------------------------------
A bearer token is a credential that any host it is sent to can replay. So the
question "may this URL receive a token" has to be answered *before* the token
is obtained, for **every** send, including the second page of a list, including
whatever a server put in ``nextLink``, and including anywhere an HTTP redirect
would like to go. An audit of this package found the opposite: paging followed
an absolute URL from the response body and the transport attached
``Authorization`` unconditionally, so one hostile list body exfiltrated a live
ARM token.

The rule here is deliberately blunt and structural:

* the scheme must be ``https``;
* the URL must carry no userinfo (``https://management.azure.com@evil/``),
  no fragment, and no embedded credentials;
* the host must be in an allowlist that came from *configuration*, never from
  a response body;
* a continuation URL must be same-origin with the request that produced it.

SOVEREIGN CLOUDS ARE CONFIGURATION, NOT A GLOBAL
------------------------------------------------
US Government, China (21Vianet) and Germany run different ARM, Graph and Kusto
hostnames. Hardcoding one public-cloud host and calling it a security boundary
means the boundary is wrong everywhere else and gets disabled. So a caller
picks a :class:`CloudEndpoints` — or builds one — and every transport and
provider is bound to it at construction.

DEPENDENCIES
------------
Standard library only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlsplit

from azaccess.errors import AuthorizationRefused, CoordinateError


@dataclass(frozen=True)
class CloudEndpoints:
    """One Azure environment's hostnames and token audiences.

    ``arm_audience`` and ``graph_audience`` are the resource the token is
    minted for. They are here, next to the hosts, because an audience that does
    not correspond to the host being called is the single most common cause of
    a 401 that reads like a missing permission — and because binding the two
    together is what makes "this transport may not call Graph" enforceable.
    """

    name: str
    arm_host: str
    graph_host: str
    arm_audience: str
    graph_audience: str
    #: Extra hosts a caller deliberately permits (a Kusto cluster's own
    #: hostname, a sovereign clone). Named individually, never wildcarded.
    extra_hosts: tuple[str, ...] = ()

    @property
    def arm_endpoint(self) -> str:
        return f"https://{self.arm_host}"

    @property
    def graph_endpoint(self) -> str:
        return f"https://{self.graph_host}"

    def hosts(self) -> frozenset[str]:
        return frozenset(
            h.lower() for h in (self.arm_host, self.graph_host, *self.extra_hosts) if h
        )

    def audience_for_host(self, host: str) -> str:
        lowered = str(host or "").lower()
        if lowered == self.arm_host.lower():
            return self.arm_audience
        if lowered == self.graph_host.lower():
            return self.graph_audience
        raise CoordinateError(
            f"no token audience is configured for host {lowered!r} in cloud "
            f"'{self.name}'; add it to the endpoints explicitly"
        )

    def with_hosts(self, *hosts: str) -> "CloudEndpoints":
        return CloudEndpoints(
            name=self.name,
            arm_host=self.arm_host,
            graph_host=self.graph_host,
            arm_audience=self.arm_audience,
            graph_audience=self.graph_audience,
            extra_hosts=tuple(dict.fromkeys(self.extra_hosts + hosts)),
        )


AZURE_PUBLIC_CLOUD = CloudEndpoints(
    name="AzureCloud",
    arm_host="management.azure.com",
    graph_host="graph.microsoft.com",
    arm_audience="https://management.azure.com/.default",
    graph_audience="https://graph.microsoft.com/.default",
)

AZURE_US_GOVERNMENT = CloudEndpoints(
    name="AzureUSGovernment",
    arm_host="management.usgovcloudapi.net",
    graph_host="graph.microsoft.us",
    arm_audience="https://management.usgovcloudapi.net/.default",
    graph_audience="https://graph.microsoft.us/.default",
)

AZURE_CHINA_CLOUD = CloudEndpoints(
    name="AzureChinaCloud",
    arm_host="management.chinacloudapi.cn",
    graph_host="microsoftgraph.chinacloudapi.cn",
    arm_audience="https://management.chinacloudapi.cn/.default",
    graph_audience="https://microsoftgraph.chinacloudapi.cn/.default",
)

#: Every cloud this package ships coordinates for, by name.
KNOWN_CLOUDS: dict[str, CloudEndpoints] = {
    c.name.lower(): c
    for c in (AZURE_PUBLIC_CLOUD, AZURE_US_GOVERNMENT, AZURE_CHINA_CLOUD)
}


def cloud_by_name(name: str) -> CloudEndpoints:
    try:
        return KNOWN_CLOUDS[str(name or "").strip().lower()]
    except KeyError:
        raise CoordinateError(
            f"'{name}' is not a configured cloud; expected one of "
            f"{sorted(KNOWN_CLOUDS)} or a CloudEndpoints built by the caller"
        ) from None


def origin_of(url: str) -> str:
    """``https://host[:port]`` for a URL that passed the structural checks.

    Raises rather than returning something lenient: an origin computed from a
    URL nobody validated is a comparison that always succeeds against itself.
    """
    parts = urlsplit(str(url or ""))
    if parts.scheme.lower() != "https":
        raise AuthorizationRefused(
            f"refusing a non-https URL: scheme {parts.scheme or '(none)'!r}"
        )
    if parts.username or parts.password or "@" in parts.netloc:
        raise AuthorizationRefused(
            "refusing a URL carrying userinfo; 'https://trusted@attacker/' "
            "reads as trusted and is not"
        )
    if not parts.hostname:
        raise AuthorizationRefused("refusing a URL with no host")
    port = f":{parts.port}" if parts.port else ""
    return f"https://{parts.hostname.lower()}{port}"


def _structural_checks(url: str, what: str) -> None:
    """Everything that is wrong with a URL regardless of which host it names."""
    text = str(url or "")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in text):
        raise AuthorizationRefused(f"{what}: URL contains control characters")
    if urlsplit(text).fragment:
        raise AuthorizationRefused(
            f"{what}: URL carries a fragment, which never reaches a server and "
            f"is only ever there to confuse a host check"
        )


def require_trusted_url(url: str, allowed_hosts: Iterable[str], *, what: str) -> str:
    """Refuse before a credential exists, or return the URL unchanged.

    ``allowed_hosts`` comes from configuration. Nothing derived from a response
    body is ever passed here as an allowlist entry — that would make the
    attacker's URL its own authorisation.
    """
    text = str(url or "")
    _structural_checks(text, what)
    origin = origin_of(text)
    host = origin.split("://", 1)[1].split(":", 1)[0]
    permitted = {h.lower() for h in allowed_hosts}
    if host not in permitted:
        raise AuthorizationRefused(
            f"{what}: host {host!r} is not in the configured endpoint allowlist "
            f"({sorted(permitted)}); refusing before any token is obtained"
        )
    return text


def require_same_origin(url: str, expected_origin: str, *, what: str) -> str:
    """A continuation must stay on the origin that produced it.

    The structural checks run here too. Origin equality alone let a fragment
    through, and a fragment is only ever present to make a host comparison read
    the wrong half of a URL.
    """
    _structural_checks(url, what)
    actual = origin_of(url)
    if actual.lower() != str(expected_origin or "").lower():
        raise AuthorizationRefused(
            f"{what}: continuation points at {actual}, not {expected_origin}; "
            f"refusing to carry a token off-origin"
        )
    return url


__all__ = [
    "AZURE_CHINA_CLOUD",
    "AZURE_PUBLIC_CLOUD",
    "AZURE_US_GOVERNMENT",
    "CloudEndpoints",
    "KNOWN_CLOUDS",
    "cloud_by_name",
    "origin_of",
    "require_same_origin",
    "require_trusted_url",
]
