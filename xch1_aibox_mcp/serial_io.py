# -*- coding: utf-8 -*-
"""CDC serial helpers for target UART bridged by XCH1-AI-BOX."""
from __future__ import annotations

import threading
from typing import Optional

import serial
from serial.tools import list_ports


class SerialSession:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ser: Optional[serial.Serial] = None

    @property
    def is_open(self) -> bool:
        return self._ser is not None and self._ser.is_open

    def list_ports(self) -> list[dict]:
        rows = []
        for p in list_ports.comports():
            rows.append(
                {
                    "device": p.device,
                    "description": p.description or "",
                    "hwid": p.hwid or "",
                    "vid": p.vid,
                    "pid": p.pid,
                    "serial_number": p.serial_number,
                }
            )
        return rows

    def open(self, port: str, baud: int = 115200, timeout: float = 0.2) -> dict:
        with self._lock:
            if self._ser and self._ser.is_open:
                self._ser.close()
            self._ser = serial.Serial(port=port, baudrate=baud, timeout=timeout)
            return {
                "port": self._ser.port,
                "baud": self._ser.baudrate,
                "open": True,
            }

    def close(self) -> dict:
        with self._lock:
            if self._ser and self._ser.is_open:
                port = self._ser.port
                self._ser.close()
                self._ser = None
                return {"port": port, "open": False}
            self._ser = None
            return {"open": False}

    def write(self, data: bytes) -> dict:
        with self._lock:
            if not self._ser or not self._ser.is_open:
                raise RuntimeError("serial not open")
            n = self._ser.write(data)
            self._ser.flush()
            return {"written": n}

    def read(self, max_bytes: int = 4096, timeout_s: Optional[float] = None) -> dict:
        with self._lock:
            if not self._ser or not self._ser.is_open:
                raise RuntimeError("serial not open")
            old = self._ser.timeout
            if timeout_s is not None:
                self._ser.timeout = timeout_s
            try:
                data = self._ser.read(max_bytes)
            finally:
                self._ser.timeout = old
            return {
                "len": len(data),
                "hex": data.hex(),
                "text": data.decode("utf-8", errors="replace"),
            }
