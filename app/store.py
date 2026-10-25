"""Atomic JSON store with cross-process locking and corruption recovery."""
from __future__ import annotations

import contextlib
import json
import os
import shutil
import tempfile

from . import normalize
from .model import default_data, now_iso

try:
    import fcntl
except ImportError:  # non-POSIX fallback: no advisory lock
    fcntl = None


class StoreError(RuntimeError):
    pass


def resolve_home(explicit=None):
    home = explicit or os.environ.get("KANBAN_HOME") or os.path.join(os.path.expanduser("~"), ".kanban")
    home = os.path.abspath(os.path.expanduser(home))
    return home


class Store:
    def __init__(self, home=None):
        self.home = resolve_home(home)
        os.makedirs(self.home, mode=0o700, exist_ok=True)
        self.data_path = os.path.join(self.home, "data.json")
        self.backup_path = os.path.join(self.home, "data.json.bak")
        self.lock_path = os.path.join(self.home, ".lock")
        self.server_path = os.path.join(self.home, "server.json")
        self.log_path = os.path.join(self.home, "server.log")

    @contextlib.contextmanager
    def locked(self):
        fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            if fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            try:
                if fcntl is not None:
                    fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)

    def load(self):
        if not os.path.exists(self.data_path):
            return normalize.ensure_data(default_data())
        try:
            with open(self.data_path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
            return normalize.ensure_data(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            return self._recover(error)

    def _recover(self, error):
        stamp = now_iso().replace(":", "").replace("-", "")
        corrupt = os.path.join(self.home, "data.corrupt-%s.json" % stamp)
        shutil.copy2(self.data_path, corrupt)
        if os.path.exists(self.backup_path):
            shutil.copy2(self.backup_path, self.data_path)
            try:
                with open(self.data_path, "r", encoding="utf-8") as handle:
                    raw = json.load(handle)
                recovered = normalize.ensure_data(raw)
                recovered["meta"]["recovered_from"] = corrupt
                self.save(recovered)
                return recovered
            except Exception:
                pass
        raise StoreError("corrupt data file %s (copy kept at %s): %s" %
                         (self.data_path, corrupt, error))

    def save(self, data):
        data.setdefault("meta", {})["saved_at"] = now_iso()
        directory = os.path.dirname(self.data_path)
        fd, temp_path = tempfile.mkstemp(prefix=".data-", suffix=".json", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, ensure_ascii=False, sort_keys=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temp_path, 0o600)
            if os.path.exists(self.data_path):
                shutil.copy2(self.data_path, self.backup_path)
                os.chmod(self.backup_path, 0o600)
            os.replace(temp_path, self.data_path)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
        return data

    def read(self):
        """Read without the lock; atomic replace keeps the snapshot coherent."""
        return self.load()

    def signature(self):
        """Cheap change token based on the atomically replaced data file."""
        try:
            stat = os.stat(self.data_path)
        except OSError:
            return None
        return "%d:%d" % (stat.st_mtime_ns, stat.st_size)

    def mutate(self, operation):
        """Run operation(data) under an exclusive lock, then persist."""
        with self.locked():
            data = self.load()
            result = operation(data)
            self.save(data)
            return result

    def initialize(self):
        if not os.path.exists(self.data_path):
            self.mutate(lambda data: data)
        return self.load()

    def write_server_info(self, info):
        fd, temp_path = tempfile.mkstemp(prefix=".server-", suffix=".json", dir=self.home)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(info, handle, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temp_path, 0o600)
            os.replace(temp_path, self.server_path)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def read_server_info(self):
        if not os.path.exists(self.server_path):
            return None
        try:
            with open(self.server_path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except (json.JSONDecodeError, OSError):
            return None

    def clear_server_info(self):
        if os.path.exists(self.server_path):
            os.unlink(self.server_path)
