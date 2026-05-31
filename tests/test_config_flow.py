"""Tests for the Magnum W Controller config flow."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.config_entries import SOURCE_DHCP, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.magnum_w_controller.api import MagnumApiError
from custom_components.magnum_w_controller.config_flow import MagnumConfigFlow
from custom_components.magnum_w_controller.const import CONF_HOST, DOMAIN

_MAC = "aabbccddeeff"


def _dhcp_info(ip: str = "1.2.3.4") -> DhcpServiceInfo:
    """Build a DHCP discovery payload for the test controller."""
    return DhcpServiceInfo(
        ip=ip, hostname="magnum_w-controller", macaddress=_MAC
    )

_SYSTEM_NAME = "custom_components.magnum_w_controller.config_flow.MagnumClient.async_get_system_name"


async def test_user_flow_success(hass: HomeAssistant) -> None:
    """A valid host creates an entry titled with the system name."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    with patch(_SYSTEM_NAME, return_value="My Magnum"):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "1.2.3.4"}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "My Magnum"
    assert result["data"] == {CONF_HOST: "1.2.3.4"}


async def test_user_flow_cannot_connect(hass: HomeAssistant) -> None:
    """A connection failure shows a form error and lets the user retry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    with patch(_SYSTEM_NAME, side_effect=MagnumApiError("boom")):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "1.2.3.4"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    # Recover on a second attempt.
    with patch(_SYSTEM_NAME, return_value="My Magnum"):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "1.2.3.4"}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_already_configured(hass: HomeAssistant) -> None:
    """Adding a host that already exists aborts the flow."""
    MockConfigEntry(
        domain=DOMAIN, data={CONF_HOST: "1.2.3.4"}, unique_id="1.2.3.4"
    ).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    with patch(_SYSTEM_NAME, return_value="My Magnum"):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "1.2.3.4"}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_dhcp_discovery_flow(hass: HomeAssistant) -> None:
    """A DHCP discovery is confirmed and creates an entry keyed by MAC.

    The controller must not be contacted until the user confirms, so the
    discovery step itself does no network I/O.
    """
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_DHCP}, data=_dhcp_info()
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "discovery_confirm"

    with patch(_SYSTEM_NAME, return_value="My Magnum") as get_name:
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        await hass.async_block_till_done()

    # The single network call happens only on confirmation.
    assert get_name.call_count == 1
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "My Magnum"
    assert result["data"] == {CONF_HOST: "1.2.3.4"}
    assert result["result"].unique_id == format_mac(_MAC)


async def test_dhcp_discovery_cannot_connect(hass: HomeAssistant) -> None:
    """A controller unreachable on confirmation shows a form error, not abort."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_DHCP}, data=_dhcp_info()
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "discovery_confirm"

    with patch(_SYSTEM_NAME, side_effect=MagnumApiError("boom")):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    # The user can retry once the controller is reachable again.
    with patch(_SYSTEM_NAME, return_value="My Magnum"):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_dhcp_updates_host_on_ip_change(hass: HomeAssistant) -> None:
    """Re-discovering a known MAC at a new IP updates the entry in place."""
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_HOST: "1.2.3.4"}, unique_id=format_mac(_MAC)
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_DHCP}, data=_dhcp_info(ip="5.6.7.8")
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_HOST] == "5.6.7.8"


async def test_dhcp_adopts_manual_entry(hass: HomeAssistant) -> None:
    """A manually-added controller is re-keyed to the MAC when discovered."""
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_HOST: "1.2.3.4"}, unique_id="1.2.3.4"
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_DHCP}, data=_dhcp_info()
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    # The host-keyed entry now carries the stable MAC identity.
    assert entry.unique_id == format_mac(_MAC)


async def test_dhcp_second_discovery_in_progress(hass: HomeAssistant) -> None:
    """A concurrent discovery for the same MAC aborts as already in progress."""
    first = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_DHCP}, data=_dhcp_info()
    )
    assert first["type"] is FlowResultType.FORM

    second = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_DHCP}, data=_dhcp_info(ip="5.6.7.8")
    )
    assert second["type"] is FlowResultType.ABORT
    assert second["reason"] == "already_in_progress"


def test_is_matching() -> None:
    """is_matching pairs flows that target the same controller host."""
    same_a = MagnumConfigFlow()
    same_a._host = "1.2.3.4"  # noqa: SLF001
    same_b = MagnumConfigFlow()
    same_b._host = "1.2.3.4"  # noqa: SLF001
    other = MagnumConfigFlow()
    other._host = "5.6.7.8"  # noqa: SLF001

    assert same_a.is_matching(same_b)
    assert not same_a.is_matching(other)
