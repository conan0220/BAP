# imu-device-communication Specification

## Purpose

Define the existing command-line behavior for discovering serial ports, monitoring parsed ANROT device output, and sending persistent device configuration commands.

## Requirements

### Requirement: Serial port discovery
The system SHALL provide a command that enumerates currently available serial ports and displays each port's device name, reported manufacturer, and access-permission status when available.

#### Scenario: Serial ports are available
- **WHEN** the operator runs the port-listing command and the operating system reports one or more serial ports
- **THEN** the system displays the number of ports and one entry for each reported port

#### Scenario: No serial ports are available
- **WHEN** the operator runs the port-listing command and the operating system reports no serial ports
- **THEN** the system reports that no available serial ports were found

### Requirement: Live serial monitoring
The system SHALL accept a serial port and positive integer baud rate, continuously read available bytes from that port until interrupted or an access error occurs, and display the most recently parsed ANROT binary and NMEA measurements together with an observed frame rate.

#### Scenario: Monitor valid mixed device output
- **WHEN** the selected port supplies supported ANROT binary frames or supported NMEA sentences
- **THEN** the system periodically refreshes the display with the latest parsed measurements and the measured number of parsed frames per second

#### Scenario: Reject an invalid monitoring baud rate
- **WHEN** the operator supplies a baud rate that is not a positive integer
- **THEN** the command rejects the value before opening the serial port

#### Scenario: Serial monitoring cannot access the port
- **WHEN** opening or reading the selected port raises a serial-access or permission error
- **THEN** the system reports the error and terminates the monitoring command with a failure status

### Requirement: Saved device command sequence
The system SHALL provide a command that opens the selected serial port using 8 data bits, no parity, and one stop bit; stops device output; sends the operator's command; saves the configuration; and restarts device output. Each command SHALL be terminated with carriage return and line feed when the supplied command does not already contain that terminator.

#### Scenario: Send and save a command successfully
- **WHEN** the device acknowledges the output-stop command, the operator command, the save command, and the output-start command with responses containing `OK`
- **THEN** the system completes the sequence in that order and displays the operator command's response

#### Scenario: Device output does not stop initially
- **WHEN** the device does not acknowledge `AT+EOUT=0`
- **THEN** the system attempts that command no more than three times and stops the sequence with an error if all attempts fail

#### Scenario: A later command is not acknowledged
- **WHEN** the operator command, `SAVECONFIG`, or `AT+EOUT=1` does not return a response containing `OK`
- **THEN** the system reports which step failed and stops the remaining sequence

#### Scenario: Reject an invalid command baud rate
- **WHEN** the operator supplies a baud rate that is not a positive integer
- **THEN** the command rejects the value before opening the serial port
