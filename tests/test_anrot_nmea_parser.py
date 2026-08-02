from __future__ import annotations

import pytest

from parsers.anrot_nmea_parser import AnrotNmeaParser


SUPPORTED_BODIES = [
    pytest.param("GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,", "GGA", id="GGA"),
    pytest.param("GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W", "RMC", id="RMC"),
    pytest.param("GPVTG,054.7,T,034.4,M,005.5,N,010.2,K", "VTG", id="VTG"),
    pytest.param("GPGSA,A,3,04,05,,09,12,,,24,,,,,2.5,1.3,2.1", "GSA", id="GSA"),
    pytest.param("GPGSV,2,1,08,01,40,083,46,02,17,308,41,12,07,344,39,14,22,228,45", "GSV", id="GSV"),
    pytest.param(
        "GPSXT,20230310090529.59,116.45784882,39.90572287,158.2289,359.87,-4.99,359.87,0.001,171.25,1,0,15,15,0.056,-0.040,0.017,-0.001,-0.000,0.002,8,0",
        "SXT",
        id="SXT",
    ),
]


@pytest.mark.parametrize(("body", "message_id"), SUPPORTED_BODIES)
@pytest.mark.scenario("imu-data-parsing", "A supported valid sentence is complete")
def test_supported_valid_nmea_sentence_is_decoded(nmea_sentence_factory, body: str, message_id: str) -> None:
    parsed = AnrotNmeaParser().parse(nmea_sentence_factory(body))

    assert len(parsed) == 1
    assert parsed[0]["message_id"] == message_id


@pytest.mark.scenario("imu-data-parsing", "A sentence is incomplete")
def test_incomplete_nmea_sentence_is_retained(nmea_sentence_factory) -> None:
    sentence = nmea_sentence_factory(SUPPORTED_BODIES[0].values[0])
    parser = AnrotNmeaParser()

    assert parser.parse(sentence[:-2]) == []
    assert parser.buffer
    parsed = parser.parse("\r\n")

    assert parsed[0]["message_id"] == "GGA"
    assert parser.buffer == ""


@pytest.mark.parametrize("kind", ["invalid-checksum", "unsupported-type"])
@pytest.mark.scenario("imu-data-parsing", "A sentence has an invalid checksum or unsupported type")
def test_invalid_or_unsupported_nmea_is_ignored_and_later_input_is_accepted(
    nmea_sentence_factory, kind: str
) -> None:
    parser = AnrotNmeaParser()
    valid = nmea_sentence_factory(SUPPORTED_BODIES[1].values[0])
    if kind == "invalid-checksum":
        rejected = valid[:-4] + "00\r\n"
    else:
        rejected = nmea_sentence_factory("GPXYZ,1,2,3")

    parsed = parser.parse(rejected + valid)

    assert len(parsed) == 1
    assert parsed[0]["message_id"] == "RMC"
