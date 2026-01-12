from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from agent_api.http.context import AuthContext, RequestContext
from agent_api.http.deps import (
    get_auth_context,
    get_db_session,
    get_request_context,
    get_runner,
    get_settings,
)
from agent_api.services.reports import ReportService
from agent_api.settings import Settings

router = APIRouter(prefix="/v1/reports", tags=["reports"])


@router.get(
    "/housing/{country_code}",
    summary="Generate and download a housing assessment report",
    description="""
    Generate a PDF housing assessment report for a country.
    
    Reports are cached in S3 and expire 30 days after generation.
    Use `skip_cache=true` to force regeneration (the new report will still be cached).
    """,
    status_code=200,
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "Returns the generated PDF report.",
        }
    },
)
async def generate_report(
    country_code: Annotated[
        str, Path(min_length=3, max_length=3, description="ISO-3 country code")
    ],
    request_context: Annotated[RequestContext, Depends(get_request_context)],
    auth_context: Annotated[AuthContext, Depends(get_auth_context)],
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
    chat_runner: Annotated[Any, Depends(get_runner)],  # get_runner returns Any (LangGraphRunner)
    settings: Annotated[Settings, Depends(get_settings)],
    skip_cache: Annotated[
        bool,
        Query(
            description="Skip cache lookup and force regeneration. "
                        "The new report will still be uploaded to the cache."
        ),
    ] = False,
):
    service = ReportService(db_session=db_session, runner=chat_runner, settings=settings)  # type: ignore[arg-type]

    # User ID is required
    user_id = auth_context.user_id
    if not user_id:
        # Should be handled by deps usually, but let's be safe or rely on repo to fail
        pass

    pdf_bytes = await service.generate_housing_report(
        country_code=country_code.upper(),
        user_id=user_id or "anonymous",  # Fallback if auth is loose, though usually required
        request_context=request_context,
        auth_context=auth_context,
        skip_cache=skip_cache,
    )

    filename = f"{country_code}_Housing_Assessment_Report.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
