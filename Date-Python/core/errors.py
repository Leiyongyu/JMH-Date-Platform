"""业务异常层次结构。中间件统一捕获并序列化为 JSON。"""


class AppError(Exception):
    """所有已知异常的基类"""
    http_status: int = 500
    error_code: str = "INTERNAL_ERROR"

    def __init__(self, message: str = "", details: dict | list | None = None):
        super().__init__(message)
        self.message = message or self.__class__.__doc__ or ""
        self.details = details


class BadRequestError(AppError):
    http_status = 400
    error_code = "BAD_REQUEST"


class ValidationError(AppError):
    """请求参数不合法"""
    http_status = 422
    error_code = "VALIDATION_ERROR"


class NotFoundError(AppError):
    """资源不存在"""
    http_status = 404
    error_code = "NOT_FOUND"


class TaskError(AppError):
    """任务执行失败（可重试）"""
    http_status = 400
    error_code = "TASK_FAILED"


class FileError(AppError):
    """文件处理失败"""
    http_status = 422
    error_code = "FILE_ERROR"


class FileTypeError(FileError):
    """文件类型不匹配"""
    http_status = 422
    error_code = "INVALID_FILE_TYPE"


class DuplicateFileError(FileError):
    """文件重复上传"""
    http_status = 409
    error_code = "DUPLICATE_FILE"


class PayloadTooLargeError(AppError):
    """上传文件超限"""
    http_status = 413
    error_code = "PAYLOAD_TOO_LARGE"


class MatchError(AppError):
    """报关资料匹配失败"""
    http_status = 422
    error_code = "MATCH_ERROR"


class ForexImportError(AppError):
    """外汇数据导入失败"""
    http_status = 422
    error_code = "FOREX_IMPORT_ERROR"
