"""
SonicOS API client for the SonicWall integration.

TZ350 / SonicOS Enhanced 6.5.4.5-53n requires session-mode auth:
``POST /api/sonicos/auth`` with HTTP Basic establishes a session cookie,
subsequent ``GET`` calls ride that cookie, and ``DELETE /api/sonicos/auth``
releases the session slot.
"""

from __future__ import annotations

import asyncio
import socket
from http import HTTPStatus
from typing import Any

import aiohttp
import async_timeout


class SonicWallApiClientError(Exception):
    """Exception to indicate a general API error."""


class SonicWallApiClientCommunicationError(
    SonicWallApiClientError,
):
    """Exception to indicate a communication error."""


class SonicWallApiClientAuthenticationError(
    SonicWallApiClientError,
):
    """Exception to indicate an authentication error."""


def _verify_response_or_raise(response: aiohttp.ClientResponse) -> None:
    """Verify that the response is valid."""
    if response.status in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN):
        msg = "Invalid credentials"
        raise SonicWallApiClientAuthenticationError(msg)
    response.raise_for_status()


class SonicWallApiClient:
    """SonicOS API client (HTTP Basic over HTTPS, session-mode)."""

    def __init__(  # noqa: PLR0913
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        verify_ssl: bool,
        session: aiohttp.ClientSession,
    ) -> None:
        """Initialize."""
        self._auth = aiohttp.BasicAuth(username, password)
        self._verify_ssl = verify_ssl
        self._session = session
        self._base_url = f"https://{host}:{port}/api/sonicos"
        # Captured Set-Cookie value (e.g. "sessId=abc123"). Set by async_login.
        self._cookie: str | None = None
        self._login_lock = asyncio.Lock()

    async def async_login(self, *, force: bool = False) -> None:
        """
        Establish a session cookie via ``POST /auth``.

        Returns immediately if a cookie is already held, unless ``force=True``.
        """
        async with self._login_lock:
            if self._cookie and not force:
                return
            self._cookie = None
            cookie = await self._post_auth()
            if not cookie:
                msg = "SonicWall did not return a session cookie"
                raise SonicWallApiClientAuthenticationError(msg)
            self._cookie = cookie

    async def async_logout(self) -> None:
        """Release the API session (best-effort; swallows errors)."""
        if not self._cookie:
            return
        try:
            await self._request("DELETE", "/auth")
        except SonicWallApiClientError:
            pass
        finally:
            self._cookie = None

    async def async_version(self) -> Any:
        """Retrieve firmware/model/serial info."""
        return await self._authenticated_get("/version")

    async def async_system_reporting(self) -> Any:
        """Retrieve system status (CPU, uptime, connections)."""
        return await self._authenticated_get("/reporting/system")

    async def async_interfaces_ipv4(self) -> Any:
        """Retrieve IPv4 per-interface byte/packet counters."""
        return await self._authenticated_get("/reporting/interfaces/ipv4")

    async def async_interface_status(self) -> Any:
        """Retrieve per-interface zone, IP, and link status."""
        return await self._authenticated_get("/reporting/interfaces/ip")

    async def _authenticated_get(self, path: str) -> Any:
        """GET with automatic re-login if the cookie has expired."""
        if not self._cookie:
            await self.async_login()
        try:
            return await self._request("GET", path)
        except SonicWallApiClientAuthenticationError:
            await self.async_login(force=True)
            return await self._request("GET", path)

    async def _post_auth(self) -> str | None:
        """Send ``POST /auth`` with Basic auth and capture the session cookie."""
        url = f"{self._base_url}/auth"
        headers = {"Accept": "application/json"}
        try:
            async with (
                async_timeout.timeout(10),
                self._session.request(
                    method="POST",
                    url=url,
                    headers=headers,
                    auth=self._auth,
                    ssl=self._verify_ssl,
                ) as response,
            ):
                _verify_response_or_raise(response)
                set_cookie = response.headers.get("Set-Cookie", "")
                await response.read()
        except TimeoutError as exception:
            msg = f"Timeout authenticating to SonicWall - {exception}"
            raise SonicWallApiClientCommunicationError(msg) from exception
        except (aiohttp.ClientError, socket.gaierror) as exception:
            msg = f"Error authenticating to SonicWall - {exception}"
            raise SonicWallApiClientCommunicationError(msg) from exception
        # Set-Cookie is "name=value; path=...; ...". Keep just "name=value".
        return set_cookie.split(";", 1)[0] if set_cookie else None

    async def _request(self, method: str, path: str) -> Any:
        """Send an authenticated request riding the session cookie."""
        url = f"{self._base_url}{path}"
        headers = {"Accept": "application/json"}
        if self._cookie:
            headers["Cookie"] = self._cookie
        try:
            async with (
                async_timeout.timeout(10),
                self._session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    ssl=self._verify_ssl,
                ) as response,
            ):
                _verify_response_or_raise(response)
                if (
                    response.status == HTTPStatus.NO_CONTENT
                    or not response.content_length
                ):
                    return None
                return await response.json(content_type=None)

        except TimeoutError as exception:
            msg = f"Timeout talking to SonicWall - {exception}"
            raise SonicWallApiClientCommunicationError(msg) from exception
        except (aiohttp.ClientError, socket.gaierror) as exception:
            msg = f"Error talking to SonicWall - {exception}"
            raise SonicWallApiClientCommunicationError(msg) from exception
