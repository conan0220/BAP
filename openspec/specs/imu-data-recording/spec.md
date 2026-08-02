# imu-data-recording Specification

## Purpose

Define the existing offline command-line recording behavior that collects parsed ANROT gateway measurements from one or more serial ports into gateway-specific CSV files.

## Requirements

### Requirement: Recording command inputs
The system SHALL provide a recording command that accepts a required comma-separated serial-port list, a positive integer baud rate defaulting to `115200`, an output path defaulting to `recorded_data.csv`, and a positive duration in seconds defaulting to `10`.

#### Scenario: Start with valid recording inputs
- **WHEN** the operator supplies at least one non-empty serial port and valid option values
- **THEN** the system opens each selected port with the common baud rate and records until the configured duration elapses or the operator interrupts it

#### Scenario: Reject an empty port list
- **WHEN** the supplied port list contains no non-whitespace port name
- **THEN** the command rejects the input before recording

#### Scenario: Reject an invalid baud rate or duration
- **WHEN** the supplied baud rate is not a positive integer or the duration is not a positive number
- **THEN** the command rejects the invalid value before recording

### Requirement: Independent multi-port parsing
The recorder SHALL maintain independent incremental binary-parser state for each selected serial port so that partial input from one port does not affect frames read from another port.

#### Scenario: Frames are interleaved across two ports
- **WHEN** two selected ports provide frame fragments in an interleaved order
- **THEN** each fragment is combined only with prior bytes from the same port and complete valid frames from both ports can be recorded

### Requirement: Gateway-specific CSV output
The recorder SHALL route each decoded packet to a CSV file identified by its gateway ID. The file name SHALL append `_<gateway-id>` before the configured suffix, use `.csv` when the configured output has no suffix, and use `unknown` when a decoded packet has no gateway ID.

#### Scenario: Record two gateway IDs
- **WHEN** decoded packets from two gateway IDs arrive during one recording
- **THEN** the recorder writes each gateway's rows to a separate output file bearing that gateway ID

#### Scenario: No packet is decoded for a gateway
- **WHEN** the recording receives no decodable packet for a gateway
- **THEN** the recorder creates no output file for that gateway

### Requirement: Fixed 16-node CSV schema
Each gateway CSV SHALL begin with `UnixTimeStamp(sec)` and `SystemTime(ms)`, followed by 16 node groups. Each node group SHALL contain node ID; three acceleration values in g; three angular-velocity values in degrees per second; three magnetic-field values in microtesla; roll, pitch, and yaw in degrees; and quaternion W, X, Y, and Z.

#### Scenario: Write a gateway packet row
- **WHEN** the recorder processes a decoded gateway packet
- **THEN** it writes one row using the host Unix time in whole seconds, the packet's first frame system time in milliseconds, and the decoded node measurements in packet-position slots

#### Scenario: A node slot is absent
- **WHEN** a gateway packet contains no decoded frame for one of the 16 node positions
- **THEN** the recorder leaves all 17 fields for that node position empty

### Requirement: Existing numeric CSV precision
The recorder SHALL format acceleration and quaternion values to three decimal places, angular velocity, magnetic field, and Euler angles to two decimal places, and leave unavailable values empty.

#### Scenario: Write available and unavailable measurements
- **WHEN** a decoded frame contains some supported measurement fields and leaves others unavailable
- **THEN** the CSV row formats the available values at their defined precision and writes empty fields for unavailable values

### Requirement: Recording termination and persistence
The recorder SHALL flush open gateway files at least once per second during capture, close them when the configured duration elapses or the operator interrupts recording, and terminate with a failure status when serial access or permission fails.

#### Scenario: Configured duration elapses
- **WHEN** the recording deadline is reached
- **THEN** the recorder closes all open serial connections and gateway CSV files and returns control to the operator

#### Scenario: Operator interrupts recording
- **WHEN** the operator sends a keyboard interrupt during capture
- **THEN** the recorder closes all open resources while preserving rows already written

#### Scenario: A selected serial port cannot be accessed
- **WHEN** opening or reading a selected serial port raises a serial-access or permission error
- **THEN** the recorder closes resources opened by the command and terminates with a failure status
