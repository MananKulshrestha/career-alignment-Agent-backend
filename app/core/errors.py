from fastapi import HTTPException, status


class WorkflowError(ValueError):
    """Base error for deterministic workflow validation failures."""


class BlockedWorkflowError(WorkflowError):
    """Raised when a workflow must stop until data is repaired or reviewed."""


def http_bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


def http_not_found(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)


def http_conflict(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)
