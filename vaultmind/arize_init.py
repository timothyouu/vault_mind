"""
vaultmind/arize_init.py — Arize + OpenTelemetry init wrapper.

FROZEN NAMING — all sessions must call init_arize() with the service name
from the table below. Never invent a different name; Arize correlates spans
across streams by these keys.

  P1 (ingestion):             init_arize("vaultmind-ingest")
  P2+P3 (watcher process):    init_arize("vaultmind-pipeline")
  P4 (Next.js server routes): init_arize("vaultmind-webapp")   ← called via subprocess or TS shim

Arize project name: "vaultmind"  (never change)
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Frozen service name constants — import these instead of using string literals.
SERVICE_INGEST   = "vaultmind-ingest"
SERVICE_PIPELINE = "vaultmind-pipeline"
SERVICE_WEBAPP   = "vaultmind-webapp"

# Frozen span / attribute names — import these instead of using string literals.
SPAN_TURN        = "turn"
SPAN_TURN_EVAL   = "turn.eval"
ATTR_TURN_ID     = "turn_id"
ATTR_EVAL_RECALL         = "eval.recall"
ATTR_EVAL_PRECISION      = "eval.precision"
ATTR_EVAL_EXTRACTION_Q   = "eval.extraction_quality"
ATTR_EVAL_LINK_RELEVANCE = "eval.link_relevance"
ATTR_EVAL_GROUNDING      = "eval.grounding"
ATTR_EVAL_PIPELINE_Q     = "eval.pipeline_quality"
ATTR_EVAL_DETAIL         = "eval.detail"

SPAN_STAGE_SCRIBE       = "stage.scribe"
SPAN_STAGE_NOTECREATOR  = "stage.notecreator"
SPAN_STAGE_CONNECTOR    = "stage.connector"

ARIZE_PROJECT = "vaultmind"


def init_arize(service_name: str) -> Optional[object]:
    """
    Initialize Arize + OpenTelemetry tracing for the given service.

    Returns the tracer provider (or None if credentials are missing and
    VAULTMIND_ARIZE_REQUIRED is not set — safe for local dev without keys).

    Each session calls this once at startup with the frozen service name:
      from vaultmind.arize_init import init_arize, SERVICE_PIPELINE
      init_arize(SERVICE_PIPELINE)
    """
    space_key = os.environ.get("ARIZE_SPACE_KEY")
    api_key   = os.environ.get("ARIZE_API_KEY")
    required  = os.environ.get("VAULTMIND_ARIZE_REQUIRED", "").lower() in ("1", "true", "yes")

    if not space_key or not api_key:
        if required:
            raise EnvironmentError(
                "ARIZE_SPACE_KEY and ARIZE_API_KEY must be set "
                "(VAULTMIND_ARIZE_REQUIRED=1)"
            )
        logger.warning(
            "Arize credentials not set (ARIZE_SPACE_KEY / ARIZE_API_KEY); "
            "tracing disabled. Set them to enable observability."
        )
        return None

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME

        # Arize Phoenix / OTLP exporter — works with arize-otel package
        from arize.otel import register

        tracer_provider = register(
            space_key=space_key,
            api_key=api_key,
            model_id=ARIZE_PROJECT,
            model_version=service_name,
        )
        logger.info(
            "Arize tracing initialized: project=%s service=%s",
            ARIZE_PROJECT, service_name,
        )
        return tracer_provider

    except ImportError as e:
        logger.warning("Arize/OTel packages not installed; tracing disabled: %s", e)
        return None
