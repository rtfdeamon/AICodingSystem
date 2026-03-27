"""n8n webhook integration service for triggering external workflows."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Map logical workflow names to n8n webhook path suffixes.
WORKFLOW_ENDPOINTS: dict[str, str] = {
    "ai_planning": "/webhook/ai-planning",
    "ai_coding": "/webhook/ai-coding",
    "build_test": "/webhook/build-test",
    "deploy_canary": "/webhook/deploy-canary",
    "notify": "/webhook/notify",
}


async def trigger_workflow(
    workflow_name: str,
    payload: dict[str, Any],
    *,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """POST *payload* to the n8n webhook for *workflow_name*.

    Returns the JSON response from n8n, or an error dict if the request fails.
    Raises :class:`ValueError` for unknown workflow names.
    """
    if workflow_name not in WORKFLOW_ENDPOINTS:
        raise ValueError(
            f"Unknown workflow '{workflow_name}'. "
            f"Valid names: {', '.join(sorted(WORKFLOW_ENDPOINTS))}."
        )

    base_url = settings.N8N_BASE_URL
    if not base_url:
        logger.warning(
            "N8N_BASE_URL is not configured; skipping workflow trigger for '%s'.",
            workflow_name,
        )
        return {"status": "skipped", "reason": "N8N_BASE_URL not configured"}

    url = f"{base_url.rstrip('/')}{WORKFLOW_ENDPOINTS[workflow_name]}"

    logger.info("Triggering n8n workflow '%s' at %s", workflow_name, url)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            result = response.json()
            logger.info(
                "n8n workflow '%s' responded with status %d",
                workflow_name,
                response.status_code,
            )
            return result  # type: ignore[no-any-return]
    except httpx.HTTPStatusError as exc:
        logger.error(
            "n8n workflow '%s' returned HTTP %d: %s",
            workflow_name,
            exc.response.status_code,
            exc.response.text[:500],
        )
        return {
            "status": "error",
            "http_status": exc.response.status_code,
            "detail": exc.response.text[:500],
        }
    except httpx.RequestError as exc:
        logger.error("n8n workflow '%s' request failed: %s", workflow_name, exc)
        return {"status": "error", "detail": str(exc)}
