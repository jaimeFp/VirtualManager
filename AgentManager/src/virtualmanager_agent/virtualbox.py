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


def get_virtual_machine_inventory_details(uuid: str) -> dict[str, object]:
    """Return resource and network settings reported by VBoxManage."""
    information = get_virtual_machine_info(uuid)
    adapters = []
    for slot in range(1, 9):
        mode = information.get(f"nic{slot}", "none").lower()
        adapter_name = ""
        for key in (f"bridgeadapter{slot}", f"hostonlyadapter{slot}", f"intnet{slot}", f"nat-network{slot}", f"nicgenericdrv{slot}"):
            if key in information:
                adapter_name = information[key]
                break
        adapters.append({
            "slot": slot,
            "enabled": mode != "none",
            "mode": mode,
            "adapter": adapter_name,
            "cable_connected": information.get(f"cableconnected{slot}", "on").lower() == "on",
        })
    return {
        "memory_mb": int(information.get("memory", "0")),
        "cpu_count": int(information.get("cpus", "0")),
        "network_adapters": adapters,
    }


def configure_virtual_machine(uuid: str, configuration: dict[str, object]) -> None:
    """Apply CPU, memory and network settings to a powered-off VM."""
    if get_virtual_machine_state(uuid) != VM_STATE_POWEROFF:
        raise ValueError("La máquina debe estar apagada para cambiar su configuración.")
    memory_mb = configuration.get("memory_mb")
    cpu_count = configuration.get("cpu_count")
    adapters = configuration.get("network_adapters")
    if type(memory_mb) is not int or not 4 <= memory_mb <= 1_048_576:
        raise ValueError("La memoria debe estar entre 4 y 1 048 576 MB.")
    if type(cpu_count) is not int or not 1 <= cpu_count <= 256:
        raise ValueError("Los núcleos deben estar entre 1 y 256.")
    if not isinstance(adapters, list) or len(adapters) != 8:
        raise ValueError("Debes especificar las ocho interfaces de red.")
    arguments = ["modifyvm", uuid, "--memory", str(memory_mb), "--cpus", str(cpu_count)]
    option_by_mode = {"bridged": "bridgeadapter", "hostonly": "hostonlyadapter", "intnet": "intnet", "natnetwork": "nat-network", "generic": "nicgenericdrv"}
    allowed_modes = {"none", "null", "nat", "natnetwork", "bridged", "intnet", "hostonly", "generic"}
    for slot, adapter in enumerate(adapters, 1):
        if not isinstance(adapter, dict) or adapter.get("slot") != slot:
            raise ValueError("La configuración de interfaces de red no es válida.")
        enabled = adapter.get("enabled")
        mode = adapter.get("mode")
        name = adapter.get("adapter", "")
        if type(enabled) is not bool or mode not in allowed_modes or not isinstance(name, str):
            raise ValueError("La configuración de interfaces de red no es válida.")
        selected_mode = mode if enabled else "none"
        arguments.extend([f"--nic{slot}", selected_mode])
        adapter_option = option_by_mode.get(selected_mode)
        if adapter_option and name.strip():
            arguments.extend([f"--{adapter_option}{slot}", name.strip()])
        if isinstance(adapter.get("cable_connected"), bool):
            arguments.extend([f"--cableconnected{slot}", "on" if adapter["cable_connected"] else "off"])
    run_vboxmanage(arguments, timeout=60.0)


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
