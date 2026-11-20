"""Launch regressions using stdlib unittest; pytest is not required."""

import contextlib
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import unittest

import httpx

PROJECT = Path(__file__).resolve().parents[1]
SHARED_PYTHON = PROJECT / ".venv/bin/python"


@contextlib.contextmanager
def running_server(command, cwd):
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    environment = {**os.environ, "HOST": "127.0.0.1", "PORT": str(port), "PYTHONUNBUFFERED": "1"}
    process = subprocess.Popen(command, cwd=cwd, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    client = httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=1, trust_env=False)
    result = {"client": client, "logs": ""}
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise AssertionError("The server exited before becoming ready: " + process.communicate()[0])
            try:
                response = client.get("/")
                if response.status_code == 200:
                    break
            except httpx.TransportError:
                pass
            time.sleep(0.05)
        else:
            raise AssertionError("The server did not return HTTP 200 within ten seconds.")
        yield result
    finally:
        client.close()
        if process.poll() is None:
            process.terminate()
        try:
            result["logs"] = process.communicate(timeout=5)[0]
        except subprocess.TimeoutExpired:
            process.kill()
            result["logs"] = process.communicate(timeout=3)[0]


class RuntimeLaunchTests(unittest.TestCase):
    def check_application(self, client):
        page = client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Make your work", page.text)
        configuration = client.get("/api/config")
        self.assertEqual(configuration.status_code, 200)
        created = client.post("/api/practice", json={"context": configuration.json()["defaultContext"], "requestId": "shared-env-startup-smoke-001"})
        self.assertEqual(created.status_code, 200)
        practice = created.json()
        self.assertEqual(practice["pendingStage"], "roleplay")
        self.assertEqual(client.delete("/api/practice/" + practice["sessionId"]).status_code, 204)

    def test_direct_app_from_server_directory(self):
        with running_server([str(SHARED_PYTHON), "app.py"], PROJECT / "server") as result:
            self.check_application(result["client"])
        self.assertIn(str(SHARED_PYTHON), result["logs"])

    def test_launcher_from_another_directory_selects_shared_environment(self):
        base_python = getattr(sys, "_base_executable", sys.executable)
        with running_server([base_python, str(PROJECT / "run.py")], PROJECT / "server") as result:
            self.check_application(result["client"])
        self.assertIn(str(SHARED_PYTHON), result["logs"])

    def test_package_launch_from_project_directory(self):
        with running_server([str(SHARED_PYTHON), "-m", "server"], PROJECT) as result:
            self.check_application(result["client"])
        self.assertIn(str(SHARED_PYTHON), result["logs"])


if __name__ == "__main__":
    unittest.main()
