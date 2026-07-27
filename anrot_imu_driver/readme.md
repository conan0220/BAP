# ANROT Python Serial Example

This package reads ANROT binary frames and NMEA text output from a serial port. It also provides a command sender for configuration commands.

## Requirements

- Python 3.6 or newer
- pyserial
- An ANROT device connected through USB, RS232-to-USB, or UART-to-USB

Install dependencies:

```bash
pip install -r requirements.txt
```

## List Serial Ports

```bash
python main.py list
```

## Read Data

Windows:

```bash
python main.py read -p COM3 -b 115200
```

Linux or Raspberry Pi:

```bash
python main.py read -p /dev/ttyUSB0 -b 115200
```

## Send a Command

```bash
python main.py send -p COM3 -b 115200 "LOG VERSION"
```

The sender stops data output, sends the command, saves the setting, and restarts data output.

## Files

- `main.py`: command-line entry point
- `commands/`: list, read, and send commands
- `parsers/anrot_serial_parser.py`: ANROT binary frame parser
- `parsers/anrot_nmea_parser.py`: NMEA text parser
- `utils.py`: serial-port helper functions
