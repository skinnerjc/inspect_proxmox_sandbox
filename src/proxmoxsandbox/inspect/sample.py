
from inspect_ai import Task, eval, task
from inspect_ai.dataset import Sample
from inspect_ai.model import ModelOutput, get_model
from inspect_ai.scorer import exact
from inspect_ai.solver import chain, generate, use_tools
from inspect_ai.tool import bash

from proxmoxsandbox.inspect.schema import VmConfig
from proxmoxsandbox.inspect.proxmox_sandbox_environment import (
    ProxmoxSandboxEnvironmentConfig,
)


@task
def hello_world():
    return Task(
        dataset=[
            Sample(
                input="Use your bash tool to return the result of `uname -a`. Do not return any other text in your answer apart from the result.",
                target="Linux localhost 6.1.0-31-amd64 #1 SMP PREEMPT_DYNAMIC Debian 6.1.128-1 (2025-02-07) x86_64 GNU/Linux",
            )
        ],
        solver=chain(use_tools(bash(timeout=120)), generate()),
        scorer=exact(),
        sandbox=(
            "vm",
            ProxmoxSandboxEnvironmentConfig(
                host="localhost",
                port=11002,
                user="root",
                user_realm="pam",
                password="Password2.0",
                vms_config = (
                    VmConfig(backup_name="vzdump-qemu-102-2025_02_11-10_28_43.vma.zst", is_sandbox=False),
                    VmConfig(backup_name="vzdump-qemu-104-2025_02_12-10_25_34.vma.zst"),
                )
            ),
        ),
    )


if __name__ == "__main__":
    eval(
        tasks=hello_world(),
        model=get_model(
            "mockllm/model",
            custom_outputs=[
                # ModelOutput.for_tool_call(
                #     "mockllm/model",
                #     tool_name=bash.__name__,
                #     tool_arguments={"cmd": "apt install -y nmap"},
                # ),
                ModelOutput.for_tool_call(
                    "mockllm/model",
                    tool_name=bash.__name__,
                    tool_arguments={"cmd": "/usr/bin/nmap 192.168.16.0/24 -p8080"},
                ),
            ],
        ),
        message_limit=3,
        log_level="trace",
        sandbox_cleanup=False,
    )
