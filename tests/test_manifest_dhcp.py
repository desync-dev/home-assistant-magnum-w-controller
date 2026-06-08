"""
Tests for the DHCP discovery matchers declared in ``manifest.json``.

These exercise the matchers the way Home Assistant's ``dhcp`` integration
actually does, so they catch the case the config-flow tests cannot: a matcher
that is syntactically valid yet never fires against a real controller.

The matching logic here mirrors ``homeassistant.components.dhcp`` verbatim
(``async_index_integration_matchers`` + ``DHCPWatcher.async_process_client``):

* a device is described by its lowercase hostname and uppercase, colon-less MAC;
* hostname matchers are bucketed by the pattern's first character and only fire
  when the *device's* hostname shares that first character;
* MAC matchers are bucketed by OUI (first 6 hex chars) and fire on the OUI alone
  - no hostname required;
* within a bucket, a matcher's ``hostname`` pattern (if present) must fnmatch.

We replicate it rather than import it because the real module pulls in
``aiodhcpwatcher`` (a runtime-only dependency absent from the test env).
"""

from __future__ import annotations

import json
import re
from fnmatch import translate
from pathlib import Path

_MANIFEST = (
    Path(__file__).parent.parent
    / "custom_components"
    / "magnum_w_controller"
    / "manifest.json"
)

# The real controller, as reported by a UniFi DHCP lease.
_CONTROLLER_HOSTNAME = "Magnum_W-Controller"
_CONTROLLER_MAC = "00:22:a8:01:0c:5c"  # OUI 00:22:A8 == Ouman Oy


def _dhcp_matchers() -> list[dict]:
    """The ``dhcp`` matcher list from the integration manifest."""
    return json.loads(_MANIFEST.read_text())["dhcp"]


def _fnmatch(name: str, pattern: str) -> bool:
    """fnmatch the way HA's ``_memorized_fnmatch`` does."""
    return bool(re.compile(translate(pattern)).match(name))


def _is_discovered(hostname: str, mac: str) -> bool:
    """Return whether HA would start a discovery flow for this device.

    Faithful port of ``homeassistant.components.dhcp`` matching.
    """
    lowercase_hostname = hostname.lower()
    uppercase_mac = mac.replace(":", "").upper()
    oui = uppercase_mac[:6]
    first_char = lowercase_hostname[0] if lowercase_hostname else ""

    no_oui_matchers: dict[str, list[dict]] = {}
    oui_matchers: dict[str, list[dict]] = {}
    for matcher in _dhcp_matchers():
        if mac_pattern := matcher.get("macaddress"):
            oui_matchers.setdefault(mac_pattern[:6], []).append(matcher)
            continue
        if host_pattern := matcher.get("hostname"):
            no_oui_matchers.setdefault(host_pattern[0].lower(), []).append(matcher)

    for matcher in (
        *no_oui_matchers.get(first_char, ()),
        *oui_matchers.get(oui, ()),
    ):
        host_pattern = matcher.get("hostname")
        if host_pattern is not None and not _fnmatch(lowercase_hostname, host_pattern):
            continue
        return True
    return False


def test_matches_sniffed_dhcp_hostname() -> None:
    """The DHCPWatcher path: a live DHCP packet carries the real hostname."""
    assert _is_discovered(_CONTROLLER_HOSTNAME, _CONTROLLER_MAC)


def test_matches_network_scan_without_hostname() -> None:
    """The always-on NetworkWatcher path provides only ARP data.

    ``aiodiscover`` resolves hostnames via the router's DNS, but the
    controller's hostname contains an underscore - illegal in DNS - so no
    usable record exists and the hostname arrives empty. Discovery must still
    fire off the MAC OUI alone; otherwise it never triggers for anyone whose
    controller has not coincidentally been caught mid-DHCP-handshake.
    """
    assert _is_discovered("", _CONTROLLER_MAC)


def test_ignores_unrelated_device() -> None:
    """A device that is neither the right OUI nor hostname is left alone."""
    assert not _is_discovered("some-laptop", "11:22:33:44:55:66")
