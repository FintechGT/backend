from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class TestResultItem(BaseModel):
    test: str
    passed: bool
    duration_ms: float
    details: str
    timestamp: str

class TestSummary(BaseModel):
    total: int
    passed: int
    failed: int
    success_rate: float
    avg_duration_ms: float
    results: List[TestResultItem]