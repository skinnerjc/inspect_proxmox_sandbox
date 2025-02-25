from vmsandboxtest.vmsandbox_utils import setup_requests_logging, setup_sandbox


async def test_multiple_sandboxes(sandbox_env_config) -> None:
    setup_requests_logging()

    task_name = "sandbox_1_task"
    task_name, envs_dict = await setup_sandbox(task_name, sandbox_env_config)

    # Second time round, the sandbox should get a different SDN IP range
    task_name = "sandbox_2_task"
    task_name, envs_dict = await setup_sandbox(task_name, sandbox_env_config)
