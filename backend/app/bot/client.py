"""HTTP client for the MITRA API, used by the Telegram bot and the offline demo.

The bot never touches the database directly; everything goes through the API.
Pass an existing httpx.Client (e.g. FastAPI's TestClient) to test without a network.
"""
import os

import httpx

DEFAULT_API_URL = "http://127.0.0.1:8000"
UNREACHABLE = "The MITRA server is not reachable right now. Please try again in a minute."


class ApiError(Exception):
    """Carries a message that is safe to show to the collector."""


class UnknownCollector(ApiError):
    pass


class MitraClient:
    def __init__(self, base_url: str | None = None, client: httpx.Client | None = None,
                 timeout: float = 10.0):
        self.http = client or httpx.Client(
            base_url=base_url or os.environ.get("MITRA_API_URL", DEFAULT_API_URL), timeout=timeout)

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            return self.http.request(method, path, **kwargs)
        except httpx.HTTPError as e:
            raise ApiError(UNREACHABLE) from e

    @staticmethod
    def _detail(r: httpx.Response) -> str:
        try:
            detail = r.json().get("detail", r.text)
        except ValueError:
            detail = r.text
        return detail if isinstance(detail, str) else "; ".join(d.get("msg", "") for d in detail)

    def _json(self, r: httpx.Response):
        if r.status_code >= 500:
            raise ApiError("The MITRA server had a problem. Please try again.")
        if r.status_code >= 400:
            raise ApiError(self._detail(r))
        return r.json()

    def health(self) -> bool:
        try:
            return self._request("GET", "/health").status_code == 200
        except ApiError:
            return False

    def materials(self) -> list[dict]:
        return self._json(self._request("GET", "/api/materials"))

    def register(self, name: str, area: str, phone: str | None = None) -> dict:
        body = {"name": name, "area": area, **({"phone": phone} if phone else {})}
        return self._json(self._request("POST", "/api/collectors", json=body))

    def collector(self, collector_id: int) -> dict | None:
        r = self._request("GET", f"/api/collectors/{collector_id}")
        return None if r.status_code == 404 else self._json(r)

    def forget(self, collector_id: int) -> dict | None:
        """Erase the collector's personal data. None if they were already gone."""
        r = self._request("DELETE", f"/api/collectors/{collector_id}")
        return None if r.status_code == 404 else self._json(r)

    def log_lot(self, collector_id: int, material_id: int, weight_kg: float,
                gps_lat: float | None = None, gps_lon: float | None = None,
                photo_url: str | None = None) -> dict:
        body = {"collector_id": collector_id, "material_id": material_id, "weight_kg": weight_kg,
                "gps_lat": gps_lat, "gps_lon": gps_lon, "photo_url": photo_url}
        r = self._request("POST", "/api/transactions", json=body)
        if r.status_code == 422 and "unknown collector_id" in self._detail(r):
            raise UnknownCollector("Your registration was not found. Please send /start to register again.")
        return self._json(r)
