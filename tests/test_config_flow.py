"""Tests for the Magnum W Controller config flow."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.config_entries import SOURCE_DHCP, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.magnum_w_controller.api import MagnumApiError
from custom_components.magnum_w_controller.const import CONF_HOST, DOMAIN

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
    """A DHCP discovery is confirmed and creates an entry keyed by MAC."""
    discovery = DhcpServiceInfo(
        ip="1.2.3.4",
        hostname="magnum_w-controller",
        macaddress="aabbccddeeff",
    )

    with patch(_SYSTEM_NAME, return_value="My Magnum"):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_DHCP}, data=discovery
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "discovery_confirm"

        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "My Magnum"
    assert result["data"] == {CONF_HOST: "1.2.3.4"}


async def test_dhcp_discovery_cannot_connect(hass: HomeAssistant) -> None:
    """A discovery that cannot reach the controller aborts."""
    discovery = DhcpServiceInfo(
        ip="1.2.3.4",
        hostname="magnum_w-controller",
        macaddress="aabbccddeeff",
    )

    with patch(_SYSTEM_NAME, side_effect=MagnumApiError("boom")):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_DHCP}, data=discovery
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"
