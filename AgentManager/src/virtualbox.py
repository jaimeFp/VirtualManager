import os
import shutil
import subprocess
import re
from pathlib import Path

VM_STATE_RUNNING = "running"
VM_STATE_PAUSED = "paused"
VM_STATE_POWEROFF = "poweroff"
VM_STATE_SAVED = "saved"
VM_STATE_ABORTED = "aborted"

def find_vboxmanage() -> str:
    """!
    @brief Locate the VBoxManage executable.
    @details Search PATH first. On Windows, also check the standard
             VirtualBox installation directory.
    @return Absolute path to the VBoxManage executable.
    @exception FileNotFoundError If VBoxManage cannot be found.
    """
    executable = shutil.which("VBoxManage")

    if executable:
        return str(Path(executable).resolve())

    if os.name == "nt":
        program_files = os.environ.get("ProgramFiles")

        if program_files:
            candidate = (
                Path(program_files)
                / "Oracle"
                / "VirtualBox"
                / "VBoxManage.exe"
            )

            if candidate.is_file():
                return str(candidate.resolve())

    raise FileNotFoundError(
        "VBoxManage was not found. Install VirtualBox or add its "
        "installation directory to PATH."
    )

def run_vboxmanage(arguments: list[str],timeout: float = 30.0,) -> str:
    """!
    @brief Execute a VBoxManage command.
    @param arguments Command arguments without the executable path.
    @param timeout Maximum execution time in seconds.
    @return Command standard output.
    @exception FileNotFoundError If VBoxManage cannot be found.
    @exception subprocess.CalledProcessError If the command fails.
    @exception subprocess.TimeoutExpired If execution exceeds the timeout.
    @exception OSError If the executable cannot be started.
    """
    executable = find_vboxmanage()

    result = subprocess.run(
        [executable, *arguments],
        capture_output=True,
        text=True,
        check=True,
        timeout=timeout,
        shell=False,
    )

    return result.stdout

def list_virtual_machines() -> list[dict[str, str]]:
    """!
    @brief List the virtual machines registered for the current user.
    @return A list of dictionaries containing each machine's name and UUID.
            Return an empty list if no machines are registered.
    @exception ValueError If an output line has an unexpected format.
    @details Exceptions raised by run_vboxmanage are propagated.
    """
    output = run_vboxmanage(["list", "vms"])
    machines: list[dict[str, str]] = []

    pattern = re.compile(
        r'^"(?P<name>.*)"\s+\{'
        r'(?P<uuid>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-'
        r'[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})'
        r'\}$'
    )

    for line in output.splitlines():
        line = line.strip()

        if not line:
            continue

        match = pattern.fullmatch(line)

        if match is None:
            raise ValueError(
                f"Unexpected VBoxManage output format: {line!r}"
            )

        machines.append({
            "name": match.group("name"),
            "uuid": match.group("uuid"),
        })

    return machines

def get_virtual_machine_state(uuid: str) -> str:
    """!
    @brief Get the current state of a virtual machine.
    @param uuid UUID of the virtual machine.
    @return Current state of the virtual machine.
    @exception ValueError If the VMState field is not present in the
                          VBoxManage output.
    @details Exceptions raised by get_virtual_machine_info are propagated.
    """
    information = get_virtual_machine_info(uuid)

    state = information.get("VMState")

    if state is None:
        raise ValueError(
            f"Unable to determine the state of virtual machine {uuid!r}."
        )

    return state

def get_virtual_machine_info(uuid: str) -> dict[str, str]:
    """!
    @brief Get detailed information about a virtual machine.
    @param uuid UUID of the virtual machine.
    @return A dictionary containing the machine information reported by
            VBoxManage.
    @details Lines that do not contain key-value information are ignored.
             Exceptions raised by run_vboxmanage are propagated.
    """
    output = run_vboxmanage([
        "showvminfo",
        uuid,
        "--machinereadable",
    ])

    information: dict[str, str] = {}

    for line in output.splitlines():
        line = line.strip()

        if not line:
            continue

        key, separator, value = line.partition("=")

        if not separator:
            continue

        key = key.strip()
        value = value.strip()

        # VBoxManage --machinereadable commonly returns quoted strings.
        if (
            len(value) >= 2
            and value.startswith('"')
            and value.endswith('"')
        ):
            value = value[1:-1]

        information[key] = value

    return information


def start_virtual_machine(uuid: str,headless: bool = True) -> None:
    """!
    @brief Start a virtual machine.
    @param uuid UUID of the virtual machine.
    @param headless Start the virtual machine without a graphical interface
                    when True.
    @exception ValueError If the virtual machine cannot be started from its
                          current state.
    @details If the virtual machine is already running or paused, no action
             is performed. Exceptions raised by run_vboxmanage are propagated.
    """
    state = get_virtual_machine_state(uuid)

    if state in ("running", "paused"):
        return

    if state not in ("poweroff", "saved", "aborted"):
        raise ValueError(f"Cannot start virtual machine {uuid!r} from state {state!r}.")

    arguments = ["startvm", uuid]

    if headless:
        arguments.extend(["--type", "headless"])

    run_vboxmanage(arguments)


def shutdown_virtual_machine(uuid: str) -> None:
    """!
    @brief Request a graceful shutdown of a virtual machine.
    @param uuid UUID of the virtual machine.
    @exception ValueError If the virtual machine cannot be shut down from its
                          current state.
    @details Sends an ACPI power button event to the guest operating system.
             If the virtual machine is already powered off, no action is
             performed. Exceptions raised by run_vboxmanage are propagated.
    """
    state = get_virtual_machine_state(uuid)

    if state == "poweroff":
        return

    if state != "running":
        raise ValueError(f"Cannot gracefully shut down virtual machine {uuid!r} from state {state!r}.")

    run_vboxmanage(["controlvm",uuid,"acpipowerbutton"])


def poweroff_virtual_machine(uuid: str) -> None:
    """!
    @brief Force a virtual machine to power off.
    @param uuid UUID of the virtual machine.
    @exception ValueError If the virtual machine cannot be powered off from
                          its current state.
    @warning This operation is equivalent to removing power from a physical
             machine and may cause data loss or filesystem corruption.
    @details If the virtual machine is already powered off, no action is
             performed. Exceptions raised by run_vboxmanage are propagated.
    """
    state = get_virtual_machine_state(uuid)

    if state == "poweroff":
        return

    if state not in ("running", "paused"):
        raise ValueError(f"Cannot power off virtual machine {uuid!r} from state {state!r}.")

    run_vboxmanage(["controlvm",uuid,"poweroff",])


def pause_virtual_machine(uuid: str) -> None:
    """!
    @brief Pause a running virtual machine.
    @param uuid UUID of the virtual machine.
    @exception ValueError If the virtual machine cannot be paused from its
                          current state.
    @details If the virtual machine is already paused, no action is performed.
             Exceptions raised by run_vboxmanage are propagated.
    """
    state = get_virtual_machine_state(uuid)

    if state == "paused":
        return

    if state != "running":
        raise ValueError(f"Cannot pause virtual machine {uuid!r} from state {state!r}.")

    run_vboxmanage(["controlvm",uuid,"pause"])


def resume_virtual_machine(uuid: str) -> None:
    """!
    @brief Resume a paused virtual machine.
    @param uuid UUID of the virtual machine.
    @exception ValueError If the virtual machine cannot be resumed from its
                          current state.
    @details If the virtual machine is already running, no action is performed.
             Exceptions raised by run_vboxmanage are propagated.
    """
    state = get_virtual_machine_state(uuid)

    if state == "running":
        return

    if state != "paused":
        raise ValueError(f"Cannot resume virtual machine {uuid!r} from state {state!r}.")

    run_vboxmanage(["controlvm",uuid,"resume",])
