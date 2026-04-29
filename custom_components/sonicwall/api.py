"""
SonicOS API client for the SonicWall integration.

TZ350 / SonicOS Enhanced 6.5.4.5-53n authenticates by source IP, not by
session cookie. ``POST /api/sonicos/auth`` with HTTP Basic establishes a
source-IP-bound session on the firewall; subsequent ``GET`` calls from the
same client IP within the idle window are accepted without further auth
headers. ``DELETE /api/sonicos/auth`` releases the session slot.

The firewall does *not* return a ``Set-Cookie`` on ``POST /auth``. Earlier
revisions of this client looked for a cookie and aborted login when none
appeared; ``ha-ro`` would log in successfully on the firewall side, then HA
would discard the session because the expected cookie was missing.
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
    """SonicOS API client (HTTP Basic over HTTPS, source-IP session)."""

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
        # `int(port)` defends against NumberSelector handing us 443.0; the
        # f-string would otherwise render that as "443.0" and produce a
        # malformed URL.
        self._base_url = f"https://{host}:{int(port)}/api/sonicos"
        self._logged_in = False
        self._login_lock = asyncio.Lock()

    async def async_login(self, *, force: bool = False) -> None:
        """
        Establish a source-IP-bound session via ``POST /auth``.

        Returns immediately if we're already logged in, unless ``force=True``.
        """
        async with self._login_lock:
            if self._logged_in and not force:
                return
            self._logged_in = False
            await self._post_auth()
            self._logged_in = True

    async def async_logout(self) -> None:
        """Release the API session (best-effort; swallows errors)."""
        if not self._logged_in:
            return
        try:
            await self._request("DELETE", "/auth")
        except SonicWallApiClientError:
            pass
        finally:
            self._logged_in = False

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
        """GET with automatic re-login if the firewall session has expired."""
        if not self._logged_in:
            await self.async_login()
        try:
            return await self._request("GET", path)
        except SonicWallApiClientAuthenticationError:
            await self.async_login(force=True)
            return await self._request("GET", path)

    async def _post_auth(self) -> None:
        """Send ``POST /auth`` with HTTP Basic to establish the session."""
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
                # Drain body so the connection can be reused for the GETs.
                await response.read()
        except TimeoutError as exception:
            msg = f"Timeout authenticating to SonicWall - {exception}"
            raise SonicWallApiClientCommunicationError(msg) from exception
        except (aiohttp.ClientError, socket.gaierror) as exception:
            msg = f"Error authenticating to SonicWall - {exception}"
            raise SonicWallApiClientCommunicationError(msg) from exception

    async def _request(self, method: str, path: str) -> Any:
        """Send a request to an endpoint that relies on the IP-bound session."""
        url = f"{self._base_url}{path}"
        headers = {"Accept": "application/json"}
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
                # SonicOS speaks HTTP/1.0 without Content-Length, so we can't
                # rely on response.content_length to detect empty bodies.
                # The endpoints we call always return a JSON object; only a
                # genuine 204 No Content has no body.
                if response.status == HTTPStatus.NO_CONTENT:
                    return None
                return await response.json(content_type=None)

        except TimeoutError as exception:
            msg = f"Timeout talking to SonicWall - {exception}"
            raise SonicWallApiClientCommunicationError(msg) from exception
        except (aiohttp.ClientError, socket.gaierror) as exception:
            msg = f"Error talking to SonicWall - {exception}"
            raise SonicWallApiClientCommunicationError(msg) from exception
