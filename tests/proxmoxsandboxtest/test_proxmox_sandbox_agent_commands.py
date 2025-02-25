import subprocess
from typing import List

from inspect_ai.util._sandbox.self_check import self_check

from proxmoxsandboxtest.proxmox_sandbox_utils import setup_requests_logging, setup_sandbox


async def test_exec_10mb_limit(sandbox_env_config) -> None:
    task_name = "test_exec_10mb_limit"
    task_name, envs_dict = await setup_sandbox(task_name, sandbox_env_config)
    try:
        sandbox_env = envs_dict["default"]
        i = (
            pow(2, 20) * 10 - 1000
        )  # 10 MiB - 1000, there are vagaries around the extra from JSON marshalling
        print(f"Testing exec with {i} characters")
        exec_string = ["perl", "-E", "print 'a' x " + str(i)]

        expected = subprocess.run(exec_string, stdout=subprocess.PIPE).stdout.decode(
            "utf-8"
        )

        exec_result = await sandbox_env.exec(exec_string, timeout=60)
        assert len(exec_result.stdout) == len(expected)
        assert exec_result.stdout == expected
    finally:
        await cleanup_sandbox(task_name, envs_dict)


async def test_self_check(sandbox_env_config) -> None:
    setup_requests_logging()

    task_name = "test_self_check"
    task_name, envs_dict = await setup_sandbox(task_name, sandbox_env_config)

    known_failures: List[str] = [
        "test_read_file_not_allowed",  # user is root, so this doesn't work
        "test_write_text_file_without_permissions",  # user is root, so this doesn't work
        "test_write_binary_file_without_permissions",  # user is root, so this doesn't work
        "test_exec_as_user",  # user parameter not supported by proxmox API
        "test_exec_as_nonexistent_user",  # user parameter not supported by proxmox API
    ]

    return await check_results_of_self_check(task_name, envs_dict, known_failures)


async def check_results_of_self_check(task_name, envs_dict, known_failures=[]):
    sandbox_env = envs_dict["default"]

    try:
        self_check_results = await self_check(sandbox_env)
        failures = []
        for test_name, result in self_check_results.items():
            if result is not True and test_name not in known_failures:
                failures.append(f"Test {test_name} failed: {result}")
        if failures:
            assert False, "\n".join(failures)
    finally:
        await sandbox_env.sample_cleanup(
            task_name=task_name,
            config=None,
            environments=envs_dict,
            interrupted=False,
        )
        await sandbox_env.task_cleanup(task_name=task_name, config=None, cleanup=True)


async def cleanup_sandbox(task_name: str, envs_dict: dict):
    """Helper to cleanup sandbox environment"""
    for env in envs_dict.values():
        await env.sample_cleanup(
            task_name=task_name, config=None, environments=envs_dict, interrupted=False
        )
        await env.task_cleanup(task_name=task_name, config=None, cleanup=True)
