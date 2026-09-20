# -*- coding: utf-8 -*-
"""
XCH1-AI-BOX MCP Server

Expose power control (XCHP HID) and target UART (USB CDC) to AI coding agents.
CMSIS-DAP flash/debug remains via standard tools (pyOCD / OpenOCD / IDE).
"""
from __future__ import annotations

import json
from typing import Optional

from mcp.server.fastmcp import FastMCP

from .serial_io import SerialSession
from . import xchp

mcp = FastMCP(
    "xch1-aibox",
    instructions=(
        "XCH1-AI-BOX USB debug terminal MCP. "
        "Use power_* tools for dual load switches (CH1/CH2). "
        "Use serial_* for target MCU UART via CDC ACM. "
        "Device must be in work/DAP mode (not boot-hold-A MSC upgrade). "
        "Typical flow: device_list → power_connect → power_set → serial_open → "
        "read logs → power_pulse to reset → power_set off when done. "
        "SWD download uses CMSIS-DAP VID:PID 0x0D28:0x0204 with pyOCD/OpenOCD separately."
    ),
)

_pwr: Optional[xchp.XchpClient] = None
_ser = SerialSession()


def _ensure_pwr() -> xchp.XchpClient:
    global _pwr
    if _pwr is None:
        _pwr = xchp.XchpClient()
    return _pwr


def _j(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


@mcp.tool()
def device_list() -> str:
    """List XCH1-AI-BOX XCHP HID interfaces and serial ports (including CDC)."""
    hid_devs = [
        {
            "path": d.path,
            "product": d.product,
            "manufacturer": d.manufacturer,
            "interface": d.interface_number,
            "usage_page": hex(d.usage_page),
            "usage": hex(d.usage),
        }
        for d in xchp.enumerate_xchp()
    ]
    ports = _ser.list_ports()
    cdc_hint = [
        p
        for p in ports
        if (p.get("vid") == xchp.VID and p.get("pid") == xchp.PID)
        or "CMSIS" in (p.get("description") or "").upper()
        or "CHERRY" in (p.get("description") or "").upper()
        or "USB Serial" in (p.get("description") or "")
    ]
    return _j(
        {
            "vid_pid": "0x0D28:0x0204",
            "xchp_hid": hid_devs,
            "serial_ports_all": ports,
            "serial_ports_likely_cdc": cdc_hint,
            "power_connected": _pwr is not None,
            "serial_open": _ser.is_open,
        }
    )


@mcp.tool()
def device_capabilities() -> str:
    """Describe XCH1-AI-BOX capabilities and recommended AI automation workflow."""
    return _j(
        {
            "product": "XCH1-AI-BOX",
            "usb_work_mode": {
                "vid": "0x0D28",
                "pid": "0x0204",
                "cmsis_dap": "SWD download/debug (external tool)",
                "cdc_uart": "Target UART bridge (serial_* tools)",
                "hid_xchp": "Dual power switches (power_* tools)",
            },
            "power_channels": {
                "CH1": "load switch; LED index 5 green=on",
                "CH2": "load switch; LED index 10 green=on",
                "default": "both OFF",
            },
            "uart_bridge_pins": {"TX": "GPIO43", "RX": "GPIO44", "uart": "UART0"},
            "workflow": [
                "1. device_list / power_connect / power_ping",
                "2. power_set(channel=1, on=true) to power target",
                "3. Use pyOCD/OpenOCD on CMSIS-DAP for flash",
                "4. serial_open CDC port, serial_read logs",
                "5. power_pulse(channel=1, off_ms=200) to reset",
                "6. power_set(channel=1, on=false) when finished",
            ],
            "docs": [
                "docs/XCHP-HID-Protocol.md",
            ],
        }
    )


@mcp.tool()
def power_connect(path: Optional[str] = None) -> str:
    """Open XCHP HID power interface. Optional path from device_list."""
    global _pwr
    if _pwr is not None:
        try:
            _pwr.close()
        except Exception:
            pass
        _pwr = None
    _pwr = xchp.XchpClient(path)
    info = _pwr.get_info()
    st = _pwr.get_status()
    pong = _pwr.ping()
    return _j(
        {
            "ok": True,
            "path": _pwr.path,
            "product": _pwr.product,
            "ping": pong,
            "info": info,
            "status": st,
        }
    )


@mcp.tool()
def power_disconnect() -> str:
    """Close XCHP HID handle."""
    global _pwr
    if _pwr is not None:
        _pwr.close()
        _pwr = None
    return _j({"ok": True, "connected": False})


@mcp.tool()
def power_ping() -> str:
    """Ping XCHP protocol (connectivity check)."""
    return _j({"pong": _ensure_pwr().ping()})


@mcp.tool()
def power_info() -> str:
    """Get XCHP protocol version / channel count / feature flags."""
    return _j(_ensure_pwr().get_info())


@mcp.tool()
def power_status() -> str:
    """Read CH1/CH2 on/off status."""
    return _j(_ensure_pwr().get_status())


@mcp.tool()
def power_set(channel: int, on: bool) -> str:
    """Set one power channel. channel=1|2, on=true/false."""
    return _j(_ensure_pwr().set_ch(channel, on))


@mcp.tool()
def power_set_all(ch1: bool, ch2: bool) -> str:
    """Set both power channels at once."""
    return _j(_ensure_pwr().set_all(ch1, ch2))


@mcp.tool()
def power_pulse(channel: int, off_ms: int = 200, on_ms: int = 0) -> str:
    """Power-cycle a channel: OFF -> wait off_ms -> ON. Used for target reset."""
    return _j(_ensure_pwr().pulse(channel, off_ms, on_ms))


@mcp.tool()
def serial_list() -> str:
    """List host serial ports (CDC ACM for target UART appears here)."""
    return _j({"ports": _ser.list_ports()})


@mcp.tool()
def serial_open(port: str, baud: int = 115200) -> str:
    """Open target UART CDC port (from serial_list / device_list)."""
    return _j(_ser.open(port, baud=baud))


@mcp.tool()
def serial_close() -> str:
    """Close target UART session."""
    return _j(_ser.close())


@mcp.tool()
def serial_write_text(text: str) -> str:
    """Write UTF-8 text to target UART."""
    return _j(_ser.write(text.encode("utf-8")))


@mcp.tool()
def serial_write_hex(hex_data: str) -> str:
    """Write raw bytes given as hex string (e.g. '0102ff')."""
    data = bytes.fromhex(hex_data.replace(" ", ""))
    return _j(_ser.write(data))


@mcp.tool()
def serial_read(max_bytes: int = 4096, timeout_s: float = 0.3) -> str:
    """Read available bytes from target UART (hex + text)."""
    return _j(_ser.read(max_bytes=max_bytes, timeout_s=timeout_s))


@mcp.tool()
def dap_guidance() -> str:
    """How to use CMSIS-DAP on this device from AI/automation (external tools)."""
    return _j(
        {
            "vid_pid": "0x0D28:0x0204",
            "note": "MCP does not drive SWD itself; use pyOCD or OpenOCD.",
            "pyocd_example": [
                "pyocd list",
                "pyocd flash -t <target> firmware.elf",
                "pyocd gdbserver -t <target>",
            ],
            "openocd_hint": "interface cmsis-dap; cmsis_dap_vid_pid 0x0d28 0x0204",
            "pins": {"SWDIO": "GPIO1", "SWCLK": "GPIO6", "nRESET": "GPIO4"},
            "recommend_order": [
                "power_set CH on",
                "pyocd flash",
                "serial_read logs",
                "power_pulse if reset needed",
            ],
        }
    )


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
