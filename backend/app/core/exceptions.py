"""Application-level exceptions mapped to API error codes."""

from __future__ import annotations


class GrayScopeError(Exception):
    code: str = "INTERNAL_ERROR"
    status_code: int = 500

    def __init__(self, message: str = "") -> None:
        self.message = message
        super().__init__(message)


class NotFoundError(GrayScopeError):
    code = "NOT_FOUND"
    status_code = 404


class TaskNotFoundError(GrayScopeError):
    code = "TASK_NOT_FOUND"
    status_code = 404


class InvalidRequestError(GrayScopeError):
    code = "INVALID_REQUEST"
    status_code = 422


class TaskStateInvalidError(GrayScopeError):
    code = "TASK_STATE_INVALID"
    status_code = 409


class RepoSyncFailedError(GrayScopeError):
    code = "REPO_SYNC_FAILED"
    status_code = 502


class ModelProviderUnavailableError(GrayScopeError):
    code = "MODEL_PROVIDER_UNAVAILABLE"
    status_code = 503


class ModelResponseInvalidError(GrayScopeError):
    code = "MODEL_RESPONSE_INVALID"
    status_code = 502


class ExportFailedError(GrayScopeError):
    code = "EXPORT_FAILED"
    status_code = 500
