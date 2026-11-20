"""Reusable Miro REST API v2 client for Voice Coach MVP planning board generation."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

MIRO_API_BASE = "https://api.miro.com/v2"


def load_dotenv(env_path: Path) -> dict[str, str]:
    """Parse a .env file into a dictionary without mutating global shell state."""
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and " " not in key:
            values[key] = value
            os.environ.setdefault(key, value)
    return values


class MiroClient:
    """Thin, rate-limit-aware wrapper around the Miro REST API v2."""

    def __init__(self, access_token: str, board_id: str, timeout: int = 20) -> None:
        if not access_token:
            raise ValueError("MIRO_ACCESS_TOKEN is required.")
        if not board_id:
            raise ValueError("MIRO_BOARD_ID is required.")
        self.access_token = access_token
        self.board_id = board_id
        self.encoded_board_id = quote(board_id, safe="")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

    @classmethod
    def from_env(cls, env_path: Path | None = None) -> "MiroClient":
        """Instantiate MiroClient using .env values or environment variables."""
        if env_path is None:
            env_path = Path(__file__).resolve().parent / ".env"
        load_dotenv(env_path)
        token = os.getenv("MIRO_ACCESS_TOKEN", "").strip()
        board_id = os.getenv("MIRO_BOARD_ID", "").strip()
        return cls(access_token=token, board_id=board_id)

    def _board_url(self, suffix: str = "") -> str:
        return f"{MIRO_API_BASE}/boards/{self.encoded_board_id}{suffix}"

    def _request(
        self,
        method: str,
        url: str,
        payload: dict[str, Any] | None = None,
        max_retries: int = 5,
    ) -> dict[str, Any]:
        """Execute an HTTP request with automatic 429 and transient 5xx retries."""
        for attempt in range(max_retries):
            resp = self.session.request(
                method=method,
                url=url,
                json=payload,
                timeout=self.timeout,
            )
            if resp.status_code == 429 or 500 <= resp.status_code < 600:
                retry_after = float(
                    resp.headers.get("Retry-After", 1.5 * (attempt + 1))
                )
                time.sleep(min(retry_after, 15.0))
                continue
            if not resp.ok:
                raise RuntimeError(
                    f"Miro API {method} {url} failed ({resp.status_code}): {resp.text}"
                )
            if resp.status_code == 204 or not resp.text.strip():
                return {}
            return resp.json()
        raise RuntimeError(f"Miro API {method} {url} exceeded {max_retries} retries.")

    def get_board(self) -> dict[str, Any]:
        return self._request("GET", self._board_url())

    def update_board(self, name: str, description: str) -> dict[str, Any]:
        return self._request(
            "PATCH",
            self._board_url(),
            {"name": name, "description": description},
        )

    def list_items(self, limit: int = 50) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            suffix = f"/items?limit={limit}" + (
                f"&cursor={quote(cursor)}" if cursor else ""
            )
            data = self._request("GET", self._board_url(suffix))
            items.extend(data.get("data", []))
            cursor = data.get("cursor")
            if not cursor:
                break
        return items

    def delete_item(self, item: dict[str, Any]) -> None:
        self_link = item.get("links", {}).get("self")
        url = self_link if self_link else self._board_url(f"/items/{item['id']}")
        self._request("DELETE", url)

    def clear_board(self) -> int:
        """Delete all non-connector items first, then remaining items, returning deleted count."""
        items = self.list_items()
        deleted = 0
        # Delete connectors first, then child items, then frames to avoid dangling references.
        priority = {"connector": 0, "frame": 2}
        ordered = sorted(items, key=lambda it: priority.get(it.get("type", ""), 1))
        for item in ordered:
            try:
                self.delete_item(item)
                deleted += 1
            except RuntimeError as exc:
                # Item may already have been cascade-deleted with a parent frame or endpoint.
                if "(404)" not in str(exc):
                    raise
        return deleted

    def create_frame(
        self,
        title: str,
        x: float,
        y: float,
        width: float,
        height: float,
        fill_color: str = "#ffffff",
    ) -> dict[str, Any]:
        payload = {
            "data": {"title": title, "format": "custom"},
            "style": {"fillColor": fill_color},
            "position": {"x": x, "y": y, "origin": "center"},
            "geometry": {"width": width, "height": height},
        }
        return self._request("POST", self._board_url("/frames"), payload)

    def create_shape(
        self,
        content: str,
        x: float,
        y: float,
        width: float,
        height: float,
        *,
        shape: str = "round_rectangle",
        fill_color: str = "#ffffff",
        border_color: str = "#cbd5e1",
        text_color: str = "#0f172a",
        font_size: str = "14",
        font_family: str = "open_sans",
        border_width: str = "2",
        border_style: str = "normal",
        fill_opacity: str = "1.0",
        text_align: str = "left",
        text_align_vertical: str = "middle",
        parent_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "data": {"shape": shape, "content": content},
            "style": {
                "fillColor": fill_color,
                "fillOpacity": fill_opacity,
                "borderColor": border_color,
                "borderWidth": border_width,
                "borderStyle": border_style,
                "borderOpacity": "1.0",
                "color": text_color,
                "fontFamily": font_family,
                "fontSize": font_size,
                "textAlign": text_align,
                "textAlignVertical": text_align_vertical,
            },
            "position": {"x": x, "y": y, "origin": "center"},
            "geometry": {"width": width, "height": height},
        }
        if parent_id:
            payload["parent"] = {"id": parent_id}
        return self._request("POST", self._board_url("/shapes"), payload)

    def create_sticky(
        self,
        content: str,
        x: float,
        y: float,
        *,
        width: float = 260,
        fill_color: str = "light_yellow",
        shape: str = "square",
        text_align: str = "left",
        text_align_vertical: str = "top",
        parent_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "data": {"content": content, "shape": shape},
            "style": {
                "fillColor": fill_color,
                "textAlign": text_align,
                "textAlignVertical": text_align_vertical,
            },
            "position": {"x": x, "y": y, "origin": "center"},
            "geometry": {"width": width},
        }
        if parent_id:
            payload["parent"] = {"id": parent_id}
        return self._request("POST", self._board_url("/sticky_notes"), payload)

    def create_card(
        self,
        title: str,
        description: str,
        x: float,
        y: float,
        *,
        width: float = 340,
        card_theme: str = "#4f46e5",
        parent_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "data": {"title": title, "description": description},
            "style": {"cardTheme": card_theme},
            "position": {"x": x, "y": y, "origin": "center"},
            "geometry": {"width": width},
        }
        if parent_id:
            payload["parent"] = {"id": parent_id}
        return self._request("POST", self._board_url("/cards"), payload)

    def create_text(
        self,
        content: str,
        x: float,
        y: float,
        *,
        width: float = 600,
        font_size: str = "16",
        color: str = "#0f172a",
        font_family: str = "open_sans",
        text_align: str = "left",
        parent_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "data": {"content": content},
            "style": {
                "color": color,
                "fontFamily": font_family,
                "fontSize": font_size,
                "textAlign": text_align,
            },
            "position": {"x": x, "y": y, "origin": "center"},
            "geometry": {"width": width},
        }
        if parent_id:
            payload["parent"] = {"id": parent_id}
        return self._request("POST", self._board_url("/texts"), payload)

    def create_connector(
        self,
        start_id: str,
        end_id: str,
        *,
        caption: str = "",
        start_snap: str = "auto",
        end_snap: str = "auto",
        start_pos: tuple[str, str] | None = None,
        end_pos: tuple[str, str] | None = None,
        shape: str = "elbowed",
        stroke_color: str = "#334155",
        stroke_width: str = "2",
        stroke_style: str = "normal",
        end_cap: str = "stealth",
        start_cap: str = "none",
        font_size: str = "13",
        text_color: str = "#0f172a",
    ) -> dict[str, Any]:
        start_item: dict[str, Any] = {"id": start_id}
        if start_pos is not None:
            start_item["position"] = {"x": start_pos[0], "y": start_pos[1]}
        else:
            start_item["snapTo"] = start_snap

        end_item: dict[str, Any] = {"id": end_id}
        if end_pos is not None:
            end_item["position"] = {"x": end_pos[0], "y": end_pos[1]}
        else:
            end_item["snapTo"] = end_snap

        payload: dict[str, Any] = {
            "startItem": start_item,
            "endItem": end_item,
            "shape": shape,
            "style": {
                "strokeColor": stroke_color,
                "strokeWidth": stroke_width,
                "strokeStyle": stroke_style,
                "startStrokeCap": start_cap,
                "endStrokeCap": end_cap,
                "fontSize": font_size,
                "color": text_color,
                "textOrientation": "horizontal",
            },
        }
        if caption:
            payload["captions"] = [
                {
                    "content": caption,
                    "position": "50%",
                    "textAlignVertical": "middle",
                }
            ]
        return self._request("POST", self._board_url("/connectors"), payload)
