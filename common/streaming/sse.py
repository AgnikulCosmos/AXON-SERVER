import sys
import re
import contextvars
from io import StringIO
from typing import Optional

task_stdout = contextvars.ContextVar("task_stdout", default=None)


class TaskLocalStdout:
    def write(self, data):
        buf = task_stdout.get()
        if buf is not None:
            buf.write(data)
        else:
            sys.__stdout__.write(data)

    def flush(self):
        buf = task_stdout.get()
        if buf is not None:
            buf.flush()
        else:
            sys.__stdout__.flush()

    def isatty(self):
        return sys.__stdout__.isatty()

    @property
    def encoding(self):
        return sys.__stdout__.encoding

    @property
    def errors(self):
        return sys.__stdout__.errors


def install_stdout_proxy():
    sys.stdout = TaskLocalStdout()


def clean_line(line: str) -> str:
    line = re.sub(r'^\s*event:\s*', '', line)
    # Strip any stray marker tokens that may appear inline in content
    line = re.sub(r'<<<[A-Z_]+>>>', '', line)
    return line.replace("\x00", "").replace("\r", "").replace("\n", "").strip()


def sse_event(data: str, event_type: Optional[str] = None) -> str:
    safe = data.replace("\x00", "").replace("\r", "")
    if event_type:
        return f"event: {event_type}\ndata: {safe}\n\n"
    return f"data: {safe}\n\n"
