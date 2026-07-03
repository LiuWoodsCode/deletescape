#!/usr/bin/env python3

import subprocess

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")

from gi.repository import Gtk, GtkLayerShell


class Keyboard(Gtk.Application):

    def __init__(self):
        super().__init__(
            application_id="org.deletescape.VirtualKeyboard"
        )

    def press(self, text):
        subprocess.run(
            ["wtype", text],
            check=False,
        )

    def special(self, key):
        subprocess.run(
            ["wtype", "-k", key],
            check=False,
        )

    def do_activate(self):

        win = Gtk.ApplicationWindow(application=self)
        win.set_title("Keyboard")
        win.set_resizable(False)

        GtkLayerShell.init_for_window(win)

        GtkLayerShell.set_layer(
            win,
            GtkLayerShell.Layer.BOTTOM,
        )

        GtkLayerShell.set_anchor(
            win,
            GtkLayerShell.Edge.LEFT,
            True,
        )

        GtkLayerShell.set_anchor(
            win,
            GtkLayerShell.Edge.RIGHT,
            True,
        )

        GtkLayerShell.set_anchor(
            win,
            GtkLayerShell.Edge.BOTTOM,
            True,
        )

        GtkLayerShell.auto_exclusive_zone_enable(win)

        grid = Gtk.Grid(
            column_spacing=4,
            row_spacing=4,
            margin_top=8,
            margin_bottom=8,
            margin_start=8,
            margin_end=8,
        )

        win.add(grid)

        rows = [
            "qwertyuiop",
            "asdfghjkl",
            "zxcvbnm",
        ]

        for r, letters in enumerate(rows):
            for c, letter in enumerate(letters):
                button = Gtk.Button(label=letter)

                button.connect(
                    "clicked",
                    lambda _, l=letter: self.press(l),
                )

                grid.attach(
                    button,
                    c,
                    r,
                    1,
                    1,
                )

        r = len(rows)

        space = Gtk.Button(label="Space")
        space.connect(
            "clicked",
            lambda *_: self.press(" "),
        )

        back = Gtk.Button(label="⌫")
        back.connect(
            "clicked",
            lambda *_: self.special("BackSpace"),
        )

        enter = Gtk.Button(label="Enter")
        enter.connect(
            "clicked",
            lambda *_: self.special("Return"),
        )

        grid.attach(space, 0, r, 5, 1)
        grid.attach(back, 5, r, 2, 1)
        grid.attach(enter, 7, r, 2, 1)

        win.show_all()


Keyboard().run()