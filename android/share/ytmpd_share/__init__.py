"""Text shared to the app from Android's Share menu, such as a YouTube Music link. Flet extension, Android only."""

from typing import Optional

import flet as ft
from flet.controls.base_control import control


@control("ShareReceiver")
class ShareReceiver(ft.Service):
    on_shared: Optional[ft.EventHandler[ft.Event["ShareReceiver"]]] = None
    """Text shared while the app is running; it's in `e.data`."""

    async def get_initial(self) -> Optional[str]:
        """Text shared when the Share menu started the app, or None."""
        return await self._invoke_method("get_initial")
