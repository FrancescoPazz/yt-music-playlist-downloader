"""Android-only Flet extension: text from the Share menu, and a foreground service for long downloads."""

from typing import Optional

import flet as ft
from flet.controls.base_control import control


@control("ShareReceiver")
class ShareReceiver(ft.Service):
    """Text shared to the app from Android's Share menu, such as a YouTube Music link."""

    on_shared: Optional[ft.EventHandler[ft.Event["ShareReceiver"]]] = None
    """Text shared while the app is running; it's in `e.data`."""

    async def get_initial(self) -> Optional[str]:
        """Text shared when the Share menu started the app, or None."""
        return await self._invoke_method("get_initial")


@control("KeepAlive")
class KeepAlive(ft.Service):
    """A foreground service with a notification: Android keeps the app (and its CPU) running with the screen off."""

    async def start(self, title: str, text: str, channel: str) -> bool:
        """Asks for the notification permission the first time (Android 13+). False if Android refused the service."""
        return await self._invoke_method("start", {"title": title, "text": text, "channel": channel})

    async def update(self, title: str, text: str) -> None:
        await self._invoke_method("update", {"title": title, "text": text})

    async def stop(self) -> None:
        await self._invoke_method("stop")
