"""Database tables. Raw telemetry, metric definitions, metric results and
discoveries are kept in separate tables (no wide 305-column table)."""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text,
                        UniqueConstraint, Uuid)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

J = JSON().with_variant(JSONB(), "postgresql")


def now():
    return dt.datetime.now(dt.timezone.utc)


class Athlete(Base):
    __tablename__ = "athletes"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120))
    sex: Mapped[str | None] = mapped_column(String(16))
    birth_year: Mapped[int | None] = mapped_column(Integer)
    max_hr: Mapped[float | None] = mapped_column(Float)
    rest_hr: Mapped[float | None] = mapped_column(Float)
    lthr: Mapped[float | None] = mapped_column(Float)
    threshold_pace_s_km: Mapped[float | None] = mapped_column(Float)
    ftp_w: Mapped[float | None] = mapped_column(Float)
    weight_kg: Mapped[float | None] = mapped_column(Float)
    goal: Mapped[str] = mapped_column(String(40), default="general")  # general|aerobic_base|speed|race_10k|...
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)


class Activity(Base):
    __tablename__ = "activities"
    __table_args__ = (UniqueConstraint("athlete_id", "file_sha256", name="uq_activity_file"),
                      Index("ix_activity_athlete_start", "athlete_id", "start_time"))
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    athlete_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("athletes.id", ondelete="CASCADE"))
    sport: Mapped[str] = mapped_column(String(24))
    sub_sport: Mapped[str | None] = mapped_column(String(40))
    start_time: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    elapsed_s: Mapped[int] = mapped_column(Integer)
    moving_s: Mapped[int] = mapped_column(Integer)
    distance_m: Mapped[float | None] = mapped_column(Float)
    source_format: Mapped[str] = mapped_column(String(8))
    original_filename: Mapped[str] = mapped_column(String(255))
    file_sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(255))
    device: Mapped[str | None] = mapped_column(String(120))
    channel_provenance: Mapped[dict] = mapped_column(J, default=dict)
    quality: Mapped[dict] = mapped_column(J, default=dict)  # score + components + issues
    summary: Mapped[dict] = mapped_column(J, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|analysed|failed
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)


class TelemetrySample(Base):
    __tablename__ = "telemetry_samples"
    activity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("activities.id", ondelete="CASCADE"), primary_key=True)
    elapsed_s: Mapped[int] = mapped_column(Integer, primary_key=True)
    distance_m: Mapped[float | None] = mapped_column(Float)
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    altitude_m: Mapped[float | None] = mapped_column(Float)
    speed_ms: Mapped[float | None] = mapped_column(Float)
    heart_rate: Mapped[float | None] = mapped_column(Float)
    cadence_spm: Mapped[float | None] = mapped_column(Float)
    power_w: Mapped[float | None] = mapped_column(Float)
    temperature_c: Mapped[float | None] = mapped_column(Float)
    grade_pct: Mapped[float | None] = mapped_column(Float)
    vertical_oscillation_mm: Mapped[float | None] = mapped_column(Float)
    ground_contact_ms: Mapped[float | None] = mapped_column(Float)
    stride_length_m: Mapped[float | None] = mapped_column(Float)
    respiration_rate: Mapped[float | None] = mapped_column(Float)
    moving: Mapped[bool] = mapped_column(Boolean, default=False)


class MetricDefinitionRow(Base):
    __tablename__ = "metric_definitions"
    metric_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(60), index=True)
    sport: Mapped[str] = mapped_column(String(24))
    unit: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(32))
    algorithm_version: Mapped[str] = mapped_column(String(16))
    definition: Mapped[dict] = mapped_column(J)


class MetricResultRow(Base):
    __tablename__ = "metric_results"
    __table_args__ = (Index("ix_metric_results_metric", "metric_id", "athlete_id"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    activity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("activities.id", ondelete="CASCADE"), index=True)
    athlete_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("athletes.id", ondelete="CASCADE"))
    metric_id: Mapped[str] = mapped_column(ForeignKey("metric_definitions.metric_id"))
    value: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(24))
    state: Mapped[str] = mapped_column(String(24))
    source: Mapped[str] = mapped_column(String(24))
    quality: Mapped[float | None] = mapped_column(Float)
    detail: Mapped[dict] = mapped_column(J, default=dict)
    algorithm_version: Mapped[str] = mapped_column(String(16))


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    athlete_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("athletes.id", ondelete="CASCADE"))
    activity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("activities.id", ondelete="CASCADE"))
    original_filename: Mapped[str] = mapped_column(String(255))
    file_sha256: Mapped[str] = mapped_column(String(64), index=True)
    storage_key: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued|running|done|failed
    stage: Mapped[str] = mapped_column(String(40), default="queued")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class EffortSegment(Base):
    """Steady efforts, km splits and intervals: the units the comparable-effort engine matches."""
    __tablename__ = "effort_segments"
    __table_args__ = (Index("ix_segments_athlete_kind", "athlete_id", "kind"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    athlete_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("athletes.id", ondelete="CASCADE"))
    activity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("activities.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # steady|split_km|interval|recovery
    start_s: Mapped[int] = mapped_column(Integer)
    duration_s: Mapped[int] = mapped_column(Integer)
    distance_m: Mapped[float] = mapped_column(Float)
    avg_pace_s_km: Mapped[float | None] = mapped_column(Float)
    avg_hr: Mapped[float | None] = mapped_column(Float)
    avg_cadence: Mapped[float | None] = mapped_column(Float)
    avg_grade: Mapped[float | None] = mapped_column(Float)
    elev_gain_m: Mapped[float | None] = mapped_column(Float)
    temperature_c: Mapped[float | None] = mapped_column(Float)
    pace_cv: Mapped[float | None] = mapped_column(Float)
    quality: Mapped[float] = mapped_column(Float)
    start_lat: Mapped[float | None] = mapped_column(Float)
    start_lon: Mapped[float | None] = mapped_column(Float)
    end_lat: Mapped[float | None] = mapped_column(Float)
    end_lon: Mapped[float | None] = mapped_column(Float)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))


class Discovery(Base):
    __tablename__ = "discoveries"
    __table_args__ = (Index("ix_discoveries_athlete", "athlete_id", "significance_score"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    athlete_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("athletes.id", ondelete="CASCADE"))
    activity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("activities.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(48))
    classification: Mapped[str] = mapped_column(String(24))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    observed_value: Mapped[dict] = mapped_column(J)
    baseline_value: Mapped[dict] = mapped_column(J)
    improvement: Mapped[dict] = mapped_column(J)
    confidence: Mapped[float] = mapped_column(Float)
    significance_score: Mapped[float] = mapped_column(Float)
    ranking: Mapped[dict] = mapped_column(J)
    limitations: Mapped[list] = mapped_column(J)
    recommended_experiment: Mapped[dict] = mapped_column(J)
    algorithm_version: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)
    evidence: Mapped[list["DiscoveryEvidence"]] = relationship(cascade="all, delete-orphan", lazy="selectin")


class DiscoveryEvidence(Base):
    __tablename__ = "discovery_evidence"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    discovery_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("discoveries.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # metric|segment|activity|statistic
    ref_id: Mapped[str | None] = mapped_column(String(80))
    label: Mapped[str] = mapped_column(String(200))
    value: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(24))
    detail: Mapped[dict] = mapped_column(J, default=dict)


class AthleteBaseline(Base):
    """Incrementally maintained per-athlete aggregates (no full-history recompute)."""
    __tablename__ = "athlete_baselines"
    __table_args__ = (UniqueConstraint("athlete_id", "key", name="uq_baseline_key"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    athlete_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("athletes.id", ondelete="CASCADE"))
    key: Mapped[str] = mapped_column(String(80))  # e.g. metric:running.efficiency_factor, curve:pace_duration
    data: Mapped[dict] = mapped_column(J)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class AthleteIndex(Base):
    __tablename__ = "athlete_indexes"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    athlete_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("athletes.id", ondelete="CASCADE"), index=True)
    activity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("activities.id", ondelete="CASCADE"), index=True)
    index_id: Mapped[str] = mapped_column(String(40))
    score: Mapped[float | None] = mapped_column(Float)
    state: Mapped[str] = mapped_column(String(24))
    confidence: Mapped[float] = mapped_column(Float)
    components: Mapped[dict] = mapped_column(J)
    version: Mapped[str] = mapped_column(String(16))
    computed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)


class GoldenCheetahSync(Base):
    __tablename__ = "golden_cheetah_sync"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    activity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("activities.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(24))  # unavailable|exported|matched|failed
    gc_filename: Mapped[str | None] = mapped_column(String(120))
    gc_metrics: Mapped[dict] = mapped_column(J, default=dict)
    comparison: Mapped[dict] = mapped_column(J, default=dict)
    message: Mapped[str | None] = mapped_column(Text)
    synced_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)


class AiConversation(Base):
    __tablename__ = "ai_conversations"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    athlete_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("athletes.id", ondelete="CASCADE"), index=True)
    activity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("activities.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(16))  # commentary|question
    question: Mapped[str | None] = mapped_column(Text)
    response: Mapped[dict] = mapped_column(J)
    tool_calls: Mapped[list] = mapped_column(J, default=list)
    model: Mapped[str] = mapped_column(String(60))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)
