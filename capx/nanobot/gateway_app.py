from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from .channels import HttpBridgeChannel
from .runtime import CapxNanobotRuntime, CapxNanobotRuntimeConfig


class HttpBridgeInboundRequest(BaseModel):
    chat_id: str
    content: str
    sender_id: str | None = None
    media: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    session_key: str | None = None


class HttpBridgeActionResponse(BaseModel):
    status: str
    channel: str = "http"
    chat_id: str


class HttpBridgeOutboundItem(BaseModel):
    channel: str
    chat_id: str
    content: str
    reply_to: str | None = None
    media: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class HttpBridgeOutboundResponse(BaseModel):
    count: int
    messages: list[HttpBridgeOutboundItem] = Field(default_factory=list)


def create_gateway_app(
    config: CapxNanobotRuntimeConfig | None = None,
    *,
    runtime: CapxNanobotRuntime | None = None,
) -> FastAPI:
    app = FastAPI(
        title="cap-x Nanobot HTTP Gateway",
        description="Embedded HTTP bridge for the in-repo nanobot runtime.",
        version="1.0.0",
    )
    gateway_runtime = runtime or CapxNanobotRuntime(config or CapxNanobotRuntimeConfig())
    app.state.gateway_runtime = gateway_runtime

    @app.on_event("startup")
    async def _startup() -> None:
        await gateway_runtime.start()

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        await gateway_runtime.stop()

    def _get_http_channel() -> HttpBridgeChannel:
        channel = gateway_runtime.get_channel("http")
        if not isinstance(channel, HttpBridgeChannel):
            raise HTTPException(status_code=404, detail="HTTP bridge channel is not enabled")
        return channel

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "relay_base_url": gateway_runtime.config.shell.relay_base_url,
            "enabled_channels": gateway_runtime.channel_manager.enabled_channels,
            "channels": gateway_runtime.channel_manager.get_status(),
            "bus": {
                "inbound_size": gateway_runtime.bus.inbound_size,
                "outbound_size": gateway_runtime.bus.outbound_size,
            },
        }

    @app.get("/channels/status")
    async def channel_status() -> dict[str, Any]:
        return gateway_runtime.channel_manager.get_status()

    @app.post("/channels/http/inbound", response_model=HttpBridgeActionResponse)
    async def inbound_message(request: HttpBridgeInboundRequest) -> HttpBridgeActionResponse:
        if not request.content.strip():
            raise HTTPException(status_code=400, detail="content must not be empty")
        channel = _get_http_channel()
        await channel.receive_message(
            chat_id=request.chat_id,
            content=request.content,
            sender_id=request.sender_id,
            media=request.media,
            metadata=request.metadata,
            session_key=request.session_key,
        )
        return HttpBridgeActionResponse(status="queued", chat_id=request.chat_id)

    @app.get("/channels/http/outbound", response_model=HttpBridgeOutboundResponse)
    async def outbound_messages(
        chat_id: str | None = Query(default=None),
        limit: int = Query(default=20, ge=1, le=100),
        wait_ms: int = Query(default=0, ge=0, le=30000),
    ) -> HttpBridgeOutboundResponse:
        channel = _get_http_channel()
        messages = await channel.pop_outbound(chat_id=chat_id, limit=limit, wait_ms=wait_ms)
        items = [
            HttpBridgeOutboundItem(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content=msg.content,
                reply_to=msg.reply_to,
                media=list(msg.media),
                metadata=dict(msg.metadata),
            )
            for msg in messages
        ]
        return HttpBridgeOutboundResponse(count=len(items), messages=items)

    return app


__all__ = [
    "HttpBridgeActionResponse",
    "HttpBridgeInboundRequest",
    "HttpBridgeOutboundItem",
    "HttpBridgeOutboundResponse",
    "create_gateway_app",
]
