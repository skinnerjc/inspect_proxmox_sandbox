import subprocess
from typing import List

from inspect_ai.util._sandbox.self_check import self_check
from proxmoxsandboxtest.proxmox_sandbox_utils import (
    setup_requests_logging,
)

from proxmoxsandbox.inspect.proxmox_sandbox_environment import ProxmoxSandboxEnvironment


async def test_exec_10mb_limit(
    proxmox_sandbox_environment: ProxmoxSandboxEnvironment,
) -> None:
    i = (
        pow(2, 20) * 10 - 1000
    )  # 10 MiB - 1000, there are vagaries around the extra from JSON marshalling
    print(f"Testing exec with {i} characters")
    exec_string = ["perl", "-E", "print 'a' x " + str(i)]

    expected = subprocess.run(exec_string, stdout=subprocess.PIPE).stdout.decode(
        "utf-8"
    )

    exec_result = await proxmox_sandbox_environment.exec(exec_string, timeout=60)
    assert len(exec_result.stdout) == len(expected)
    assert exec_result.stdout == expected


async def test_self_check(
    proxmox_sandbox_environment: ProxmoxSandboxEnvironment,
) -> None:
    setup_requests_logging()

    known_failures: List[str] = [
        "test_read_file_not_allowed",  # user is root, so this doesn't work
        "test_write_text_file_without_permissions",  # user is root, so this doesn't work
        "test_write_binary_file_without_permissions",  # user is root, so this doesn't work
    ]

    return await check_results_of_self_check(
        proxmox_sandbox_environment, known_failures
    )


async def check_results_of_self_check(sandbox_env, known_failures=[]):
    self_check_results = await self_check(sandbox_env)
    failures = []
    for test_name, result in self_check_results.items():
        if result is not True and test_name not in known_failures:
            failures.append(f"Test {test_name} failed: {result}")
    if failures:
        assert False, "\n".join(failures)
