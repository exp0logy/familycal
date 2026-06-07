"""
app/routers/plugins.py — Plugin management API.

Routes:
  GET    /api/plugins                    → PluginInfo[]
  PATCH  /api/plugins/{name}             → PluginInfo    body: { enabled: bool }
  GET    /api/plugins/{name}/settings    → settings object
  PUT    /api/plugins/{name}/settings    → settings object  (broadcasts settings.updated)

Disabled plugins still have their routes in the app's route table (FastAPI does
not support unmounting), but requests to disabled plugin routes return 404 via
the ``_require_enabled`` dependency so the contract in ARCHITECTURE §5 is met.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from app.plugins.registry import registry
from app.schemas import PluginInfo, PluginUpdate

router = APIRouter(prefix="/plugins", tags=["plugins"])


# ── Shared dependencies ───────────────────────────────────────────────────────

def _get_loader(request: Request):
    """Return the plugin loader, or raise 503 if unavailable."""
    loader = getattr(request.app.state, "plugin_loader", None)
    if loader is None:
        raise HTTPException(status_code=503, detail="Plugin system not available")
    return loader


def _require_enabled(name: str, request: Request) -> None:
    """Raise 404 if the plugin's router is currently disabled."""
    loader = getattr(request.app.state, "plugin_loader", None)
    if loader is not None and loader.is_plugin_disabled(name):
        raise HTTPException(status_code=404, detail=f"Plugin {name!r} is disabled")


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[PluginInfo])
async def list_plugins(request: Request) -> list[PluginInfo]:
    """Return info for all discovered plugins."""
    loader = getattr(request.app.state, "plugin_loader", None)
    if loader is None:
        return []
    infos = await loader.get_plugin_info_list()
    return [PluginInfo(**info) for info in infos]


@router.patch("/{name}", response_model=PluginInfo)
async def toggle_plugin(
    name: str,
    body: PluginUpdate,
    request: Request,
) -> PluginInfo:
    """Enable or disable a plugin at runtime."""
    loader = _get_loader(request)

    if name not in registry:
        raise HTTPException(status_code=404, detail=f"Plugin {name!r} not found")

    ok = await loader.enable_plugin(name) if body.enabled else await loader.disable_plugin(name)

    if not ok:
        raise HTTPException(status_code=500, detail=f"Failed to toggle plugin {name!r}")

    infos = await loader.get_plugin_info_list()
    for info in infos:
        if info["name"] == name:
            return PluginInfo(**info)

    raise HTTPException(status_code=404, detail=f"Plugin {name!r} disappeared after toggle")


@router.get("/{name}/settings")
async def get_plugin_settings(
    name: str,
    request: Request,
    _enabled: None = Depends(_require_enabled),
) -> dict[str, Any]:
    """Return the current settings for a plugin."""
    if name not in registry:
        raise HTTPException(status_code=404, detail=f"Plugin {name!r} not found")
    loader = _get_loader(request)
    return await loader.get_plugin_settings(name)


@router.put("/{name}/settings")
async def put_plugin_settings(
    name: str,
    settings: dict[str, Any],
    request: Request,
    _enabled: None = Depends(_require_enabled),
) -> dict[str, Any]:
    """Update settings for a plugin.

    Validates the body against the manifest schema (type-checks declared keys;
    extra keys are passed through).  Persists and broadcasts settings.updated.
    """
    if name not in registry:
        raise HTTPException(status_code=404, detail=f"Plugin {name!r} not found")
    loader = _get_loader(request)

    plugin = registry.get(name)

    # Validate against the manifest schema if one is declared.
    schema = plugin.manifest.settings_schema
    if schema and schema.get("properties"):
        errors: list[str] = []
        for prop_name, prop_schema in schema["properties"].items():
            if prop_name not in settings:
                continue   # missing keys are fine; defaults fill them in
            val = settings[prop_name]
            expected_type = prop_schema.get("type")
            if expected_type == "integer" and not isinstance(val, int):
                errors.append(f"{prop_name!r}: expected integer, got {type(val).__name__}")
            elif expected_type == "number" and not isinstance(val, (int, float)):
                errors.append(f"{prop_name!r}: expected number, got {type(val).__name__}")
            elif expected_type == "string" and not isinstance(val, str):
                errors.append(f"{prop_name!r}: expected string, got {type(val).__name__}")
            elif expected_type == "boolean" and not isinstance(val, bool):
                errors.append(f"{prop_name!r}: expected boolean, got {type(val).__name__}")
            elif expected_type == "array" and not isinstance(val, list):
                errors.append(f"{prop_name!r}: expected array, got {type(val).__name__}")
        if errors:
            raise HTTPException(
                status_code=422,
                detail={"message": "Settings validation failed", "errors": errors},
            )

    # set_plugin_settings persists AND broadcasts settings.updated.
    return await loader.set_plugin_settings(name, settings)
