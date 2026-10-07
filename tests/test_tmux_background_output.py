"""Exercise background output preservation through its CLI and private tmux."""

import gzip
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

TOOL = Path(__file__).resolve().parents[1] / "tmux_background_output.py"


class BackgroundOutputTests(unittest.TestCase):
    """Use fresh directories and an isolated tmux server for each case."""

    def setUp(self):
        """Create independent fixture state.

        Parameters: self - the test instance.
        Returns: None.
        """
        print(f"self={object.__repr__(self)}")
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.socket = self.root / "tmux.sock"
        self.env = dict(os.environ, TMUX=f"{self.socket},0,0")
        self.env.pop("TMUX_PANE", None)
        print(None)

    def tearDown(self):
        """Remove only this case's server and directory.

        Parameters: self - the test instance.
        Returns: None.
        """
        print(f"self={object.__repr__(self)}")
        subprocess.run(["tmux", "-S", str(self.socket), "kill-server"], capture_output=True)
        self.tmp.cleanup()
        print(None)

    def tmux(self, *args):
        """Invoke the isolated server.

        Parameters: self - fixture owner; args - tmux arguments.
        Returns: stripped command output.
        """
        print(f"self={object.__repr__(self)} args={args}")
        result = subprocess.check_output(["tmux", "-S", str(self.socket), *args], text=True).strip()
        print(result)
        return result

    def cli(self, *args, payload=None):
        """Call the public recorder interface.

        Parameters: self - fixture owner; args - CLI arguments; payload - optional stdin bytes.
        Returns: completed subprocess result.
        """
        print(f"self={object.__repr__(self)} args={args} payload={payload}")
        result = subprocess.run([sys.executable, str(TOOL), *args], input=payload,
                                capture_output=True, env=self.env)
        print(result)
        return result

    def archives(self, marker):
        """Wait for a marker in complete recorded gzip members.

        Parameters: self - fixture owner; marker - expected final bytes.
        Returns: all currently archived bytes.
        """
        print(f"self={object.__repr__(self)} marker={marker}")
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            try:
                result = b"".join(gzip.decompress(path.read_bytes())
                                  for path in sorted(self.root.glob("*.gz")))
                if marker in result:
                    print(result)
                    return result
            except (EOFError, gzip.BadGzipFile):
                pass
            time.sleep(0.05)
        self.fail(f"Missing archived marker {marker!r}")

    def test_record(self):
        """Preserve arbitrary bytes in a readable private gzip archive.

        Parameters: self - the test instance.
        Returns: None.
        """
        print(f"self={object.__repr__(self)}")
        path = self.root / "binary bytes.gz"
        payload = bytes(range(256)) * 600
        result = self.cli("record", "--file", str(path), payload=payload)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(gzip.decompress(path.read_bytes()), payload)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        empty = self.root / "empty.gz"
        self.assertEqual(self.cli("record", "--file", str(empty), payload=b"").returncode, 0)
        self.assertEqual(subprocess.run(["gzip", "-t", str(empty)], capture_output=True).returncode, 0)
        print(None)

    def test_rejections(self):
        """Reject malformed commands before creating archives or a server.

        Parameters: self - the test instance.
        Returns: None.
        """
        print(f"self={object.__repr__(self)}")
        for args in ((), ("unknown",), ("record",), ("record", "--file", str(self.root / "x"), "extra"),
                     ("start", "--target", "demo:app"),
                     ("start", "--target", "demo:app", "--archive-dir", str(self.root))):
            self.assertNotEqual(self.cli(*args).returncode, 0)
            self.assertFalse(self.socket.exists())
            self.assertFalse(list(self.root.glob("*.gz")))
        print(None)

    def test_background(self):
        """Bound background history, archive old/new output, and retain agents.

        Parameters: self - the test instance.
        Returns: None.
        """
        print(f"self={object.__repr__(self)}")
        self.tmux("new-session", "-d", "-s", "demo", "-n", "agent", "sleep 1000")
        self.tmux("set-option", "-g", "history-limit", "2147483647")
        self.tmux("new-window", "-d", "-t", "demo", "-n", "app", "printf 'old-marker\\n'; sleep 1000")
        time.sleep(0.1)
        agent = self.tmux("display-message", "-p", "-t", "demo:agent", "#{pane_id}:#{history_limit}")
        self.tmux("set-window-option", "-t", "demo:app", "remain-on-exit", "on")
        command = "printf '\\033[31m'; seq 1 8000; printf 'first-end\\n'; sleep 1000"
        result = self.cli("start", "--target", "demo:app", "--archive-dir", str(self.root), "--cwd", str(self.root), "--", "bash", "-c", command)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = self.archives(b"first-end")
        self.assertIn(b"old-marker", data)
        self.assertIn(b"\x1b[31m", data)
        for i in range(1, 8001):
            self.assertIn(f"{i}\r\n".encode(), data)
        limit, size, pane = self.tmux("display-message", "-p", "-t", "demo:app", "#{history_limit} #{history_size} #{pane_id}").split()
        self.assertEqual(self.tmux("display-message", "-p", "-t", "demo:app", "#{pane_current_path}"), str(self.root))
        self.assertEqual(limit, "2000")
        self.assertLessEqual(int(size), 2000)
        self.assertEqual(self.tmux("show-option", "-gv", "history-limit"), "2147483647")
        self.assertEqual(self.tmux("display-message", "-p", "-t", "demo:agent", "#{pane_id}:#{history_limit}"), agent)
        result = self.cli("start", "--target", "demo:app", "--archive-dir", str(self.root), "--", "bash", "-c", "printf 'second-end\\n'; sleep 1000")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.archives(b"second-end")
        self.assertEqual(self.tmux("display-message", "-p", "-t", "demo:app", "#{pane_id}"), pane)
        result = self.cli("start", "--target", "demo:fresh", "--archive-dir", str(self.root), "--", "bash", "-c", "printf 'fresh-end\\n'; sleep 1000")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.archives(b"fresh-end")
        self.assertEqual(self.tmux("display-message", "-p", "-t", "demo:fresh", "#{history_limit}"), "2000")
        print(None)

    def test_multiple_panes(self):
        """Leave a multipane window intact on a rejected replacement.

        Parameters: self - the test instance.
        Returns: None.
        """
        print(f"self={object.__repr__(self)}")
        self.tmux("new-session", "-d", "-s", "demo", "-n", "app", "sleep 1000")
        self.tmux("split-window", "-d", "-t", "demo:app", "sleep 1000")
        before = self.tmux("list-panes", "-t", "demo:app", "-F", "#{pane_id}:#{pane_start_command}")
        result = self.cli("start", "--target", "demo:app", "--archive-dir", str(self.root), "--", "sleep", "1000")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.tmux("list-panes", "-t", "demo:app", "-F", "#{pane_id}:#{pane_start_command}"), before)
        result = self.cli("start", "--target", "demo:app", "--archive-dir", str(self.root), "--cwd", str(self.root / "missing"), "--", "sleep", "1000")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.tmux("list-panes", "-t", "demo:app", "-F", "#{pane_id}:#{pane_start_command}"), before)
        print(None)


if __name__ == "__main__":
    unittest.main()
