"""
e-drug lab 本地工具管理器
"""
import subprocess
import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class ToolInfo:
    def __init__(self, name: str, executable_path: str):
        self.name = name
        self.executable_path = executable_path
        self.is_available = os.path.exists(executable_path)
        self.last_checked: Optional[datetime] = None

    def check(self) -> bool:
        self.last_checked = datetime.utcnow()
        self.is_available = os.path.exists(self.executable_path)
        return self.is_available

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "executable_path": self.executable_path,
            "available": self.is_available,
            "last_checked": self.last_checked.isoformat() if self.last_checked else None,
        }


class ToolManager:
    def __init__(self, tool_paths: Dict[str, str]):
        self.tools: Dict[str, ToolInfo] = {}
        for name, path in tool_paths.items():
            if path:
                self.tools[name] = ToolInfo(name, path)
        self._perform_initial_check()

    def _perform_initial_check(self):
        for tool in self.tools.values():
            tool.check()
        available = sum(1 for t in self.tools.values() if t.is_available)
        logger.info(f"ToolManager 初始化完成：{available}/{len(self.tools)} 工具可用")

    def _check_executable(self, path: str) -> bool:
        return os.path.exists(path)

    def get_tool_status(self) -> Dict[str, dict]:
        return {name: tool.to_dict() for name, tool in self.tools.items()}

    def get_tool(self, name: str) -> Optional[ToolInfo]:
        return self.tools.get(name)

    def execute(self, tool_name: str, args: list[str], timeout: int = 600, cwd: Optional[str] = None, env: Optional[Dict[str, str]] = None) -> subprocess.CompletedProcess:
        tool = self.tools.get(tool_name)
        if not tool:
            raise ValueError(f"Unknown tool: {tool_name}")
        if not tool.is_available:
            raise FileNotFoundError(f"Tool not available: {tool_name} at {tool.executable_path}")
        full_env = os.environ.copy()
        if env:
            full_env.update(env)
        logger.info(f"Executing {tool_name}: {args}", extra={"tool": tool_name, "args": args, "cwd": cwd})
        return subprocess.run([tool.executable_path] + args, capture_output=True, text=True, timeout=timeout, cwd=cwd, env=full_env)
