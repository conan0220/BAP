from __future__ import annotations

import math

import pytest

from helpers import (
    build_gateway_frame,
    build_gateway_node,
    build_hi81_frame,
    build_hi91_frame,
    build_hi92_frame,
)
from parsers.anrot_serial_parser import AnrotSerialParser, GRAVITY, R2D


@pytest.mark.scenario("imu-data-parsing", "A valid frame arrives in multiple chunks")
def test_valid_frame_arrives_in_multiple_chunks(hi91_frame: bytes) -> None:
    parser = AnrotSerialParser()

    assert parser.parse(hi91_frame[:5]) == []
    assert parser.parse(hi91_frame[5:30]) == []
    frames = parser.parse(hi91_frame[30:])

    assert len(frames) == 1
    assert frames[0].frame_type == 0x91
    assert parser.buffer == bytearray()


@pytest.mark.scenario("imu-data-parsing", "Noise precedes a valid frame")
def test_noise_precedes_valid_frame(hi91_frame: bytes) -> None:
    frames = AnrotSerialParser().parse(b"noise\x5a" + hi91_frame)

    assert len(frames) == 1
    assert frames[0].system_time_ms == 456789


@pytest.mark.scenario("imu-data-parsing", "A complete frame has an invalid CRC")
def test_invalid_crc_is_rejected_and_later_frame_is_accepted(hi91_frame: bytes) -> None:
    invalid = bytearray(hi91_frame)
    invalid[4] ^= 0xFF
    parser = AnrotSerialParser()

    frames = parser.parse(bytes(invalid) + hi91_frame)

    assert len(frames) == 1
    assert frames[0].system_time_ms == 456789


@pytest.mark.parametrize(
    ("frame_factory", "frame_type"),
    [
        pytest.param(build_hi91_frame, 0x91, id="HI91"),
        pytest.param(build_hi92_frame, 0x92, id="HI92"),
        pytest.param(build_hi81_frame, 0x81, id="HI81"),
    ],
)
@pytest.mark.scenario("imu-data-parsing", "Decode a supported single-device payload")
def test_decode_supported_single_device_payload(frame_factory, frame_type: int) -> None:
    frame = AnrotSerialParser().parse(frame_factory())[0]

    assert frame.frame_type == frame_type
    assert frame.acc is not None
    assert frame.gyr is not None
    assert frame.mag is not None
    assert frame.quat is not None

    if frame_type == 0x91:
        assert frame.temperature == 25
        assert frame.pressure == pytest.approx(100123.5)
        assert frame.system_time_ms == 456789
        assert frame.acc == pytest.approx((1.25, -2.5, 3.75))
        assert frame.gyr == pytest.approx((10.0, -20.0, 30.0))
        assert frame.mag == pytest.approx((40.0, -50.0, 60.0))
        assert (frame.roll, frame.pitch, frame.yaw) == pytest.approx((12.5, -6.25, 270.0))
    elif frame_type == 0x92:
        assert frame.temperature == 21
        assert frame.pressure == 100123
        assert frame.gyr == pytest.approx([1000 * 0.001 * R2D, -2000 * 0.001 * R2D, 500 * 0.001 * R2D])
        assert frame.acc == pytest.approx([1000 * 0.0048828 / GRAVITY, -1000 * 0.0048828 / GRAVITY, 2000 * 0.0048828 / GRAVITY])
        assert frame.mag == pytest.approx([3.0517, -6.1034, 9.1551])
        assert (frame.roll, frame.pitch, frame.yaw) == pytest.approx((1.234, -5.678, 90.0))
    else:
        assert frame.ins_status == 7
        assert frame.gpst_wn == 2300
        assert frame.gpst_tow == pytest.approx(123.456)
        assert frame.system_time_ms == 987654
        assert (frame.roll, frame.pitch, frame.yaw) == pytest.approx((12.5, -6.25, 270.0))
        assert (frame.ins_lon, frame.ins_lat, frame.ins_msl) == pytest.approx((121.5, 25.0, 12.345))
        assert frame.vel_enu == pytest.approx([1.0, -2.0, 3.0])


@pytest.mark.scenario("imu-data-parsing", "Decode a complete multi-node gateway payload")
def test_decode_complete_multi_node_gateway_payload() -> None:
    raw = build_gateway_frame(
        gateway_id=7,
        timestamp_ms=654321,
        nodes=[build_gateway_node(11), build_gateway_node(12, acc=(500, 0, -500))],
    )

    frames = AnrotSerialParser().parse(raw)

    assert [frame.node_id for frame in frames] == [11, 12]
    assert [frame.node_index for frame in frames] == [0, 1]
    assert all(frame.frame_type == 0x63 for frame in frames)
    assert all(frame.gw_id == 7 for frame in frames)
    assert all(frame.node_count == 2 for frame in frames)
    assert all(frame.gw_ts_ms == 654321 and frame.system_time_ms == 654321 for frame in frames)
    assert frames[0].acc == pytest.approx((1.0, -2.0, 3.0))
    assert frames[0].mag == pytest.approx((10.0, -20.0, 30.0))
    assert frames[0].gyr == pytest.approx((40.0, -50.0, 60.0))
    assert frames[0].quat == pytest.approx((1.0, 0.0, -16384 / 32767, 8192 / 32767))
    assert (frames[0].roll, frames[0].pitch, frames[0].yaw) == pytest.approx((12.5, -6.25, 270.0))


@pytest.mark.scenario("imu-data-parsing", "Gateway declares more than 16 nodes")
def test_gateway_declaring_more_than_sixteen_nodes_is_capped() -> None:
    nodes = [build_gateway_node(node_id) for node_id in range(1, 18)]

    frames = AnrotSerialParser().parse(build_gateway_frame(declared_node_count=17, nodes=nodes))

    assert len(frames) == 16
    assert [frame.node_id for frame in frames] == list(range(1, 17))
    assert all(frame.node_count == 17 for frame in frames)


@pytest.mark.scenario("imu-data-parsing", "Final node block is incomplete")
def test_incomplete_final_gateway_node_is_not_fabricated() -> None:
    complete_node = build_gateway_node(11)
    partial_node = build_gateway_node(12)[:10]

    frames = AnrotSerialParser().parse(
        build_gateway_frame(declared_node_count=2, nodes=[complete_node, partial_node])
    )

    assert len(frames) == 1
    assert frames[0].node_id == 11
    assert frames[0].node_count == 2
