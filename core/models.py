from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from typing import Any

from .version import APP_VERSION


RaceMode = Literal["nar", "jra"]


@dataclass(frozen=True)
class HtmlMeta:
    file_name: str
    title: str = ""
    canonical: str = ""
    og_url: str = ""
    body_id: str = ""
    table_markers: tuple[str, ...] = ()


@dataclass(frozen=True)
class ClassifiedHtml:
    kind: str
    label: str
    file_name: str
    html_text: str
    meta: HtmlMeta
    reasons: tuple[str, ...] = ()
    all_matches: dict[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass
class PredictionResult:
    """Future bridge from notebook-derived prediction logic to mobile PNG rendering."""

    race_mode: RaceMode
    version: str = APP_VERSION
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    race_name: str = ""
    race_info: dict[str, Any] = field(default_factory=dict)
    overall_table: Any = None
    horse_evaluation: Any = None
    attention_horses: list[str] = field(default_factory=list)
    ai_race_review: str = ""
    betting_structure: str = ""
    source_files: dict[str, str] = field(default_factory=dict)
    status: str = "not_started"
    message: str = ""
    raw_output: str = ""
    debug_info: dict[str, Any] = field(default_factory=dict)
