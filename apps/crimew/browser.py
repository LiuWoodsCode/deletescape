# Copyright (C) 2023 The Qt Company Ltd.
# SPDX-License-Identifier: LicenseRef-Qt-Commercial OR BSD-3-Clause
from __future__ import annotations

from PySide6.QtWebEngineCore import (qWebEngineChromiumVersion,
                                     QWebEngineProfile, QWebEngineSettings)
from PySide6.QtCore import QObject, Qt, Slot

from downloadmanagerwidget import DownloadManagerWidget
from browserwindow import BrowserWindow
import flags
import platform


class Browser(QObject):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._windows = []
        self._download_manager_widget = DownloadManagerWidget()
        self._profile = None

        # Quit application if the download manager window is the only
        # remaining window
        self._download_manager_widget.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)

    def generate_user_agent(self, chromium_version: str, mobile: bool = False) -> str:
        system = platform.system()
        machine = platform.machine().lower()
        crimewver = flags.get_app_version()
        # Normalize architecture
        if machine in ("amd64", "x86_64"):
            arch = "Win64; x64" if system == "Windows" else "x86_64"
        elif "arm" in machine or "aarch" in machine:
            arch = "ARM64"
        else:
            arch = machine

        # Desktop platform strings
        if not mobile:
            if system == "Windows":
                os_part = f"Windows NT 10.0; {arch}"
            elif system == "Darwin":
                os_part = "Macintosh; Intel Mac OS X 10_15_7"
            elif system == "Linux":
                os_part = f"X11; Linux {arch}"
            else:
                os_part = f"{system} {arch}"

            ua = (
                f"Mozilla/5.0 ({os_part}) "
                f"AppleWebKit/537.36 (KHTML, like Gecko) "
                f"Chrome/{chromium_version} Safari/537.36"
            )

        # Mobile platform strings (fake but believable)
        else:
            if system == "Darwin":
                # Pretend iPhone (WebKit-based anyway)
                os_part = "iPhone; CPU iPhone OS 17_0 like Mac OS X"
                mobile_tag = "Mobile/15E148"
            else:
                # Default to Android-style UA
                os_part = "Linux; Android 16; Grizzco Mobile"
                mobile_tag = "Mobile Safari/537.36"

            ua = (
                f"Mozilla/5.0 ({os_part}) "
                f"AppleWebKit/537.36 (KHTML, like Gecko) "
                f"Chrome/{chromium_version} {mobile_tag}"
            )

        ua = ua + f" Crimew/{crimewver}"
        return ua
        
    def create_hidden_window(self, offTheRecord=False, parent_container=None):
        if not offTheRecord and not self._profile:
            name = "simplebrowser." + qWebEngineChromiumVersion()
            self._profile = QWebEngineProfile(name)
            user_data_dir = flags.get_user_data_dir()
            self._profile.setPersistentStoragePath(str(user_data_dir / "Profile"))
            self._profile.setCachePath(str(user_data_dir / "Cache"))
            self._profile.setHttpUserAgent(self.generate_user_agent(qWebEngineChromiumVersion(), mobile=False))
            s = self._profile.settings()
            s.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, True)
            s.setAttribute(QWebEngineSettings.WebAttribute.DnsPrefetchEnabled, True)
            s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
            s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, False)
            s.setAttribute(QWebEngineSettings.ScreenCaptureEnabled, True)
            self._profile.downloadRequested.connect(
                self._download_manager_widget.download_requested)

        profile = QWebEngineProfile.defaultProfile() if offTheRecord else self._profile
        main_window = BrowserWindow(self, profile, False)
        profile.setPersistentPermissionsPolicy(
            QWebEngineProfile.PersistentPermissionsPolicy.AskEveryTime)

        # If a parent_container is provided, reparent the BrowserWindow's
        # central widget (which contains the tab widget and progress bar)
        # and toolbar into the container and return a proxy object that
        # shows/hides the embedded widgets instead of the toplevel window.
        if parent_container is not None:
            # ensure container has a layout
            from PySide6.QtWidgets import QVBoxLayout, QToolBar

            if not parent_container.layout():
                parent_container.setLayout(QVBoxLayout(parent_container))

            central = main_window.centralWidget()
            # move toolbar(s) into the container too
            toolbars = main_window.findChildren(QToolBar)
            for tb in toolbars:
                tb.setParent(parent_container)
                parent_container.layout().addWidget(tb)

            if central:
                central.setParent(parent_container)
                parent_container.layout().addWidget(central)

            self._windows.append(main_window)
            main_window.about_to_close.connect(self._remove_window)

            class EmbeddedProxy:
                def __init__(self, main_window, embedded_widget, toolbars):
                    self._main = main_window
                    self._widget = embedded_widget
                    self._toolbars = toolbars

                def show(self):
                    if self._toolbars:
                        for t in self._toolbars:
                            t.show()
                    if self._widget:
                        self._widget.show()

                def hide(self):
                    if self._toolbars:
                        for t in self._toolbars:
                            t.hide()
                    if self._widget:
                        self._widget.hide()

                def close(self):
                    # forward close to the main window to trigger cleanup
                    try:
                        self._main.close()
                    except Exception:
                        pass

                def raise_(self):
                    if self._widget:
                        self._widget.raise_()

                def activateWindow(self):
                    if self._widget:
                        self._widget.activateWindow()

                def tab_widget(self):
                    return self._main.tab_widget()

            return EmbeddedProxy(main_window, central, toolbars)

        self._windows.append(main_window)
        main_window.about_to_close.connect(self._remove_window)
        return main_window

    def create_window(self, offTheRecord=False):
        main_window = self.create_hidden_window(offTheRecord)
        main_window.show()
        return main_window

    def create_dev_tools_window(self):
        profile = (self._profile if self._profile
                   else QWebEngineProfile.defaultProfile())
        main_window = BrowserWindow(self, profile, True)
        self._windows.append(main_window)
        main_window.about_to_close.connect(self._remove_window)
        main_window.show()
        return main_window

    def windows(self):
        return self._windows

    def download_manager_widget(self):
        return self._download_manager_widget

    @Slot()
    def _remove_window(self):
        w = self.sender()
        if w in self._windows:
            del self._windows[self._windows.index(w)]
