"""
Oz Agent SDK wrapper for dispatching tasks to Oz environments.

Supports dynamic credentials per-request for multi-tenant gateway usage.
"""
import os
import time
import logging
from urllib.parse import urlparse
from oz_agent_sdk import OzAPI

logger = logging.getLogger(__name__)

# Terminal states for task polling (Oz SDK uses SUCCEEDED instead of COMPLETED)
TERMINAL_STATES = {"SUCCEEDED", "FAILED", "CANCELLED", "ERROR"}
DEFAULT_OZ_API_BASE_URL = "https://app.warp.dev/api/v1"


def get_default_oz_api_base_url() -> str:
    """Return the default Oz API base URL for clients that omit one."""
    return os.environ.get("OZ_API_BASE_URL", DEFAULT_OZ_API_BASE_URL)


class WarpAgentClient:
    """
    Client for invoking Oz agents.
    
    Accepts credentials at initialization time, enabling per-bot configurations.
    """

    def __init__(
        self,
        api_key: str,
        environment_id: str,
        base_url: str | None = None,
        mcp_servers: dict | None = None,
    ):
        """
        Initialize an Oz agent client.
        
        Args:
            api_key: Warp API key
            environment_id: Oz cloud environment ID to run tasks in
            base_url: Oz API base URL
            mcp_servers: Optional dict of MCP server configurations
        """
        if not api_key:
            raise ValueError("api_key is required")
        if not environment_id:
            raise ValueError("environment_id is required")
        
        self.api_key = api_key
        self.environment_id = environment_id
        self.base_url = base_url or get_default_oz_api_base_url()
        self.mcp_servers = mcp_servers

        self.client = OzAPI(
            api_key=self.api_key,
            base_url=self.base_url,
        )

    def _build_run_link(self, run_id: str) -> str | None:
        """Construct an Oz run URL for the configured API host."""
        parsed = urlparse(self.base_url)
        if not parsed.scheme or not parsed.hostname:
            return None

        hostname = parsed.hostname
        if hostname == "app.warp.dev":
            hostname = "oz.warp.dev"
        elif hostname.startswith("api."):
            hostname = hostname[4:]
        if not hostname.startswith("oz."):
            hostname = f"oz.{hostname}"

        netloc = hostname
        if parsed.port:
            netloc = f"{hostname}:{parsed.port}"

        return f"{parsed.scheme}://{netloc}/runs/{run_id}"

    def _refresh_terminal_run(self, run_id: str, run, max_attempts: int = 5, poll_interval: float = 1.0):
        """Retry a terminal run briefly so delayed session links have time to populate."""
        if run.session_link:
            return run

        latest_run = run
        for _ in range(max_attempts):
            time.sleep(poll_interval)
            latest_run = self.client.agent.runs.retrieve(run_id)
            if latest_run.session_link:
                logger.info(f"Run {run_id} session link became available after terminal state")
                return latest_run

        return latest_run

    def submit_task(
        self,
        prompt: str,
        skill_spec: str | None = None,
        startup_timeout: float = 0.0,
        startup_poll_interval: float = 1.0,
    ) -> dict:
        """
        Submit a task and return immediately with task info.
        
        Note: session_link is not available on the initial run response in Oz SDK,
        so we do an immediate retrieve to get it.
        
        Args:
            prompt: The task prompt to send to the agent
            skill_spec: Optional skill spec (e.g. "owner/repo:skill-name")
            startup_timeout: Optional seconds to wait for an initial session link or
                terminal state
            startup_poll_interval: Seconds between startup checks when startup_timeout is set
            
        Returns:
            dict with run_id, session_link, and initial state
        """
        logger.info("Submitting task to Oz agent: prompt_length=%s", len(prompt))
        
        config = {
            "environment_id": self.environment_id,
        }
        if self.mcp_servers:
            config["mcp_servers"] = self.mcp_servers
        if skill_spec:
            config["skill_spec"] = skill_spec
        
        response = self.client.agent.run(
            prompt=prompt,
            config=config,
        )
        
        run_id = response.run_id
        logger.info(f"Task submitted: run_id={run_id}")
        
        # Retrieve immediately to get session_link (not available on run response)
        run_info = self.client.agent.runs.retrieve(run_id)
        if startup_timeout > 0:
            deadline = time.time() + startup_timeout
            while (
                not run_info.session_link
                and run_info.state not in TERMINAL_STATES
                and time.time() < deadline
            ):
                time.sleep(startup_poll_interval)
                run_info = self.client.agent.runs.retrieve(run_id)

        session_link = run_info.session_link
        run_link = self._build_run_link(run_id)
        status_msg = ""
        status_message = getattr(run_info, "status_message", None)
        if status_message:
            status_msg = status_message.message
        
        logger.info(
            "Task info retrieved: run_id=%s, state=%s, session_link=%s, run_link=%s",
            run_id,
            run_info.state,
            session_link,
            run_link,
        )
        
        return {
            "run_id": run_id,
            "task_id": run_id,  # For backwards compatibility
            "session_link": session_link,
            "run_link": run_link,
            "state": run_info.state,
            "status_message": status_msg,
        }
    
    def poll_task(
        self,
        run_id: str,
        poll_interval: float = 5.0,
        timeout: float = 600.0,
        on_status_update: callable = None,
    ) -> dict:
        """
        Poll an existing run until completion.
        
        Args:
            run_id: The run ID to poll
            poll_interval: Seconds between status checks
            timeout: Max seconds to wait for completion
            on_status_update: Callback function(run) called on each poll
            
        Returns:
            dict with run_id, state, status_message, session_link, artifacts
        """
        start_time = time.time()
        last_status = None
        last_session_link = None
        run = None
        
        while time.time() - start_time < timeout:
            run = self.client.agent.runs.retrieve(run_id)
            
            logger.debug(f"Run {run_id} state: {run.state!r}")
            
            current_status = run.status_message.message if run.status_message else None
            current_session_link = run.session_link
            if on_status_update and (
                current_status != last_status or current_session_link != last_session_link
            ):
                on_status_update(run)
                last_status = current_status
                last_session_link = current_session_link
            
            if run.state in TERMINAL_STATES:
                run = self._refresh_terminal_run(run_id, run)
                logger.info(f"Run {run_id} completed with state: {run.state}")
                
                status_msg = ""
                if run.status_message:
                    status_msg = run.status_message.message
                
                return {
                    "run_id": run_id,
                    "task_id": run_id,  # For backwards compatibility
                    "state": run.state,
                    "status_message": status_msg,
                    "session_link": run.session_link,
                    "run_link": self._build_run_link(run_id),
                    "artifacts": run.artifacts,
                }
            
            time.sleep(poll_interval)
        
        # Timeout
        elapsed = time.time() - start_time
        final_state = run.state if run else 'unknown'
        logger.warning(f"Run {run_id} polling timed out after {elapsed:.1f}s, last state: {final_state}")
        
        status_msg = ""
        if run and run.status_message:
            status_msg = run.status_message.message
        
        return {
            "run_id": run_id,
            "task_id": run_id,  # For backwards compatibility
            "state": final_state if final_state in TERMINAL_STATES else "TIMEOUT",
            "status_message": status_msg,
            "session_link": run.session_link if run else None,
            "run_link": self._build_run_link(run_id),
            "artifacts": run.artifacts if run else None,
        }

    def run_task(
        self,
        prompt: str,
        wait_for_completion: bool = True,
        poll_interval: float = 5.0,
        timeout: float = 600.0,
        on_status_update: callable = None,
    ) -> dict:
        """
        Run a task on the Oz agent platform.

        Args:
            prompt: The task prompt to send to the agent
            wait_for_completion: If True, poll until task completes
            poll_interval: Seconds between status checks
            timeout: Max seconds to wait for completion
            on_status_update: Callback function(task) called on each poll

        Returns:
            dict with task_id, state, and status_message
        """
        try:
            submit_result = self.submit_task(prompt)
            run_id = submit_result["run_id"]

            if not wait_for_completion:
                return submit_result

            return self.poll_task(
                run_id=run_id,
                poll_interval=poll_interval,
                timeout=timeout,
                on_status_update=on_status_update,
            )

        except Exception as e:
            logger.error(f"Failed to run task: {e}")
            raise


def create_warp_client(
    api_key: str,
    environment_id: str,
    base_url: str | None = None,
    mcp_servers: dict | None = None,
) -> WarpAgentClient:
    """
    Create an Oz agent client with the given credentials.
    
    Args:
        api_key: Warp API key
        environment_id: Oz cloud environment ID
        base_url: Oz API base URL
        mcp_servers: Optional dict of MCP server configurations
        
    Returns:
        Configured WarpAgentClient instance
    """
    return WarpAgentClient(
        api_key=api_key,
        environment_id=environment_id,
        base_url=base_url,
        mcp_servers=mcp_servers,
    )
