from enum import Enum


class StrEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class ApplicationStatus(StrEnum):
    NOT_STARTED = "not_started"
    DRAFTING = "drafting"
    APPLIED = "applied"
    INTERVIEWING = "interviewing"
    OFFER = "offer"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class ExtractionRisk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class FileType(StrEnum):
    PDF = "pdf"
    DOCX = "docx"
    UNSPECIFIED = "unspecified"


class JobStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    ARCHIVED = "archived"
    BLOCKED = "blocked"


class MatchVerdict(StrEnum):
    STRONG = "strong"
    GOOD = "good"
    WEAK = "weak"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"


class RemotePolicy(StrEnum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNKNOWN = "unknown"


class RequirementType(StrEnum):
    EXPLICIT = "explicit"
    INFERRED = "inferred"
    UNCERTAIN = "uncertain"


class ResumeLength(StrEnum):
    ONE_PAGE = "one_page"
    TWO_PAGE = "two_page"
    UNSPECIFIED = "unspecified"


class SalaryPeriod(StrEnum):
    ANNUAL = "annual"
    MONTHLY = "monthly"
    HOURLY = "hourly"
    UNKNOWN = "unknown"


class SavedStatus(StrEnum):
    NEW = "new"
    SAVED = "saved"
    DISMISSED = "dismissed"
    ARCHIVED = "archived"


class Seniority(StrEnum):
    INTERNSHIP = "internship"
    ENTRY = "entry"
    MID = "mid"
    SENIOR = "senior"
    UNKNOWN = "unknown"


class TailoringStatus(StrEnum):
    NOT_STARTED = "not_started"
    SELECTION_DRAFT = "selection_draft"
    SELECTION_APPROVED = "selection_approved"
    CONTENT_DRAFT = "content_draft"
    COMPILE_FAILED = "compile_failed"
    RENDERED = "rendered"
    FINAL_APPROVED = "final_approved"
