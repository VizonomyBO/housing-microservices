"""HTTP clients for interacting with other services."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx

from job_service.settings import Settings

logger = logging.getLogger(__name__)


@dataclass
class AuthClient:
    """Client for authentication service."""

    settings: Settings
    _access_token: str | None = field(default=None, init=False)
    _token_expires_at: datetime | None = field(default=None, init=False)

    async def get_access_token(self) -> str:
        """Get a valid access token, refreshing if necessary."""
        # For now, always login fresh. Could add token caching/refresh later.
        if not self.settings.auth.email or not self.settings.auth.password:
            raise RuntimeError(
                "Job service credentials not configured. "
                "Set JOB_SERVICE_EMAIL and JOB_SERVICE_PASSWORD."
            )

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.settings.auth.base_url.rstrip('/')}/v1/auth/login",
                json={
                    "login": self.settings.auth.email,
                    "password": self.settings.auth.password,
                },
            )

            if response.status_code != 200:
                logger.error(f"Login failed: {response.status_code} - {response.text}")
                raise RuntimeError(f"Authentication failed: {response.status_code}")

            data = response.json()
            self._access_token = data.get("access_token")

            if not self._access_token:
                raise RuntimeError("No access_token in login response")

            logger.info("Successfully authenticated for job execution")
            return self._access_token


@dataclass
class AgentApiClient:
    """Client for Agent API service."""

    settings: Settings
    auth_client: AuthClient

    async def get_countries_with_documents(
        self, access_scope: str | None = None
    ) -> list[str]:
        """Fetch list of countries that have documents."""
        token = await self.auth_client.get_access_token()

        params: dict[str, Any] = {"exclude_regions": "true"}
        if access_scope:
            params["access_scope"] = access_scope

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.settings.agent_api.base_url.rstrip('/')}/v1/documents/countries",
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )

            if response.status_code != 200:
                logger.error(
                    f"Failed to fetch countries: {response.status_code} - {response.text}"
                )
                raise RuntimeError(f"Failed to fetch countries: {response.status_code}")

            data = response.json()
            countries = data.get("countries", [])
            logger.info(f"Found {len(countries)} countries with documents")
            return countries

    async def generate_report(
        self,
        country_code: str,
        skip_cache: bool = True,
    ) -> tuple[bool, int, str]:
        """
        Generate a report for a specific country.

        Args:
            country_code: ISO-3 country code
            skip_cache: Whether to skip cache lookup (default True for pre-generation)

        Returns:
            Tuple of (success, http_status, message)
        """
        token = await self.auth_client.get_access_token()

        params: dict[str, Any] = {
            "skip_cache": str(skip_cache).lower(),
        }

        url = f"{self.settings.agent_api.base_url.rstrip('/')}/v1/reports/housing/{country_code}"

        try:
            async with httpx.AsyncClient(
                timeout=self.settings.agent_api.timeout_seconds
            ) as client:
                response = await client.get(
                    url,
                    params=params,
                    headers={"Authorization": f"Bearer {token}"},
                )

                if response.status_code == 200:
                    # Check if we got a PDF
                    content_type = response.headers.get("content-type", "")
                    if "application/pdf" in content_type:
                        size = len(response.content)
                        logger.info(
                            f"Generated report for {country_code}: {size} bytes"
                        )
                        return True, 200, f"Generated ({size} bytes)"

                logger.error(
                    f"Report generation failed for {country_code}: "
                    f"{response.status_code} - {response.text[:200]}"
                )
                return False, response.status_code, response.text[:200]

        except httpx.TimeoutException:
            logger.error(f"Timeout generating report for {country_code}")
            return False, 504, "Request timed out"
        except Exception as e:
            logger.error(f"Error generating report for {country_code}: {e}")
            return False, 500, str(e)


__all__ = ["AuthClient", "AgentApiClient"]

