# -*- coding: utf-8 -*-
"""XCHP HID client for XCH1-AI-BOX (VID:PID 0x0D28:0x0204)."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Optional

import hid

VID = 0x0D28
PID = 0x0204
PACKET = 64
REPORT_OUT = 0x01
REPORT_IN = 0x02
VER = 0x01
MAGIC = bytes([0x58, 0x43, 0x48, 0x50])  # XCHP

CMD_PING = 0x00
CMD_GET_STATUS = 0x01
CMD_SET_CH = 0x02
CMD_SET_ALL = 0x03
CMD_PULSE = 0x04
CMD_GET_INFO = 0x05

ST_OK = 0x00
ST_NAMES = {
    0x00: "OK",
    0x01: "BAD_MAGIC",
    0x02: "BAD_VER",
    0x03: "BAD_CMD",
    0x04: "BAD_PARAM",
    0x05: "BUSY",
}


def _path_str(path: Any) -> str:
    if isinstance(path, (bytes, bytearray)):
        return path.decode("utf-8", errors="replace")
    return str(path)


@dataclass
class XchpDeviceInfo:
    path: str
    path_raw: Any
    product: str
    manufacturer: str
    interface_number: int
    usage_page: int
    usage: int


def enumerate_xchp() -> list[XchpDeviceInfo]:
    out: list[XchpDeviceInfo] = []
    for d in hid.enumerate(VID, PID):
        usage_page = int(d.get("usage_page") or 0)
        path_raw = d.get("path")
        if not path_raw:
            continue
        out.append(
            XchpDeviceInfo(
                path=_path_str(path_raw),
                path_raw=path_raw,
                product=str(d.get("product_string") or "XCH1-AI-BOX"),
                manufacturer=str(d.get("manufacturer_string") or ""),
                interface_number=int(d.get("interface_number") or -1),
                usage_page=usage_page,
                usage=int(d.get("usage") or 0),
            )
        )
    out.sort(key=lambda x: (0 if x.usage_page == 0xFF00 else 1, x.interface_number))
    return out


class XchpClient:
    def __init__(self, path: Optional[str] = None):
        self._lock = threading.Lock()
        self._seq = 0
        devices = enumerate_xchp()
        if not devices:
            raise RuntimeError(
                "No XCHP HID found (VID=0x0D28 PID=0x0204). "
                "Ensure device is in DAP/work mode (not MSC upgrade)."
            )
        target: Optional[XchpDeviceInfo] = None
        if path:
            for d in devices:
                if d.path == path:
                    target = d
                    break
            if target is None:
                raise RuntimeError(f"Device path not found: {path}")
        else:
            target = next((d for d in devices if d.usage_page == 0xFF00), devices[0])

        self.path = target.path
        self.product = target.product
        self._dev = hid.device()
        self._dev.open_path(target.path_raw)
        self._dev.set_nonblocking(False)

    def close(self) -> None:
        with self._lock:
            try:
                self._dev.close()
            except Exception:
                pass

    def transfer(self, cmd: int, payload: bytes = b"", timeout_ms: int = 2000) -> tuple[int, bytes]:
        if len(payload) > 54:
            raise ValueError("payload max 54 bytes")
        with self._lock:
            self._seq = (self._seq + 1) & 0xFF
            if self._seq == 0:
                self._seq = 1
            seq = self._seq
            pkt = bytearray(PACKET)
            pkt[0] = REPORT_OUT
            pkt[1:5] = MAGIC
            pkt[5] = VER
            pkt[6] = cmd & 0xFF
            pkt[7] = seq
            pkt[8] = len(payload)
            pkt[9 : 9 + len(payload)] = payload
            self._dev.write(bytes(pkt))

            deadline = time.time() + timeout_ms / 1000.0
            while time.time() < deadline:
                remain = max(1, int((deadline - time.time()) * 1000))
                data = self._dev.read(PACKET, timeout_ms=min(200, remain))
                if not data:
                    continue
                buf = bytes(data)
                if len(buf) < 10:
                    continue
                if buf[0] != REPORT_IN and len(buf) >= PACKET - 1:
                    buf = bytes([REPORT_IN]) + buf
                if buf[0] != REPORT_IN or buf[1:5] != MAGIC:
                    continue
                if buf[7] not in (seq, 0):
                    continue
                status = buf[8]
                plen = buf[9]
                payload_out = buf[10 : 10 + plen] if plen else b""
                if status != ST_OK:
                    name = ST_NAMES.get(status, f"0x{status:02X}")
                    raise RuntimeError(f"XCHP status {name} (0x{status:02X})")
                return status, payload_out
            raise TimeoutError(f"XCHP cmd 0x{cmd:02X} timeout")

    def ping(self) -> str:
        _, p = self.transfer(CMD_PING)
        return p.decode("ascii", errors="replace")

    def get_status(self) -> dict:
        _, p = self.transfer(CMD_GET_STATUS)
        if len(p) < 2:
            raise RuntimeError("GET_STATUS short payload")
        return {"ch1": bool(p[0]), "ch2": bool(p[1])}

    def set_ch(self, ch: int, on: bool) -> dict:
        if ch not in (1, 2):
            raise ValueError("ch must be 1 or 2")
        _, p = self.transfer(CMD_SET_CH, bytes([ch, 1 if on else 0]))
        return {"ch1": bool(p[0]), "ch2": bool(p[1])}

    def set_all(self, ch1: bool, ch2: bool) -> dict:
        _, p = self.transfer(CMD_SET_ALL, bytes([1 if ch1 else 0, 1 if ch2 else 0]))
        return {"ch1": bool(p[0]), "ch2": bool(p[1])}

    def pulse(self, ch: int, off_ms: int = 200, on_ms: int = 0) -> dict:
        if ch not in (1, 2):
            raise ValueError("ch must be 1 or 2")
        off_ms = max(0, min(10000, int(off_ms)))
        on_ms = max(0, min(10000, int(on_ms)))
        pld = bytes([ch, off_ms & 0xFF, (off_ms >> 8) & 0xFF])
        if on_ms:
            pld += bytes([on_ms & 0xFF, (on_ms >> 8) & 0xFF])
        timeout = max(2000, off_ms + on_ms + 1500)
        _, p = self.transfer(CMD_PULSE, pld, timeout_ms=timeout)
        return {"ch1": bool(p[0]), "ch2": bool(p[1])}

    def get_info(self) -> dict:
        _, p = self.transfer(CMD_GET_INFO)
        if len(p) < 3:
            raise RuntimeError("GET_INFO short payload")
        return {
            "protocol_ver": p[0],
            "channels": p[1],
            "flags": p[2],
            "pulse_supported": bool(p[2] & 0x01),
        }
