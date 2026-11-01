"""Bounded capture of ONE already-authorized, fixture/host-owned child process.

No public CLI, executable resolution, approval issuance, retry or raw logging.
The supplied starter belongs to the trusted composition root, not agent input.
"""
from __future__ import annotations

import queue
import threading
import time


class CaptureError(RuntimeError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def bounded_capture(start, *, deadline, clock=time.monotonic):
    if clock() >= deadline:
        raise CaptureError("YC_READ_TIMEOUT")
    process = None
    failed = None
    try:
        process = start()
    except Exception:
        failed = "YC_READ_START_FAILED"
    if failed:
        raise CaptureError(failed)
    if process.stdout is None or process.stderr is None:
        process.kill()
        process.wait(timeout=5)
        raise CaptureError("YC_READ_PIPE_REQUIRED")
    messages = queue.Queue(maxsize=4)
    stop = threading.Event()

    def emit(item):
        while not stop.is_set():
            try:
                messages.put(item, timeout=0.05)
                return
            except queue.Full:
                pass

    def reader(name, stream):
        try:
            while not stop.is_set():
                chunk = stream.read(4096)
                if not chunk:
                    break
                emit((name, chunk))
        except Exception:
            emit(("error", None))
        finally:
            emit((name, None))

    threads = [threading.Thread(target=reader, args=(name, stream), daemon=True)
               for name, stream in (("stdout", process.stdout), ("stderr", process.stderr))]
    for thread in threads:
        thread.start()
    output, stderr_size, ended = bytearray(), 0, set()
    try:
        while len(ended) < 2:
            remaining = deadline - clock()
            if remaining <= 0:
                failed = "YC_READ_TIMEOUT"
                break
            try:
                name, chunk = messages.get(timeout=min(0.05, remaining))
            except queue.Empty:
                continue
            if name == "error":
                failed = "YC_READ_CAPTURE_FAILED"
                break
            if chunk is None:
                ended.add(name)
            elif type(chunk) is not bytes:
                failed = "YC_READ_BINARY_PIPE_REQUIRED"
                break
            elif name == "stdout":
                if len(output) + len(chunk) > 65536:
                    failed = "YC_READ_OUTPUT_LIMIT"
                    break
                output.extend(chunk)
            else:
                stderr_size += len(chunk)
                if stderr_size > 8192:
                    failed = "YC_READ_STDERR_LIMIT"
                    break
        if failed is None:
            remaining = deadline - clock()
            if remaining <= 0:
                failed = "YC_READ_TIMEOUT"
            else:
                try:
                    if process.wait(timeout=remaining) != 0:
                        failed = "YC_READ_EXIT_NONZERO"
                except Exception:
                    failed = "YC_READ_TIMEOUT"
    finally:
        stop.set()
        if process.poll() is None:
            # Only the child returned by this trusted starter; never search/kill by name.
            process.kill()
        try:
            process.wait(timeout=5)
        except Exception:
            failed = "YC_READ_CLEANUP_INCOMPLETE"
        for thread in threads:
            thread.join(timeout=1)
        # Inherited pipes held by grandchildren are outside this single-child profile.
        if any(thread.is_alive() for thread in threads):
            failed = "YC_READ_CLEANUP_INCOMPLETE"
        else:
            process.stdout.close()
            process.stderr.close()
    if failed:
        output.clear()
        raise CaptureError(failed)
    return bytes(output)
