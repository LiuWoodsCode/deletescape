from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel, QMdiSubWindow, QLineEdit
from PySide6.QtCore import Qt, QTimer, QEvent, QObject, QSize
from PySide6.QtGui import QIcon
from datetime import datetime




class Taskbar(QWidget):
    """A minimal taskbar showing running apps and allowing quick activation.

    This is intentionally simple: it renders a button per running app and
    activates the associated MDI subwindow when clicked. If an app isn't
    running it will launch it via the shell.
    """

    def __init__(self, shell):
        super().__init__()
        self.shell = shell
        self.setFixedHeight(40)

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(6, 4, 6, 4)
        self._layout.setSpacing(6)
        self._layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.setSizePolicy(self.sizePolicy().horizontalPolicy(), self.sizePolicy().verticalPolicy())

        self._buttons = {}
        # Left-most "Apps" button that opens the home app as a frameless panel
        # Icon-only Apps button (Win10-style)
        self._apps_button = QPushButton()
        try:
            self._apps_button.setToolTip('Apps')
        except Exception:
            pass
        self._apps_button.clicked.connect(self._on_apps_click)
        # Set a Win10-style Apps icon if available and make the button icon-sized
        try:
            icon = QIcon('assets/icons/convergance/applauncher.svg')
            self._apps_button.setIcon(icon)
            icon_size = QSize(20, 20)
            try:
                self._apps_button.setIconSize(icon_size)
            except Exception:
                pass
            try:
                # Make button flat and remove any background/border
                self._apps_button.setFlat(True)
            except Exception:
                pass
            try:
                self._apps_button.setStyleSheet('border: none; background: transparent;')
            except Exception:
                pass
            try:
                # Size the button tightly around the icon
                self._apps_button.setFixedSize(icon_size.width() + 8, icon_size.height() + 8)
            except Exception:
                pass
        except Exception:
            pass
        self._layout.addWidget(self._apps_button)
        # Search box next to Apps (UI only for now)
        self._search = QLineEdit()
        try:
            self._search.setPlaceholderText('Search apps, settings...')
        except Exception:
            pass
        try:
            self._search.setFixedWidth(200)
        except Exception:
            pass
        try:
            self._search.setClearButtonEnabled(True)
        except Exception:
            pass
        self._layout.addWidget(self._search)
        # Dummy Overview button next to search (icon-only)
        try:
            self._overview_button = QPushButton()
            try:
                self._overview_button.setToolTip('Overview')
            except Exception:
                pass
            try:
                ov_icon = QIcon('assets/icons/convergance/overview.svg')
                self._overview_button.setIcon(ov_icon)
                ov_icon_size = QSize(20, 20)
                try:
                    self._overview_button.setIconSize(ov_icon_size)
                except Exception:
                    pass
            except Exception:
                ov_icon_size = QSize(20, 20)
            try:
                self._overview_button.setFlat(True)
            except Exception:
                pass
            try:
                self._overview_button.setStyleSheet('border: none; background: transparent;')
            except Exception:
                pass
            try:
                self._overview_button.clicked.connect(self._on_overview_click)
            except Exception:
                try:
                    self._overview_button.clicked.connect(lambda: None)
                except Exception:
                    pass
            self._layout.addWidget(self._overview_button)
        except Exception:
            pass
        # Clock label on the right-hand side (time + date stacked)
        self._clock = QLabel("")
        # Slightly wider to accommodate two lines (time + date)
        try:
            self._clock.setFixedWidth(100)
        except Exception:
            pass
        self._clock.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        try:
            self._clock.setWordWrap(True)
        except Exception:
            pass

        # Add a stretch and then the clock so buttons appear on the left
        self._layout.addStretch(1)
        self._layout.addWidget(self._clock)

        # Timer to update clock text every second
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)
        self._update_clock()

    def clear(self):
        # Remove only the dynamic app buttons, preserve clock and spacer
        for w in list(self._buttons.values()):
            try:
                self._layout.removeWidget(w)
            except Exception:
                pass
            try:
                w.deleteLater()
            except Exception:
                pass
        self._buttons.clear()

    def refresh(self):
        """Rebuild taskbar buttons from current shell state."""
        self.clear()

        # Prune stale/hidden windows and show truly running apps.
        running_ids = []
        for app_id, sub in list(self.shell._running.items()):
            keep = False
            try:
                keep = bool(sub is not None and sub.isVisible())
            except Exception:
                keep = False

            if keep:
                running_ids.append(app_id)
            else:
                self.shell._running.pop(app_id, None)

        # Show running apps first (insert to the right of the Apps button)
        try:
            apps_idx = self._layout.indexOf(self._apps_button)
        except Exception:
            apps_idx = -1

        # Determine insertion index: after the search box if present, otherwise after Apps
        try:
            if hasattr(self, '_search') and self._layout.indexOf(self._search) >= 0:
                insert_idx = self._layout.indexOf(self._search) + 2
            elif apps_idx >= 0:
                insert_idx = apps_idx + 1
            else:
                insert_idx = 0
        except Exception:
            insert_idx = apps_idx + 1 if apps_idx >= 0 else 0

        for app_id in running_ids:
            desc = self.shell.apps.get(app_id)
            label = (desc.display_name if desc and getattr(desc, 'display_name', None) else app_id)
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(self.shell.active_app_id == app_id)
            btn.clicked.connect(lambda checked, aid=app_id: self._on_click(aid))
            # Insert buttons to the left of the stretch/clock so they appear on the left
            # but keep the Apps button as the far-left control.
            if insert_idx >= 0:
                self._layout.insertWidget(insert_idx, btn)
                insert_idx += 1
            else:
                self._layout.insertWidget(0, btn)
            self._buttons[app_id] = btn

        # Small spacer to take remaining space on the right
        # Spacer and clock are managed in __init__, nothing more to do here

    def _update_clock(self):
        try:
            # Prefer shell-provided formatting if available
            now = datetime.now()
            if hasattr(self.shell, 'format_time'):
                time_text = self.shell.format_time(now)
            else:
                time_text = now.strftime('%H:%M')

            # Date shown on the line below the time (short month + day)
            try:
                date_text = now.strftime('%b %d')
            except Exception:
                date_text = now.strftime('%Y-%m-%d')

            # Two-line display: time on first line, date below
            try:
                self._clock.setText(f"{time_text}\n{date_text}")
            except Exception:
                self._clock.setText(time_text)
        except Exception:
            pass

    def _on_click(self, app_id: str):
        # If running, toggle focus/visibility; otherwise launch
        try:
            running = self.shell._running.get(app_id)
        except Exception:
            running = None

        sub = None
        try:
            # Try to find the QMdiSubWindow wrapper for the running app widget.
            for s in list(self.shell.mdi.subWindowList()):
                try:
                    # s.widget() is the inner container in many codepaths
                    if s is running or s.widget() is running:
                        sub = s
                        break
                except Exception:
                    continue

            # If we didn't find it yet, but running itself is a subwindow-like object,
            # accept it directly (best-effort).
            if sub is None and isinstance(running, QMdiSubWindow):
                sub = running
        except Exception:
            sub = None

        if sub is not None:
            try:
                active = None
                try:
                    active = self.shell.mdi.activeSubWindow()
                except Exception:
                    active = None

                # If already active, hide/minimize it; otherwise show and activate.
                if active is sub:
                    try:
                        if sub.isVisible():
                            sub.hide()
                        else:
                            sub.show()
                            try:
                                self.shell.mdi.setActiveSubWindow(sub)
                            except Exception:
                                pass
                    except Exception:
                        try:
                            sub.close()
                        except Exception:
                            pass
                else:
                    try:
                        if not sub.isVisible():
                            sub.show()
                        self.shell.mdi.setActiveSubWindow(sub)
                    except Exception:
                        try:
                            sub.show()
                        except Exception:
                            pass

                # Update button checked state to reflect new active app
                try:
                    btn = self._buttons.get(app_id)
                    if btn is not None:
                        btn.setChecked(self.shell.active_app_id == app_id or (self.shell.mdi.activeSubWindow() is sub))
                except Exception:
                    pass

                return
            except Exception:
                pass

        # Not running or no subwindow found -> try launching
        try:
            self.shell.launch_app(app_id)
        except Exception:
            pass

    def _on_apps_click(self):
        # Open the home app as a frameless panel in the lower-left corner.
        try:
            app_id = 'desktopapplauncher'
            # If already running, adjust its subwindow.
            if app_id in self.shell._running:
                running = self.shell._running.get(app_id)
                self._adjust_home_subwindow(running)
                return

            # Launch and adjust shortly after creation so sizes are available.
            try:
                self.shell.launch_app(app_id)
            except Exception:
                return

            QTimer.singleShot(0, lambda: self._adjust_home_subwindow(self.shell._running.get(app_id)))
        except Exception:
            pass

    def _on_overview_click(self):
        # Dummy handler for the overview button (no-op for now)
        try:
            return
        except Exception:
            pass

    def _adjust_home_subwindow(self, running):
        try:
            if running is None:
                return

            # Find the QMdiSubWindow wrapper for the running widget (could be stored inconsistently).
            sw = None
            try:
                for s in list(self.shell.mdi.subWindowList()):
                    try:
                        if s is running or s.widget() is running:
                            sw = s
                            break
                    except Exception:
                        continue
            except Exception:
                sw = None

            if sw is None:
                return

            # Make it frameless and position lower-left inside the MDI area.
            sw.setWindowFlags(sw.windowFlags() | Qt.FramelessWindowHint)
            sw.show()

            mdi = self.shell.mdi
            # ensure geometry / sizes are up to date
            sw.adjustSize()
            w = sw.width() or sw.sizeHint().width()
            h = sw.height() or sw.sizeHint().height()
            x = 6
            try:
                y = max(7, mdi.height() - h - 6)
            except Exception:
                y = max(9, self.height() - h - 46)

            sw.move(x, y)
            sw.raise_()
            sw.show()
            # Install a click-away filter on the MDI area so clicking outside closes it.
            try:
                mdi_widget = self.shell.mdi

                class _ClickAwayFilter(QObject):
                    def __init__(self, parent, subwindow):
                        super().__init__(parent)
                        self._subwindow = subwindow

                    def eventFilter(self, obj, event):
                        try:
                            if event.type() == QEvent.MouseButtonPress:
                                pos = event.pos()
                                # If click is outside the subwindow geometry, close it.
                                try:
                                    rect = self._subwindow.geometry()
                                except Exception:
                                    rect = None

                                if rect is None or not rect.contains(pos):
                                    try:
                                        self._subwindow.close()
                                    except Exception:
                                        try:
                                            self._subwindow.hide()
                                        except Exception:
                                            pass
                                    try:
                                        obj.removeEventFilter(self)
                                    except Exception:
                                        pass
                                    return False
                        except Exception:
                            pass
                        return False

                # Remove any existing filter first
                try:
                    if hasattr(self, '_home_click_filter') and self._home_click_filter is not None:
                        try:
                            mdi_widget.removeEventFilter(self._home_click_filter)
                        except Exception:
                            pass
                        self._home_click_filter = None
                except Exception:
                    pass

                # Create and install new filter
                try:
                    self._home_click_filter = _ClickAwayFilter(mdi_widget, sw)
                    mdi_widget.installEventFilter(self._home_click_filter)
                except Exception:
                    self._home_click_filter = None

                # Ensure filter is removed when the subwindow is destroyed
                def _cleanup():
                    try:
                        if hasattr(self, '_home_click_filter') and self._home_click_filter is not None:
                            try:
                                mdi_widget.removeEventFilter(self._home_click_filter)
                            except Exception:
                                pass
                            self._home_click_filter = None
                    except Exception:
                        pass

                try:
                    sw.destroyed.connect(_cleanup)
                except Exception:
                    pass
            except Exception:
                pass
        except Exception:
            pass
