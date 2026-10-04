import time

import pytest

from conftest import make_fixture_root
from judgeguard import config, sandbox_runner

pytestmark = pytest.mark.usefixtures("require_sandbox")

PASSING = "def f():\n    return 1\n"
TEST = "from solution import f\n\n\ndef test_f():\n    assert f() == 1\n"


def leftovers(tmp_root):
    return [p.name for p in tmp_root.iterdir() if p.name.startswith("jg-job-")]


def alive(pid):
    try:
        with open(f"/proc/{pid}/stat") as fh:
            return fh.read().rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        return False


@pytest.fixture
def scratch(tmp_path):
    tmp_root = tmp_path / "scratch"
    tmp_root.mkdir()
    return tmp_root


def run(tmp_path, scratch, c1, c2=PASSING, test=TEST, cid="probe-c1"):
    root = make_fixture_root(tmp_path / "fx", "probe", c1, c2, test)
    return sandbox_runner.run_candidate("probe", cid, "base", fixtures_root=root, tmp_root=scratch)


def test_pass_and_fail_are_reported_with_per_test_outcomes(tmp_path, scratch):
    result = run(tmp_path, scratch, PASSING, c2="def f():\n    return 2\n")
    assert result["status"] == "PASS" and result["counts"]["passed"] == 1
    assert result["tests"] == [{"name": "test_f", "outcome": "passed"}]
    failing = sandbox_runner.run_candidate("probe", "probe-c2", "base", fixtures_root=tmp_path / "fx", tmp_root=scratch)
    assert failing["status"] == "FAIL" and failing["tests"] == [{"name": "test_f", "outcome": "failed"}]
    assert leftovers(scratch) == []


def test_import_error_is_an_execution_error(tmp_path, scratch):
    result = run(tmp_path, scratch, "X = UNDEFINED\n\n\ndef f():\n    return 1\n")
    assert result["status"] == "ERROR" and "exit code" in result["error"]
    assert leftovers(scratch) == []


def test_timeout_kills_child_processes_and_removes_temp_files(tmp_path, scratch, monkeypatch):
    monkeypatch.setitem(config.SANDBOX, "exec_timeout_s", 2)
    pid_file = tmp_path / "child.pid"
    hang = (
        "import subprocess, sys\n\n\n"
        "def f():\n"
        "    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
        f"    open({str(pid_file)!r}, 'w').write(str(child.pid))\n"
        "    while True:\n"
        "        pass\n"
    )
    started = time.monotonic()
    result = run(tmp_path, scratch, hang)
    assert result["status"] == "TIMEOUT"
    assert time.monotonic() - started < 10
    child = int(pid_file.read_text())
    deadline = time.monotonic() + 5
    while alive(child) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not alive(child)
    assert leftovers(scratch) == []


def test_output_is_bounded(tmp_path, scratch):
    noisy = "def f():\n    print('x' * 200000)\n    return 2\n"
    result = run(tmp_path, scratch, noisy)
    assert result["status"] == "FAIL"
    assert len(result["output_tail"].encode()) <= config.SANDBOX["max_output_bytes"]


def test_runaway_file_write_is_stopped_by_the_file_size_limit(tmp_path, scratch):
    writer = (
        "def f():\n"
        "    with open('big.bin', 'wb') as fh:\n"
        "        fh.write(b'0' * (8 * 1024 * 1024))\n"
        "    return 1\n"
    )
    result = run(tmp_path, scratch, writer)
    assert result["status"] != "PASS"
    assert leftovers(scratch) == []


def test_child_environment_does_not_inherit_worker_variables(tmp_path, scratch, monkeypatch):
    monkeypatch.setenv("JG_SECRET_LOOKING_VALUE", "do-not-leak")
    probe = "import os\n\n\ndef f():\n    return 1 if 'JG_SECRET_LOOKING_VALUE' not in os.environ else 0\n"
    assert run(tmp_path, scratch, probe)["status"] == "PASS"
