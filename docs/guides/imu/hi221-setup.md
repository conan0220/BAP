# HI221 Setup Guide

This guide describes a manual setup procedure for new-generation HI221 nodes and an HI221 Dongle using the `0x63` data format. Legacy `0x62` configuration is not covered.

For packet layout, coordinate conventions, and hardware constraints, see [`docs/knowledge/imu/hi221.md`](../../knowledge/imu/hi221.md).

## Before Configuring Devices

1. Connect and configure only one device at a time so commands cannot be sent to the wrong node.
2. Record the current settings reported by `AT+INFO` before making changes.
3. Decide the following values:
   - One shared `GWID` for the Dongle and all of its nodes.
   - One unique, consecutive node ID per node, starting at 0.
   - The required sampling rate and corresponding maximum node count.
   - The Dongle UART baud rate.
4. Ensure the serial tool uses the device's current baud rate. Unreadable output usually indicates a baud-rate mismatch.

## Example High-Rate Configuration

A two-node, high-rate deployment can use:

| Setting | Value |
|---|---|
| Dongle packet format | `0x63` |
| Node RF format | `09` |
| Dongle output rate | 400 Hz |
| Dongle UART baud rate | 921600 |

At 400 Hz, the Dongle supports at most two nodes. Reduce the output rate when more nodes are required.

## Configure the Dongle

Connect to the HI221 Dongle at its current baud rate.

```text
AT+INFO
AT+EOUT=0
AT+GWID=<shared-gwid>
AT+SETPTL=63
AT+ODR=<output-rate>
```

Confirm that the `AT+ODR` response reports a maximum node count large enough for the intended deployment.

Set the UART baud rate last:

```text
AT+BAUD=<baud-rate>
```

`AT+BAUD` takes effect immediately. Reconfigure or reopen the host serial connection at the new baud rate before sending further commands. Then restart and reconnect:

```text
AT+RST
```

After reconnecting, use `AT+INFO` to verify the settings.

## Configure Each Node

Connect each HI221 node directly and configure it separately.

```text
AT+INFO
AT+GWID=<shared-gwid>
AT+ID=<node-id>
AT+TXFMT=09
AT+RST
```

Requirements:

- The node `GWID` must match the Dongle `GWID`.
- Node IDs must be unique and consecutive: `0`, `1`, ..., `N-1`.
- Each node ID must be lower than the maximum node count reported by the Dongle.
- All nodes under one Dongle must use `AT+TXFMT=09` for `0x63` mode.

A node's UART baud rate only affects a direct serial connection to that node. It does not control the wireless update rate reported by the Dongle. Change it only when direct node access requires a different baud rate.

## Verify the Deployment

1. Connect to the Dongle at the configured baud rate.
2. Run `AT+INFO` and verify its `GWID`, output rate, and maximum node count.
3. Enable data output if necessary:

   ```text
   AT+EOUT=1
   ```

4. Verify that received payloads have:
   - Gateway tag `0x63`.
   - The expected node count.
   - One 34-byte block per node.
   - Node tag `0x93` in every block.
   - The expected unique node IDs.

## Troubleshooting

### Serial output is unreadable

- The host and device baud rates probably differ.
- Reopen the serial connection using the configured device baud rate.
- Remember that `AT+BAUD` changes the device baud rate immediately.

### The Dongle reports no node

Check that:

- The Dongle and every node use the same `GWID`.
- Node IDs are unique, consecutive, and within the Dongle's reported range.
- Every new node uses `AT+TXFMT=09`.
- The Dongle uses `AT+SETPTL=63`.
- Devices were restarted after changing settings that require a restart.

### The requested rate cannot support all nodes

Reduce the Dongle output rate with `AT+ODR`. Typical limits from the vendor documentation are:

| Output rate | Maximum nodes |
|---:|---:|
| 400 Hz | 2 |
| 200 Hz | 7 |
| 100 Hz | 16 |
