from __future__ import annotations

import struct
from collections.abc import Iterable

from parsers.anrot_serial_parser import AnrotSerialParser


def build_anrot_frame(payload: bytes | bytearray) -> bytes:
    payload = bytes(payload)
    prefix = b"\x5a\xa5" + struct.pack("<H", len(payload))
    crc = AnrotSerialParser.crc16_update(0, prefix + payload)
    return prefix + struct.pack("<H", crc) + payload


def build_hi91_frame() -> bytes:
    payload = bytearray(76)
    payload[0] = 0x91
    struct.pack_into("<b", payload, 3, 25)
    struct.pack_into("<f", payload, 4, 100123.5)
    struct.pack_into("<I", payload, 8, 456789)
    struct.pack_into("<3f", payload, 12, 1.25, -2.5, 3.75)
    struct.pack_into("<3f", payload, 24, 10.0, -20.0, 30.0)
    struct.pack_into("<3f", payload, 36, 40.0, -50.0, 60.0)
    struct.pack_into("<3f", payload, 48, 12.5, -6.25, 270.0)
    struct.pack_into("<4f", payload, 60, 1.0, 0.0, -0.5, 0.25)
    return build_anrot_frame(payload)


def build_hi92_frame() -> bytes:
    payload = bytearray(48)
    payload[0] = 0x92
    struct.pack_into("<b", payload, 3, 21)
    struct.pack_into("<h", payload, 6, 123)
    struct.pack_into("<3h", payload, 10, 1000, -2000, 500)
    struct.pack_into("<3h", payload, 16, 1000, -1000, 2000)
    struct.pack_into("<3h", payload, 22, 100, -200, 300)
    struct.pack_into("<3i", payload, 28, 1234, -5678, 90000)
    struct.pack_into("<4h", payload, 40, 10000, 0, -10000, 5000)
    return build_anrot_frame(payload)


def build_hi81_frame() -> bytes:
    payload = bytearray(104)
    payload[0] = 0x81
    struct.pack_into("<B", payload, 3, 7)
    struct.pack_into("<H", payload, 4, 2300)
    struct.pack_into("<I", payload, 6, 123456)
    struct.pack_into("<3h", payload, 12, 100, -200, 300)
    struct.pack_into("<3h", payload, 18, 1000, -1000, 500)
    struct.pack_into("<3h", payload, 24, 100, -200, 300)
    struct.pack_into("<h", payload, 30, 250)
    struct.pack_into("<b", payload, 34, 22)
    struct.pack_into("<5B", payload, 35, 26, 8, 2, 14, 30)
    struct.pack_into("<H", payload, 40, 12345)
    struct.pack_into("<2hH", payload, 42, 1250, -625, 27000)
    struct.pack_into("<4h", payload, 48, 10000, 0, -10000, 5000)
    struct.pack_into("<3i", payload, 56, 1215000000, 250000000, 12345)
    struct.pack_into("<2B", payload, 68, 15, 10)
    struct.pack_into("<5B", payload, 70, 4, 12, 5, 8, 2)
    struct.pack_into("<h", payload, 75, -125)
    struct.pack_into("<3h", payload, 78, 100, -200, 300)
    struct.pack_into("<3h", payload, 84, 10, -20, 30)
    struct.pack_into("<I", payload, 90, 987654)
    return build_anrot_frame(payload)


def build_gateway_node(
    node_id: int,
    *,
    acc: tuple[int, int, int] = (1000, -2000, 3000),
    mag: tuple[int, int, int] = (100, -200, 300),
    gyr: tuple[int, int, int] = (400, -500, 600),
    quat: tuple[int, int, int, int] = (32767, 0, -16384, 8192),
    euler: tuple[int, int, int] = (1250, -625, 27000),
) -> bytes:
    node = bytearray(34)
    node[0] = 0x93
    node[1] = node_id
    struct.pack_into("<3h", node, 2, *acc)
    struct.pack_into("<3h", node, 8, *mag)
    struct.pack_into("<3h", node, 14, *gyr)
    struct.pack_into("<4h", node, 20, *quat)
    struct.pack_into("<3h", node, 28, *euler)
    return bytes(node)


def build_gateway_frame(
    *,
    gateway_id: int = 3,
    declared_node_count: int | None = None,
    nodes: Iterable[bytes] | None = None,
    timestamp_ms: int = 123456,
) -> bytes:
    node_blocks = list(nodes if nodes is not None else [build_gateway_node(11)])
    node_count = len(node_blocks) if declared_node_count is None else declared_node_count
    payload = bytearray(8)
    payload[0] = 0x63
    payload[1] = gateway_id
    payload[2] = node_count
    struct.pack_into("<I", payload, 4, timestamp_ms)
    payload.extend(b"".join(node_blocks))
    return build_anrot_frame(payload)


def build_nmea_sentence(body: str) -> str:
    checksum = 0
    for char in body:
        checksum ^= ord(char)
    return f"${body}*{checksum:02X}\r\n"


class FakeSerial:
    def __init__(
        self,
        chunks: Iterable[bytes] = (),
        *,
        responses: Iterable[bytes] = (),
        interrupt_when_empty: bool = False,
        waiting_error: BaseException | None = None,
    ) -> None:
        self.chunks = list(chunks)
        self.responses = list(responses)
        self.interrupt_when_empty = interrupt_when_empty
        self.waiting_error = waiting_error
        self.response_buffer = b""
        self.writes: list[bytes] = []
        self.is_open = True
        self.closed = False
        self.flush_count = 0
        self.name = "FAKE"

    @property
    def in_waiting(self) -> int:
        if self.waiting_error is not None:
            error, self.waiting_error = self.waiting_error, None
            raise error
        if self.response_buffer:
            return len(self.response_buffer)
        if self.chunks:
            return len(self.chunks[0])
        if self.interrupt_when_empty:
            raise KeyboardInterrupt
        return 0

    def read(self, size: int) -> bytes:
        if self.response_buffer:
            data, self.response_buffer = self.response_buffer[:size], self.response_buffer[size:]
            return data
        if not self.chunks:
            return b""
        chunk = self.chunks.pop(0)
        data, remainder = chunk[:size], chunk[size:]
        if remainder:
            self.chunks.insert(0, remainder)
        return data

    def write(self, data: bytes) -> int:
        self.writes.append(data)
        if self.responses:
            self.response_buffer = self.responses.pop(0)
        return len(data)

    def open(self) -> None:
        self.is_open = True

    def close(self) -> None:
        self.closed = True
        self.is_open = False

    def flush(self) -> None:
        self.flush_count += 1

    def __enter__(self) -> "FakeSerial":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()


class SequenceClock:
    def __init__(self, values: Iterable[float], *, fallback: float | None = None) -> None:
        self.values = iter(values)
        self.last = 0.0 if fallback is None else fallback

    def __call__(self) -> float:
        try:
            self.last = next(self.values)
        except StopIteration:
            pass
        return self.last
