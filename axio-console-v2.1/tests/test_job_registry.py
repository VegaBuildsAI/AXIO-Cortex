"""Background-jobs registry: register/list/stop/tail for detached dev-server jobs."""
import subprocess
import sys
import time

from core.code_tools import job_registry


def _spawn_sleeper() -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])


def test_register_list_and_stop_job():
    job_registry.clear()
    proc = _spawn_sleeper()
    try:
        job_id = job_registry.register(
            pid=proc.pid, script="dev", workspace="C:/tmp/ws",
            log_path="C:/tmp/ws/.axio-dev-dev.log", proc=proc,
        )
        jobs = job_registry.list_jobs()
        match = [j for j in jobs if j["id"] == job_id]
        assert match, "registered job should be listed"
        assert match[0]["status"] == "running"
        assert match[0]["script"] == "dev"

        job_registry.stop(job_id)
        proc.wait(timeout=10)
        stopped = [j for j in job_registry.list_jobs() if j["id"] == job_id]
        assert stopped and stopped[0]["status"] == "stopped"
    finally:
        if proc.poll() is None:
            proc.kill()
        job_registry.clear()


def test_stop_unknown_job_raises():
    job_registry.clear()
    try:
        job_registry.stop("does-not-exist")
        assert False, "expected KeyError"
    except KeyError:
        pass


def test_tail_log_missing_file_is_graceful():
    job_registry.clear()
    job_id = job_registry.register(
        pid=None, script="dev", workspace="C:/tmp/ws",
        log_path="C:/tmp/ws/nope.log", proc=None,
    )
    assert "log unavailable" in job_registry.tail_log(job_id)
    job_registry.clear()
