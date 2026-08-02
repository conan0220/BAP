## Purpose

Define the existing incremental decoding behavior that converts supported ANROT binary frames and checksummed NMEA text sentences into structured sensor measurements.

## ADDED Requirements

### Requirement: Incremental ANROT binary framing
The binary parser SHALL buffer arbitrarily divided input bytes, identify frames beginning with `0x5A 0xA5`, use the declared payload length to await a complete frame, and emit measurements only for frames whose CRC-16 matches the received CRC.

#### Scenario: A valid frame arrives in multiple chunks
- **WHEN** the bytes of a valid ANROT frame are supplied across multiple parser calls
- **THEN** the parser retains the incomplete bytes and emits the decoded frame only after the complete CRC-valid frame is available

#### Scenario: Noise precedes a valid frame
- **WHEN** unrelated bytes precede a valid ANROT synchronization sequence
- **THEN** the parser discards bytes before the synchronization sequence and decodes the valid frame

#### Scenario: A complete frame has an invalid CRC
- **WHEN** a complete ANROT frame's calculated CRC does not equal its received CRC
- **THEN** the parser emits no measurement for that frame and continues accepting later input

### Requirement: Supported single-device ANROT payloads
The binary parser SHALL decode supported `0x91`, `0x92`, and `0x81` payloads into their available timestamp, acceleration, angular velocity, magnetic field, orientation, environment, navigation, and status fields using the format-specific scale factors.

#### Scenario: Decode a supported single-device payload
- **WHEN** a CRC-valid ANROT frame contains a supported `0x91`, `0x92`, or `0x81` payload
- **THEN** the parser emits one structured frame with the fields provided by that payload converted to the units defined by the parser's format mapping

### Requirement: Compact multi-node gateway payload decoding
The binary parser SHALL decode an ANROT `0x63` gateway payload into no more than 16 node measurements. Each emitted node measurement SHALL include the gateway ID, node ID, shared gateway timestamp in milliseconds, node count, zero-based packet position, three-axis acceleration in g, three-axis magnetic field in microtesla, three-axis angular velocity in degrees per second, quaternion, and roll, pitch, and yaw in degrees.

#### Scenario: Decode a complete multi-node gateway payload
- **WHEN** a CRC-valid `0x63` payload declares node blocks that are fully present
- **THEN** the parser emits one structured measurement per decoded node block with the shared gateway metadata and scaled sensor values

#### Scenario: Gateway declares more than 16 nodes
- **WHEN** a `0x63` payload declares more than 16 nodes
- **THEN** the parser emits measurements for at most the first 16 node blocks

#### Scenario: Final node block is incomplete
- **WHEN** the remaining `0x63` payload bytes cannot provide a complete 34-byte node block
- **THEN** the parser emits the node blocks decoded before the incomplete block and does not fabricate the missing measurement

### Requirement: Incremental checksummed NMEA parsing
The NMEA parser SHALL buffer text until a newline-terminated sentence is available, validate its checksum, and emit structured data only for supported `GGA`, `RMC`, `VTG`, `GSA`, `GSV`, and `SXT` sentence types.

#### Scenario: A supported valid sentence is complete
- **WHEN** a newline-terminated supported NMEA sentence has a valid checksum and valid field values
- **THEN** the parser emits a structured dictionary identifying the sentence type and decoded fields

#### Scenario: A sentence is incomplete
- **WHEN** a parser call ends before the newline terminating an NMEA sentence
- **THEN** the parser retains the partial sentence and emits no data for it until completion

#### Scenario: A sentence has an invalid checksum or unsupported type
- **WHEN** a complete NMEA sentence fails checksum validation or has a sentence type outside the supported set
- **THEN** the parser emits no structured data for that sentence and continues accepting later input
