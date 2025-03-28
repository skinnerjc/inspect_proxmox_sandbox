import hashlib
import subprocess
from pathlib import Path
from typing import List

from inspect_ai.util._sandbox.self_check import self_check

from proxmoxsandbox._proxmox_sandbox_environment import ProxmoxSandboxEnvironment

from .proxmox_sandbox_utils import setup_requests_logging


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


CURRENT_DIR = Path(__file__).parent


async def test_write_file_large(
    proxmox_sandbox_environment: ProxmoxSandboxEnvironment,
) -> None:
    with open(CURRENT_DIR / ".." / "oVirtTinyCore64-13.11.ova", "rb") as ova:
        file_contents = ova.read()
        # calculate md5sum of the file
        md5 = hashlib.md5()
        md5.update(file_contents)
        expected_md5 = md5.hexdigest()
        assert expected_md5 == "b6059a0fec3d0e431531abeabff212fe"
        await proxmox_sandbox_environment.write_file(
            "oVirtTinyCore64-13.11.ova", file_contents
        )
    exec_result = await proxmox_sandbox_environment.exec(
        ["md5sum", "oVirtTinyCore64-13.11.ova"]
    )
    assert (
        exec_result.stdout
        == "b6059a0fec3d0e431531abeabff212fe  oVirtTinyCore64-13.11.ova\n"
    )


async def test_self_check(
    proxmox_sandbox_environment: ProxmoxSandboxEnvironment,
) -> None:
    setup_requests_logging()

    known_failures: List[str] = [
        "test_read_file_not_allowed",  # user is root, so this doesn't work
        "test_write_text_file_without_permissions",  # ditto
        "test_write_binary_file_without_permissions",  # ditto
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
