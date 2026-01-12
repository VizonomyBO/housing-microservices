from __future__ import annotations

import asyncio
import dataclasses
import json
import subprocess
import time
from typing import Literal

# Mirrors langchain-sandbox minimal execution flow without importing langchain-core.

PKG_NAME = "jsr:@langchain/pyodide-sandbox@0.0.4"


def _build_permission_flag(flag: str, *, value: bool | list[str]) -> str | None:
    if value is True:
        return flag
    if isinstance(value, list) and value:
        return f"{flag}={','.join(value)}"
    return None


@dataclasses.dataclass(kw_only=True)
class CodeExecutionResult:
    result: object | None = None
    stdout: str | None = None
    stderr: str | None = None
    status: Literal["success", "error"] = "success"
    execution_time: float | None = None
    session_metadata: dict | None = None
    session_bytes: bytes | None = None


class PyodideSandbox:
    def __init__(
        self,
        *,
        stateful: bool = False,
        allow_env: list[str] | bool = False,
        allow_read: list[str] | bool = False,
        allow_write: list[str] | bool = False,
        allow_net: list[str] | bool = True,
        allow_run: list[str] | bool = False,
        allow_ffi: list[str] | bool = False,
        node_modules_dir: str = "auto",
    ) -> None:
        self.stateful = stateful
        self.permissions: list[str] = []
        try:
            subprocess.run(["deno", "--version"], check=True, capture_output=True)
        except FileNotFoundError as exc:  # pragma: no cover - environment issue
            msg = "Deno is not installed or not in PATH."
            raise RuntimeError(msg) from exc
        except subprocess.CalledProcessError as exc:  # pragma: no cover
            msg = "Deno is installed, but running it failed."
            raise RuntimeError(msg) from exc

        perm_defs = [
            ("--allow-env", allow_env, None),
            ("--allow-read", allow_read, ["node_modules"]),
            ("--allow-write", allow_write, ["node_modules"]),
            ("--allow-net", allow_net, None),
            ("--allow-run", allow_run, None),
            ("--allow-ffi", allow_ffi, None),
        ]
        for flag, value, defaults in perm_defs:
            perm = _build_permission_flag(flag, value=value)
            if perm is None and defaults is not None:
                perm = f"{flag}={','.join(defaults)}"
            if perm:
                self.permissions.append(perm)
        self.permissions.append(f"--node-modules-dir={node_modules_dir}")

    def _build_command(
        self,
        code: str,
        session_bytes: bytes | None = None,
        session_metadata: dict | None = None,
        memory_limit_mb: int | None = None,
    ) -> list[str]:
        cmd = ["deno", "run"]
        cmd.extend(self.permissions)
        if memory_limit_mb:
            cmd.append(f"--v8-flags=--max-old-space-size={memory_limit_mb}")
        cmd.append(PKG_NAME)
        cmd.extend(["-c", code])
        if self.stateful:
            cmd.append("-s")
        if session_bytes:
            bytes_array = list(session_bytes)
            cmd.extend(["-b", json.dumps(bytes_array)])
        if session_metadata:
            cmd.extend(["-m", json.dumps(session_metadata)])
        return cmd

    async def execute(
        self,
        code: str,
        *,
        packages: list[str] | None = None,
        session_bytes: bytes | None = None,
        session_metadata: dict | None = None,
        timeout_seconds: float | None = None,
        memory_limit_mb: int | None = None,
    ) -> CodeExecutionResult:
        start = time.time()
        cmd = self._build_command(
            code,
            session_bytes=session_bytes,
            session_metadata=session_metadata,
            memory_limit_mb=memory_limit_mb,
        )
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(), timeout=timeout_seconds
            )
            raw_stdout = stdout_bytes.decode("utf-8", errors="replace")
            raw_stderr = stderr_bytes.decode("utf-8", errors="replace")
            if raw_stdout:
                try:
                    payload = json.loads(raw_stdout)
                except json.JSONDecodeError:
                    return CodeExecutionResult(
                        status="error",
                        execution_time=time.time() - start,
                        stdout=raw_stdout,
                        stderr=raw_stderr or "invalid JSON payload from sandbox",
                        result=None,
                    )
                status = "success" if payload.get("success") else "error"
                return CodeExecutionResult(
                    status=status,
                    execution_time=time.time() - start,
                    stdout=payload.get("stdout"),
                    stderr=payload.get("stderr") or raw_stderr or None,
                    result=payload.get("result"),
                    session_metadata=payload.get("sessionMetadata"),
                    session_bytes=bytes(payload["sessionBytes"])
                    if payload.get("sessionBytes")
                    else None,
                )
            return CodeExecutionResult(
                status="error",
                execution_time=time.time() - start,
                stdout=None,
                stderr=raw_stderr or "empty stdout from sandbox",
                result=None,
            )
        except TimeoutError:
            process.kill()
            await process.wait()
            return CodeExecutionResult(
                status="error",
                execution_time=time.time() - start,
                stdout=None,
                stderr=f"Execution timed out after {timeout_seconds} seconds",
                result=None,
            )
