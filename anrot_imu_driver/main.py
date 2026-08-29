import click

try:
    from .utils import check_python_version
    from .commands.cmd_list import cmd_list
    from .commands.read_data import cmd_read
    from .commands.cmd_send import cmd_send
    from .commands.record_data import cmd_record
except ImportError:  # Preserve direct `python anrot_imu_driver/main.py` usage.
    from utils import check_python_version
    from commands.cmd_list import cmd_list
    from commands.read_data import cmd_read
    from commands.cmd_send import cmd_send
    from commands.record_data import cmd_record

@click.group()
def cli():
    """IMU Python Example"""
    check_python_version()

cli.add_command(cmd_list)
cli.add_command(cmd_read)
cli.add_command(cmd_send)
cli.add_command(cmd_record)

if __name__ == "__main__":
    cli()
