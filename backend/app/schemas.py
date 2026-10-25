from typing import Literal, Optional
from pydantic import BaseModel, Field

DocType = Literal["procedure", "repair_report", "test_report", "work_permit", "maintenance_record", "other"]


class ReviewIn(BaseModel):
    equipment_id: str = Field(min_length=1, max_length=40)
    equipment_type: str = Field(min_length=1, max_length=100)
    maintenance_description: str = Field(min_length=1, max_length=2000)
    review_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    notes: str = Field(default="", max_length=4000)


class ExtractIn(BaseModel):
    procedure_document_id: int


class RequirementIn(BaseModel):
    description: str = Field(min_length=3, max_length=2000)
    mandatory_status: Literal["mandatory", "optional", "unclear"]
    source_document_id: Optional[int] = None
    source_page: Optional[int] = None
    source_quote: str = ""
    expected_evidence_type: str = "other"
    confidence: str = "medium"
    uncertainty: str = ""
    approved_by_user: bool = False


class RequirementsIn(BaseModel):
    requirements: list[RequirementIn]


class DocTypeIn(BaseModel):
    document_type: DocType
