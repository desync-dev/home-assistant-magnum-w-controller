"""
Config flow for the Magnum W Controller integration.

Supports two entry points:

* Automatic **DHCP discovery** — the controller presents the DHCP hostname
  ``Magnum_W-Controller`` (see the ``dhcp`` matcher in ``manifest.json``). The
  MAC address from the DHCP lease is used as a stable ``unique_id`` so the
  config entry survives IP changes. Per Home Assistant's discovery rules, the
  discovery step performs no network I/O and never finishes the flow — the
  controller is only contacted once the user confirms.
* Manual setup — the user types the host; the host doubles as the ``unique_id``.

A controller added manually is keyed by its host. When that same controller is
later seen via DHCP, the existing entry is adopted and re-keyed to the MAC, so
both paths converge on one stable identity instead of creating a duplicate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import format_mac

from .api import MagnumApiError, MagnumClient
from .const import CONF_HOST, DOMAIN

if TYPE_CHECKING:
    from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

STEP_USER_SCHEMA = vol.Schema({vol.Required(CONF_HOST): str})


class MagnumConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Magnum W Controller."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow's discovery state."""
        self._host: str | None = None
        self._system_name: str | None = None

    @property
    def host(self) -> str | None:
        """Host of the controller this flow is configuring."""
        return self._host

    def is_matching(self, other_flow: Self) -> bool:
        """Return True if another in-progress flow targets the same controller."""
        return other_flow.host == self._host

    async def _async_get_system_name(self, host: str) -> str:
        """Connect to the controller and return its system name."""
        session = async_get_clientsession(self.hass)
        client = MagnumClient(host, session)
        return await client.async_get_system_name()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle manual setup."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._host = user_input[CONF_HOST].strip()
            self._async_abort_entries_match({CONF_HOST: self._host})
            # The MAC would be a stabler id, but it isn't available here: the
            # controller's API doesn't expose it, and resolving it from the IP
            # via ARP only works on the same L2 segment as Home Assistant -
            # exactly the case where DHCP discovery already fires and re-keys
            # this entry to the MAC (see async_step_dhcp). So manual entries
            # key on the host and converge on the MAC once discovered.
            await self.async_set_unique_id(self._host)
            self._abort_if_unique_id_configured()
            try:
                system_name = await self._async_get_system_name(self._host)
            except MagnumApiError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=system_name, data={CONF_HOST: self._host}
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    async def async_step_dhcp(
        self, discovery_info: DhcpServiceInfo
    ) -> ConfigFlowResult:
        """
        Handle discovery via DHCP.

        No network I/O happens here: the controller is contacted only after the
        user confirms, in ``async_step_discovery_confirm``.
        """
        self._host = discovery_info.ip

        # The MAC is the stable id; update the stored host if the IP changed.
        unique_id = format_mac(discovery_info.macaddress)
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured(updates={CONF_HOST: discovery_info.ip})

        # A controller added manually is keyed by host. Adopt that entry so it
        # picks up the stable MAC unique_id instead of creating a duplicate.
        for entry in self._async_current_entries():
            if entry.data.get(CONF_HOST) == discovery_info.ip:
                self.hass.config_entries.async_update_entry(entry, unique_id=unique_id)
                return self.async_abort(reason="already_configured")

        self.context["title_placeholders"] = {"name": discovery_info.ip}
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm a discovered controller, contacting it only on confirmation."""
        assert self._host is not None  # noqa: S101
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                self._system_name = await self._async_get_system_name(self._host)
            except MagnumApiError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=self._system_name or "Magnum W Controller",
                    data={CONF_HOST: self._host},
                )

        return self.async_show_form(
            step_id="discovery_confirm",
            description_placeholders={"host": self._host},
            errors=errors,
        )
