"""
e-drug lab 错误体系
类型化错误类 + 全局错误处理器，遵循 RFC 9457 标准
"""
from typing import Any, Optional
from fastapi import HTTPException, status, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import logging

logger = logging.getLogger(__name__)


class AppError(HTTPException):
    """应用基础错误类"""
    def __init__(
        self,
        message: str,
        code: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Optional[dict[str, Any]] = None,
        is_operational: bool = True,
    ):
        self.code = code
        self.details = details or {}
        self.is_operational = is_operational
        super().__init__(status_code=status_code, detail=message)


class TargetNotFoundError(AppError):
    def __init__(self, target_id: str):
        super().__init__(message=f"靶点不存在：{target_id}", code="TARGET_NOT_FOUND",
                         status_code=status.HTTP_404_NOT_FOUND, details={"target_id": target_id})


class StructureProcessingError(AppError):
    def __init__(self, reason: str, pdb_id: Optional[str] = None):
        super().__init__(message=f"结构处理失败：{reason}", code="STRUCTURE_PROCESSING_ERROR",
                         status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, details={"reason": reason, "pdb_id": pdb_id})


class MoleculeLibraryError(AppError):
    def __init__(self, reason: str, library_id: Optional[str] = None):
        super().__init__(message=f"分子库操作失败：{reason}", code="MOLECULE_LIBRARY_ERROR",
                         status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, details={"reason": reason, "library_id": library_id})


class ScreeningTaskError(AppError):
    def __init__(self, reason: str, task_id: Optional[str] = None):
        super().__init__(message=f"筛选任务失败：{reason}", code="SCREENING_TASK_ERROR",
                         status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, details={"reason": reason, "task_id": task_id})


class ToolExecutionError(AppError):
    def __init__(self, tool_name: str, reason: str, exit_code: Optional[int] = None):
        super().__init__(message=f"工具执行失败 [{tool_name}]: {reason}", code="TOOL_EXECUTION_ERROR",
                         status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                         details={"tool_name": tool_name, "reason": reason, "exit_code": exit_code}, is_operational=False)


class ExternalAPIError(AppError):
    def __init__(self, api_name: str, reason: str, status_code: Optional[int] = None):
        super().__init__(message=f"外部 API 调用失败 [{api_name}]: {reason}", code="EXTERNAL_API_ERROR",
                         status_code=status.HTTP_502_BAD_GATEWAY,
                         details={"api_name": api_name, "reason": reason, "external_status": status_code})


class TaskNotFoundError(AppError):
    def __init__(self, task_id: str):
        super().__init__(message=f"任务不存在：{task_id}", code="TASK_NOT_FOUND",
                         status_code=status.HTTP_404_NOT_FOUND, details={"task_id": task_id})


class ValidationError(AppError):
    def __init__(self, errors: list[dict[str, Any]]):
        super().__init__(message="数据验证失败", code="VALIDATION_ERROR",
                         status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, details={"errors": errors})


class ConfigurationError(AppError):
    def __init__(self, reason: str):
        super().__init__(message=f"配置错误：{reason}", code="CONFIGURATION_ERROR",
                         status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, details={"reason": reason}, is_operational=False)


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    logger.error(f"业务错误 [{exc.code}]", extra={
        "request_id": getattr(request.state, "request_id", None),
        "path": request.url.path, "method": request.method,
    })
    return JSONResponse(status_code=exc.status_code, content={
        "title": exc.code, "status": exc.status_code, "detail": exc.detail,
        "request_id": getattr(request.state, "request_id", None), **exc.details,
    })


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = [{"field": ".".join(str(x) for x in e["loc"]), "message": e["msg"], "type": e["type"]} for e in exc.errors()]
    logger.warning(f"验证错误：{errors}", extra={"request_id": getattr(request.state, "request_id", None)})
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={
        "title": "VALIDATION_ERROR", "status": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "detail": "请求数据验证失败", "errors": errors, "request_id": getattr(request.state, "request_id", None),
    })


async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    logger.error(f"未处理异常：{exc}", exc_info=True, extra={"request_id": request_id})
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={
        "title": "INTERNAL_ERROR", "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
        "detail": "服务器内部错误", "request_id": request_id,
    })
