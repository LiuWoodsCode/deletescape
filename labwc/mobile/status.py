from __future__ import annotations

import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import GLib, Gtk, GtkLayerShell


BAR_HEIGHT = 24


class StatusBar(Gtk.Window):
    def __init__(self) -> None:
        super().__init__(title="deletescape mobile status")

        self.set_decorated(False)
        self.set_resizable(False)
        self.set_default_size(1, BAR_HEIGHT)

        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_layer(self, GtkLayerShell.Layer.TOP)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.TOP, True)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.LEFT, True)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.RIGHT, True)
        GtkLayerShell.set_exclusive_zone(self, BAR_HEIGHT)

        self._install_css()
        self.clock = Gtk.Label()
        self.clock.set_xalign(0.0)
        self.clock.set_margin_start(8)
        self.clock.set_margin_end(8)

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        box.set_size_request(-1, BAR_HEIGHT)
        box.pack_start(self.clock, True, True, 0)
        self.add(box)

        self._update_clock()
        GLib.timeout_add_seconds(1, self._update_clock)

    def _update_clock(self) -> bool:
        self.clock.set_text(time.strftime("%H:%M"))
        return True


    def _install_css(self) -> None:
        css = b"""
        window {
            background: #202020;
            color: white;
            font-size: 12px;
        }
        button.taskbar-button,
        button.apps-button {
            background: #303030;
            border: 1px solid #505050;
            border-radius: 0;
            color: white;
            min-height: 28px;
            padding: 1px 6px;
        }
        button.taskbar-button {
            min-width: 34px;
        }
        button.apps-button {
            min-width: 64px;
            padding: 1px 10px;
        }
        button.taskbar-button:hover,
        button.apps-button:hover {
            background: #404040;
        }
        button.taskbar-button.active {
            background: #34445a;
            border-color: #7fb5ff;
        }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_screen(
            self.get_screen(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

def main() -> None:
    bar = StatusBar()
    bar.connect("destroy", Gtk.main_quit)
    bar.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
