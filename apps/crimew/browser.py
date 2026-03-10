# Copyright (C) 2023 The Qt Company Ltd.
# SPDX-License-Identifier: LicenseRef-Qt-Commercial OR BSD-3-Clause
from __future__ import annotations

from PySide6.QtWebEngineCore import (qWebEngineChromiumVersion,
                                     QWebEngineProfile, QWebEngineSettings)
from PySide6.QtCore import QObject, Qt, Slot

from downloadmanagerwidget import DownloadManagerWidget
from browserwindow import BrowserWindow


class Browser(QObject):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._windows = []
        self._download_manager_widget = DownloadManagerWidget()
        self._profile = None

        # Quit application if the download manager window is the only
        # remaining window
        self._download_manager_widget.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)

    def create_hidden_window(self, offTheRecord=False, parent_container=None):
        if not offTheRecord and not self._profile:
            name = "simplebrowser." + qWebEngineChromiumVersion()
            self._profile = QWebEngineProfile(name)
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
