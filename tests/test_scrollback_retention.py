"""Regress unbounded recording through the Python and native public CLIs."""
import gzip
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import time
import unittest

TOOL = Path(__file__).resolve().parents[1] / 'tmux_background_output.py'
SEGMENT = 8 * 1024 * 1024
BUDGET = 256 * 1024 * 1024


class RetentionTests(unittest.TestCase):
    """Use fresh archive state and real gzip members for every regression."""

    def setUp(self):
        """Create isolated archive state.

        Parameters: self - fixture owner.
        Returns: None.
        """
        print(f'self={object.__repr__(self)}')
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        native = os.environ.get('TMUX_BACKGROUND_TOOL')
        self.command = [native] if native else [sys.executable, str(TOOL)]
        print(None)

    def tearDown(self):
        """Remove this test's archive directory.

        Parameters: self - fixture owner.
        Returns: None.
        """
        print(f'self={object.__repr__(self)}')
        self.temp.cleanup()
        print(None)

    def cli(self, *args, payload=None):
        """Run the installed-style public interface.

        Parameters: self - fixture owner; args - command operands; payload - input bytes or None.
        Returns: completed subprocess status and output.
        """
        print(f'self={object.__repr__(self)} args={args} payload={payload}')
        result = subprocess.run([*self.command, *args], input=payload, capture_output=True)
        print(result)
        return result

    def seed(self, index, data=b'old history', age=0):
        """Create a recorder-owned legacy archive.

        Parameters: self - fixture owner; index - unique sequence; data - raw history; age - elapsed seconds.
        Returns: created path.
        """
        print(f'self={object.__repr__(self)} index={index} data={data} age={age}')
        path = self.root / f'20261001T120000.{index:06}Z-deadbeef-output.gz'
        path.write_bytes(gzip.compress(data, mtime=0))
        os.utime(path, (time.time() - age, time.time() - age))
        print(path)
        return path

    def test_long_record_rotates_and_preserves_bytes(self):
        """Bound a single long run while retaining all history within the budget.

        Parameters: self - fixture owner.
        Returns: None.
        """
        print(f'self={object.__repr__(self)}')
        path = self.root / '20261001T120000.000001Z-output.gz'
        payload = random.Random(42).randbytes(20 * 1024 * 1024) + b'latest-marker\n'
        result = subprocess.run([*self.command, 'record', '--file', str(path)],
                                input=payload, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        files = sorted(self.root.glob('*.gz'))
        self.assertGreater(len(files), 1)
        self.assertTrue(all(p.stat().st_size <= SEGMENT for p in files))
        self.assertEqual(b''.join(gzip.decompress(p.read_bytes()) for p in files), payload)
        self.assertTrue(all(p.stat().st_mode & 0o777 == 0o600 for p in files))
        print(None)

    def test_prune_count_age_and_unrelated_files(self):
        """Retain recent files and leave unrelated content and symlinks alone.

        Parameters: self - fixture owner.
        Returns: None.
        """
        print(f'self={object.__repr__(self)}')
        expired = self.seed(0, age=8 * 86400)
        files = [self.seed(i) for i in range(1, 71)]
        unrelated = self.root / 'notes.gz'
        unrelated.write_bytes(b'user data')
        link = self.root / '20261001T120000.123456Z-link-output.gz'
        link.symlink_to(unrelated)
        for _ in range(2):
            result = self.cli('prune', '--archive-dir', str(self.root))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(expired.exists())
            self.assertLessEqual(sum(p.exists() for p in files), 64)
            self.assertEqual(gzip.decompress(files[-1].read_bytes()), b'old history')
            self.assertEqual(unrelated.read_bytes(), b'user data')
            self.assertTrue(link.is_symlink())
        print(None)

    def test_legacy_large_tail_and_incomplete_member(self):
        """Recover recent whole members without loading a huge legacy archive.

        Parameters: self - fixture owner.
        Returns: None.
        """
        print(f'self={object.__repr__(self)}')
        path = self.seed(1)
        member = gzip.compress(random.Random(43).randbytes(65536), compresslevel=1, mtime=0)
        with path.open('ab') as output:
            for _ in range(160):
                output.write(member)
            output.write(gzip.compress(b'latest-marker', mtime=0))
            output.write(gzip.compress(b'interrupted chunk', mtime=0)[:12])
        result = self.cli('prune', '--archive-dir', str(self.root))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLessEqual(path.stat().st_size, SEGMENT)
        self.assertTrue(gzip.decompress(path.read_bytes()).endswith(b'latest-marker'))
        print(None)

    def test_total_budget_and_record_cleans_old_runs(self):
        """Bound directory bytes and clean accumulated runs on recording itself.

        Parameters: self - fixture owner.
        Returns: None.
        """
        print(f'self={object.__repr__(self)}')
        member = gzip.compress(random.Random(44).randbytes(65536), compresslevel=1, mtime=0)
        for i in range(40):
            path = self.seed(i)
            with path.open('wb') as output:
                output.write(member * 127)
        expired = self.seed(100, age=8 * 86400)
        latest = self.root / '20261012T120000.000002Z-output.gz'
        result = self.cli('record', '--file', str(latest), payload=b'newest')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(expired.exists())
        self.assertLessEqual(sum(p.stat().st_size for p in self.root.glob('*.gz')), BUDGET)
        self.assertEqual(gzip.decompress(latest.read_bytes()), b'newest')
        print(None)

    def test_concurrent_recorders_preserve_members(self):
        """Serialize writers so concurrent appends keep every gzip member readable.

        Parameters: self - fixture owner.
        Returns: None.
        """
        print(f'self={object.__repr__(self)}')
        path = self.root / '20261001T120000.000004Z-output.gz'
        source = self.root / 'input.bin'
        payload = random.Random(45).randbytes(2 * 1024 * 1024)
        source.write_bytes(payload)
        processes = []
        try:
            for _ in range(2):
                with source.open('rb') as input_stream:
                    process = subprocess.Popen([*self.command, 'record', '--file', str(path)],
                                               stdin=input_stream, stdout=subprocess.DEVNULL,
                                               stderr=subprocess.PIPE)
                processes.append(process)
            for process in processes:
                _, error = process.communicate(timeout=20)
                self.assertEqual(process.returncode, 0, error)
            actual = gzip.decompress(path.read_bytes())
            self.assertEqual(len(actual), 2 * len(payload))
            self.assertEqual(sorted(actual), sorted(payload * 2))
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.wait()
        print(None)

    def test_rejections_preserve_existing_history(self):
        """Reject malformed retention commands without deleting existing bytes.

        Parameters: self - fixture owner.
        Returns: None.
        """
        print(f'self={object.__repr__(self)}')
        path = self.seed(1, data=b'preserved')
        for args in [('prune',), ('prune', '--archive-dir'),
                     ('prune', '--archive-dir', str(self.root), 'extra'),
                     ('prune', '--file', str(path))]:
            self.assertNotEqual(self.cli(*args).returncode, 0)
            self.assertEqual(gzip.decompress(path.read_bytes()), b'preserved')
        print(None)

    def test_live_writer_survives_pruned_path(self):
        """Reopen a retired path rather than write into an unlinked descriptor.

        Parameters: self - fixture owner.
        Returns: None.
        """
        print(f'self={object.__repr__(self)}')
        path = self.root / '20261012T120000.000003Z-output.gz'
        process = subprocess.Popen([*self.command, 'record', '--file', str(path)],
                                   stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 5
            while not path.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(path.exists())
            for i in range(70):
                self.seed(i)
            result = self.cli('prune', '--archive-dir', str(self.root))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(path.exists())
            _, error = process.communicate(b'still-recording', timeout=10)
            self.assertEqual(process.returncode, 0, error)
            self.assertEqual(gzip.decompress(path.read_bytes()), b'still-recording')
            self.assertLessEqual(len(list(self.root.glob('*.gz'))), 64)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
        print(None)


if __name__ == '__main__':
    unittest.main()
