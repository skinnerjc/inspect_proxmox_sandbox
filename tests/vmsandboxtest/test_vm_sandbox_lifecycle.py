from vmsandbox.inspect.vm_sandbox_environment import VmSandboxEnvironment
from vmsandboxtest.vmsandbox_utils import setup_requests_logging, setup_sandbox


async def test_smoke(sandbox_env_config) -> None:
    task_name = "sandbox_test_smoketask"
    task_name, envs_dict = await setup_sandbox(task_name, sandbox_env_config)


async def test_multiple_sandboxes(sandbox_env_config) -> None:
    setup_requests_logging()

    sandboxes = {}

    try:
        task_name = "sandbox_1_task"
        task_name, envs_dict = await setup_sandbox(task_name, sandbox_env_config)
        sandboxes["first"] = envs_dict["default"]

        # Second time round, the sandbox should get a different SDN IP range
        task_name = "sandbox_2_task"
        task_name, envs_dict = await setup_sandbox(task_name, sandbox_env_config)
        sandboxes["second"] = envs_dict["default"]
    finally:
        VmSandboxEnvironment.sample_cleanup(
            task_name="unused", config=sandbox_env_config, environments=sandboxes, interrupted=False
        )
