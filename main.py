"""Desktop app entry point: `flet run` while developing, `flet build windows` to package it."""

import flet as ft

from ytmpd.gui import main

ft.run(main, assets_dir="assets")
