from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

from PySide6.QtCore import QEvent, QEasingCurve, Property, QPropertyAnimation, Qt, QSize, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
	QCheckBox,
	QComboBox,
	QFrame,
	QGraphicsOpacityEffect,
	QHBoxLayout,
	QLabel,
	QLineEdit,
	QPlainTextEdit,
	QProgressBar,
	QPushButton,
	QRadioButton,
	QSlider,
	QSizePolicy,
	QSpinBox,
	QToolButton,
	QVBoxLayout,
	QWidget,
)


@dataclass
class ThemePalette:
	accent: QColor = field(default_factory=lambda: QColor("#FF00AA"))
	bg: QColor = field(default_factory=lambda: QColor("#000000"))
	panel: QColor = field(default_factory=lambda: QColor("#0B0B0B"))
	panel2: QColor = field(default_factory=lambda: QColor("#121212"))
	text: QColor = field(default_factory=lambda: QColor("#FFFFFF"))
	muted: QColor = field(default_factory=lambda: QColor("#B8B8B8"))
	prog_bg: QColor = field(default_factory=lambda: QColor("#333333"))
	divider: QColor = field(default_factory=lambda: QColor("#1E1E1E"))


DARK_PALETTE = ThemePalette(
	accent=QColor("#FF00AA"),
	bg=QColor("#000000"),
	panel=QColor("#0B0B0B"),
	panel2=QColor("#121212"),
	text=QColor("#FFFFFF"),
	muted=QColor("#B8B8B8"),
	prog_bg=QColor("#333333"),
	divider=QColor("#1E1E1E"),
)

LIGHT_PALETTE = ThemePalette(
	accent=QColor("#FF00AA"),
	bg=QColor("#FFFFFF"),
	panel=QColor("#F6F6F6"),
	panel2=QColor("#ECECEC"),
	text=QColor("#111111"),
	muted=QColor("#5A5A5A"),
	prog_bg=QColor("#D7D7D7"),
	divider=QColor("#D0D0D0"),
)

ACCENT = QColor(DARK_PALETTE.accent)
BG = QColor(DARK_PALETTE.bg)
PANEL = QColor(DARK_PALETTE.panel)
PANEL2 = QColor(DARK_PALETTE.panel2)
TEXT = QColor(DARK_PALETTE.text)
MUTED = QColor(DARK_PALETTE.muted)
PROG_BG = QColor(DARK_PALETTE.prog_bg)
DIVIDER = QColor(DARK_PALETTE.divider)


def set_theme(theme: ThemePalette) -> None:
	global ACCENT, BG, PANEL, PANEL2, TEXT, MUTED, PROG_BG, DIVIDER
	ACCENT = QColor(theme.accent)
	BG = QColor(theme.bg)
	PANEL = QColor(theme.panel)
	PANEL2 = QColor(theme.panel2)
	TEXT = QColor(theme.text)
	MUTED = QColor(theme.muted)
	PROG_BG = QColor(theme.prog_bg)
	DIVIDER = QColor(theme.divider)


def set_theme_mode(dark_mode: bool) -> None:
	set_theme(DARK_PALETTE if bool(dark_mode) else LIGHT_PALETTE)


def apply_theme_for_current_scheme() -> None:
	from PySide6.QtWidgets import QApplication

	app = QApplication.instance()
	if app is None:
		return
	set_theme_mode(app.styleHints().colorScheme() == Qt.ColorScheme.Dark)


def get_theme() -> ThemePalette:
	return ThemePalette(
		accent=QColor(ACCENT),
		bg=QColor(BG),
		panel=QColor(PANEL),
		panel2=QColor(PANEL2),
		text=QColor(TEXT),
		muted=QColor(MUTED),
		prog_bg=QColor(PROG_BG),
		divider=QColor(DIVIDER),
	)


apply_theme_for_current_scheme()


def qcolor_css(color: QColor) -> str:
	return f"rgb({color.red()},{color.green()},{color.blue()})"


def make_glyph_icon(glyph: str, size: int = 18, color: QColor = ACCENT) -> QIcon:
	pixmap = QPixmap(size * 2, size * 2)
	pixmap.fill(Qt.transparent)

	painter = QPainter(pixmap)
	painter.setRenderHint(QPainter.Antialiasing, True)
	painter.setPen(color)

	font = QFont("Segoe Fluent Icons")
	font.setPixelSize(int(size * 1.6))
	painter.setFont(font)
	painter.drawText(pixmap.rect(), Qt.AlignCenter, glyph)
	painter.end()

	return QIcon(pixmap)


GLYPH_GEAR = "\uE713"
GLYPH_SYSTEM = "\ue8ea"
GLYPH_NETWORK = "\uE770"
GLYPH_PERSONALIZE = "\ue771"
GLYPH_INTERNET = "\ue774"
GLYPH_DEVICES = "\ue772"
GLYPH_TIMELANG = "\ue775"
GLYPH_ACCESS = "\ue776"
GLYPH_UPDATE = "\ue895"
GLYPH_TEST = "\ue978"
GLYPH_CHEVRON_RIGHT = "\uE76C"
GLYPH_BACK = "\uE72B"


def line_edit_stylesheet() -> str:
	return f"""
	QLineEdit {{
		background: transparent;
		border: 1px solid {qcolor_css(MUTED)};
		border-radius: 2px;
		padding: 6px 10px;
		color: {qcolor_css(TEXT)};
		font-size: 14px;
	}}
	QLineEdit:focus {{
		border: 1px solid {qcolor_css(ACCENT)};
	}}
	"""


def primary_button_stylesheet() -> str:
	return f"""
	QPushButton {{
		background: {qcolor_css(ACCENT)};
		/* border: 1px solid {qcolor_css(ACCENT)}; */
		color: {qcolor_css(TEXT)};
		border-radius: 2px;
		padding: 6px 12px;
		font-size: 14px;
	}}
	QPushButton:hover {{  border: 1px solid {qcolor_css(TEXT)}; }}
	QPushButton:pressed {{ background: {qcolor_css(PANEL)}; }}
	"""


def neutral_button_stylesheet() -> str:
	return f"""
	QPushButton {{
		text-align: left;
		background: {qcolor_css(PANEL2)};
		border: 1px solid {qcolor_css(DIVIDER)};
		color: {qcolor_css(TEXT)};
		border-radius: 2px;
		padding: 6px 12px;
		font-size: 13px;
	}}
	QPushButton:hover {{
		border: 1px solid {qcolor_css(MUTED)};
	}}
	QPushButton:pressed {{
		border: 1px solid {qcolor_css(ACCENT)};
	}}
	"""


def combo_box_stylesheet() -> str:
	return f"""
	QComboBox {{
		background: transparent;
		border: 1px solid {qcolor_css(MUTED)};
		border-radius: 2px;
		padding: 6px 10px;
		color: {qcolor_css(TEXT)};
		font-size: 14px;
	}}
	QComboBox:hover {{
		border: 1px solid {qcolor_css(TEXT)};
	}}
	QComboBox:focus {{
		border: 1px solid {qcolor_css(ACCENT)};
	}}
	QComboBox::drop-down {{
		border: none;
		width: 26px;
	}}
	QComboBox QAbstractItemView {{
		background: {qcolor_css(PANEL2)};
		color: {qcolor_css(TEXT)};
		border: 1px solid {qcolor_css(DIVIDER)};
		selection-background-color: {qcolor_css(ACCENT)};
		selection-color: {qcolor_css(TEXT)};
	}}
	"""


def text_area_stylesheet() -> str:
	return f"""
	QPlainTextEdit {{
		background: transparent;
		border: 1px solid {qcolor_css(MUTED)};
		border-radius: 2px;
		padding: 8px 10px;
		color: {qcolor_css(TEXT)};
		font-size: 14px;
		selection-background-color: {qcolor_css(ACCENT)};
	}}
	QPlainTextEdit:focus {{
		border: 1px solid {qcolor_css(ACCENT)};
	}}
	"""


def radio_button_stylesheet() -> str:
	return f"""
	QRadioButton {{
		color: {qcolor_css(TEXT)};
		font-size: 14px;
		spacing: 8px;
	}}
	QRadioButton::indicator {{
		width: 16px;
		height: 16px;
		border-radius: 8px;
		border: 1px solid {qcolor_css(MUTED)};
		background: {qcolor_css(PANEL2)};
	}}
	QRadioButton::indicator:checked {{
		border: 1px solid {qcolor_css(ACCENT)};
		background: qradialgradient(
			cx: 0.5,
			cy: 0.5,
			radius: 0.6,
			fx: 0.5,
			fy: 0.5,
			stop: 0 {qcolor_css(ACCENT)},
			stop: 0.36 {qcolor_css(ACCENT)},
			stop: 0.37 {qcolor_css(PANEL2)},
			stop: 1 {qcolor_css(PANEL2)}
		);
	}}
	"""


def switch_stylesheet() -> str:
	return f"""
	QCheckBox {{
		color: {qcolor_css(TEXT)};
		font-size: 14px;
		spacing: 10px;
	}}
	QCheckBox::indicator {{
		width: 34px;
		height: 18px;
		border-radius: 9px;
		border: 1px solid {qcolor_css(MUTED)};
		background: {qcolor_css(PANEL2)};
	}}
	QCheckBox::indicator:checked {{
		background: {qcolor_css(ACCENT)};
		border: 1px solid {qcolor_css(ACCENT)};
	}}
	"""


def slider_stylesheet() -> str:
	return f"""
	QSlider::groove:horizontal {{
		height: 4px;
		background: {qcolor_css(DIVIDER)};
		border-radius: 2px;
	}}
	QSlider::handle:horizontal {{
		background: {qcolor_css(ACCENT)};
		width: 14px;
		height: 14px;
		margin: -5px 0;
		border-radius: 7px;
	}}
	QSlider::sub-page:horizontal {{
		background: {qcolor_css(ACCENT)};
		border-radius: 2px;
	}}
	"""


def progress_bar_stylesheet() -> str:
	return f"""
	QProgressBar {{
		background: {qcolor_css(PROG_BG)};
		border: none;
		border-radius: 10px;
		padding: 1px;
		color: {qcolor_css(TEXT)};
		text-align: center;
		font-size: 10px;
	}}
	QProgressBar::chunk {{
		background: {qcolor_css(ACCENT)};
		border-radius: 8px;
	}}
	"""


def spin_box_stylesheet() -> str:
	return f"""
	QSpinBox {{
		background: transparent;
		border: 1px solid {qcolor_css(MUTED)};
		border-radius: 2px;
		padding: 6px 10px;
		color: {qcolor_css(TEXT)};
		font-size: 14px;
	}}
	QSpinBox:focus {{
		border: 1px solid {qcolor_css(ACCENT)};
	}}
	QSpinBox::up-button,
	QSpinBox::down-button {{
		background: {qcolor_css(PANEL2)};
		border: none;
		width: 16px;
	}}
	"""


class Divider(QFrame):
	def __init__(self, thickness: int = 1):
		super().__init__()
		self.setFrameShape(QFrame.HLine)
		self.setFrameShadow(QFrame.Plain)
		self.setFixedHeight(thickness)
		self.setStyleSheet(f"background: {qcolor_css(DIVIDER)};")


class HeaderBar(QWidget):
	backClicked = Signal()

	def __init__(self, title: str, show_back: bool, left_icon: Optional[QIcon] = None):
		super().__init__()
		self._title = QLabel(title)
		self._title.setObjectName("HeaderTitle")

		self._back = QToolButton()
		self._back.setIcon(make_glyph_icon(GLYPH_BACK, 18, TEXT))
		self._back.setIconSize(QSize(18, 18))
		self._back.setAutoRaise(True)
		self._back.clicked.connect(self.backClicked.emit)

		self._left_icon = QLabel()
		self._left_icon.setFixedSize(22, 22)
		if left_icon is not None:
			self._left_icon.setPixmap(left_icon.pixmap(22, 22))
		else:
			self._left_icon.hide()

		row = QHBoxLayout(self)
		row.setContentsMargins(16, 14, 16, 12)
		row.setSpacing(10)

		if show_back:
			row.addWidget(self._back, 0, Qt.AlignVCenter)
		else:
			self._back.hide()

		row.addWidget(self._left_icon, 0, Qt.AlignVCenter)
		row.addWidget(self._title, 1, Qt.AlignVCenter)

		self.setStyleSheet(
			f"""
			QLabel#HeaderTitle {{
				color: {qcolor_css(TEXT)};
				font-size: 22px;
				font-weight: 600;
			}}
			QToolButton {{
				color: {qcolor_css(TEXT)};
			}}
			"""
		)


class NavRowItem(QFrame):
	clicked = Signal()

	def __init__(self, title: str, subtitle: str = "", icon: Optional[QIcon] = None):
		super().__init__()
		self.setCursor(Qt.PointingHandCursor)
		self._search_title = title
		self._search_subtitle = subtitle

		self.setStyleSheet(
			f"""
			QFrame {{
				background: transparent;
			}}
			QFrame:hover {{
				background: {qcolor_css(PANEL2)};
			}}
			"""
		)
		self.setFixedHeight(72)
		self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

		root = QHBoxLayout(self)
		root.setContentsMargins(16, 12, 16, 12)
		root.setSpacing(12)

		if icon:
			icon_label = QLabel()
			icon_label.setPixmap(icon.pixmap(24, 24))
			root.addWidget(icon_label, 0, Qt.AlignVCenter)

		text_column = QVBoxLayout()
		text_column.setSpacing(2)

		self.title_lbl = QLabel(title)
		self.title_lbl.setStyleSheet(
			f"color: {qcolor_css(TEXT)}; font-size: 16px; font-weight: 600;"
		)
		text_column.addWidget(self.title_lbl)

		if subtitle:
			self.sub_lbl = QLabel(subtitle)
			self.sub_lbl.setStyleSheet(f"color: {qcolor_css(MUTED)}; font-size: 12px;")
			text_column.addWidget(self.sub_lbl)

		root.addLayout(text_column, 1)

		chevron = QLabel()
		chevron.setPixmap(make_glyph_icon(GLYPH_CHEVRON_RIGHT, 14, MUTED).pixmap(14, 14))
		root.addWidget(chevron, 0, Qt.AlignVCenter)

	def mousePressEvent(self, event):
		if event.button() == Qt.LeftButton:
			self.clicked.emit()


class SectionTitle(QLabel):
	def __init__(self, text: str):
		super().__init__(text)
		self.setStyleSheet(
			f"""
			QLabel {{
				color: {qcolor_css(TEXT)};
				font-size: 22px;
				font-weight: 600;
				padding: 4px 0px;
			}}
			"""
		)


class SubHeading(QLabel):
	def __init__(self, text: str):
		super().__init__(text)
		self.setStyleSheet(
			f"""
			QLabel {{
				color: {qcolor_css(TEXT)};
				font-size: 18px;
				font-weight: 600;
				padding: 14px 0px 6px 0px;
			}}
			"""
		)


class InfoRow(QWidget):
	def __init__(self, label: str, value: str):
		super().__init__()
		row = QHBoxLayout(self)
		row.setContentsMargins(0, 0, 0, 0)
		row.setSpacing(8)

		left = QLabel(label)
		left.setStyleSheet(f"color: {qcolor_css(TEXT)}; font-size: 14px;")
		right = QLabel(value)
		right.setStyleSheet(f"color: {qcolor_css(TEXT)}; font-size: 14px;")
		right.setWordWrap(True)

		row.addWidget(left, 0, Qt.AlignTop)
		row.addWidget(right, 1, Qt.AlignTop)


class ToggleSwitch(QCheckBox):
	def __init__(self, text: str = "", parent: Optional[QWidget] = None):
		super().__init__(text, parent)
		self._track_w = 36
		self._track_h = 20
		self._thumb = 14
		self._margin = 3
		self._thumb_pos = 0.0
		self._thumb_anim = QPropertyAnimation(self, b"thumbPosition", self)
		self._thumb_anim.setDuration(140)
		self._thumb_anim.setEasingCurve(QEasingCurve.OutCubic)
		self.setCursor(Qt.PointingHandCursor)
		self.setMinimumHeight(24)
		self.toggled.connect(self._animate_thumb)

	def sizeHint(self):
		fm = QFontMetrics(self.font())
		text_w = fm.horizontalAdvance(self.text()) if self.text() else 0
		w = self._track_w + (10 if text_w else 0) + text_w
		h = max(self._track_h, fm.height()) + 4
		return QSize(w, h)

	def paintEvent(self, event):
		painter = QPainter(self)
		painter.setRenderHint(QPainter.Antialiasing, True)

		track_y = (self.height() - self._track_h) // 2
		track_rect = self.rect().adjusted(0, track_y, -(self.width() - self._track_w), -(self.height() - track_y - self._track_h))

		checked = self.isChecked()
		enabled = self.isEnabled()

		if checked:
			track_fill = QColor(ACCENT)
			track_border = QColor(ACCENT)
		else:
			track_fill = QColor(PANEL2)
			track_border = QColor(MUTED)

		if not enabled:
			track_fill.setAlpha(110)
			track_border.setAlpha(110)

		painter.setPen(track_border)
		painter.setBrush(track_fill)
		painter.drawRoundedRect(track_rect, self._track_h / 2, self._track_h / 2)

		travel = self._track_w - (2 * self._margin) - self._thumb
		thumb_x = track_rect.left() + self._margin + int(travel * self._thumb_pos)
		thumb_y = track_rect.top() + (self._track_h - self._thumb) // 2
		thumb_rect = track_rect.adjusted(thumb_x - track_rect.left(), thumb_y - track_rect.top(), -(track_rect.right() - thumb_x - self._thumb + 1), -(track_rect.bottom() - thumb_y - self._thumb + 1))

		thumb_color = QColor(TEXT) if checked else QColor(MUTED)
		if not enabled:
			thumb_color.setAlpha(120)
		painter.setPen(Qt.NoPen)
		painter.setBrush(thumb_color)
		painter.drawEllipse(thumb_rect)

		if self.text():
			text_rect = self.rect().adjusted(self._track_w + 10, 0, 0, 0)
			text_color = QColor(TEXT if enabled else MUTED)
			painter.setPen(text_color)
			painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, self.text())

		painter.end()

	def get_thumb_position(self) -> float:
		return self._thumb_pos

	def set_thumb_position(self, value: float) -> None:
		self._thumb_pos = max(0.0, min(1.0, float(value)))
		self.update()

	thumbPosition = Property(float, get_thumb_position, set_thumb_position)

	def _animate_thumb(self, checked: bool) -> None:
		self._thumb_anim.stop()
		self._thumb_anim.setStartValue(self._thumb_pos)
		self._thumb_anim.setEndValue(1.0 if checked else 0.0)
		self._thumb_anim.start()


class InWindowDialog(QWidget):
	accepted = Signal()
	rejected = Signal()

	def __init__(
		self,
		parent: QWidget,
		title: str = "Dialog",
		message: str = "",
		confirm_text: str = "OK",
		cancel_text: str = "Cancel",
	):
		super().__init__(parent)
		self.setAttribute(Qt.WA_StyledBackground, True)
		self.setStyleSheet(f"background: rgba(0, 0, 0, 0.80);")
		self.setGeometry(parent.rect())
		self._closing = False
		self._opacity_effect = QGraphicsOpacityEffect(self)
		self._opacity_effect.setOpacity(1.0)
		self.setGraphicsEffect(self._opacity_effect)
		self._fade_anim = QPropertyAnimation(self._opacity_effect, b"opacity", self)
		self._fade_anim.setDuration(160)
		self._fade_anim.setEasingCurve(QEasingCurve.InOutQuad)
		self._fade_anim.finished.connect(self._on_fade_finished)
		self.hide()

		parent.installEventFilter(self)

		root = QVBoxLayout(self)
		root.setContentsMargins(20, 20, 20, 20)
		root.setSpacing(0)
		root.setAlignment(Qt.AlignCenter)

		self._card = QFrame()
		self._card.setObjectName("DialogCard")
		self._card.setMinimumWidth(280)
		self._card.setMaximumWidth(420)

		card_l = QVBoxLayout(self._card)
		card_l.setContentsMargins(16, 16, 16, 14)
		card_l.setSpacing(10)

		self._title = QLabel(title)
		self._title.setObjectName("DialogTitle")
		card_l.addWidget(self._title)

		self._message = QLabel(message)
		self._message.setObjectName("DialogMessage")
		self._message.setWordWrap(True)
		self._message.setVisible(bool(message))
		card_l.addWidget(self._message)

		self._body_host = QWidget()
		self._body_layout = QVBoxLayout(self._body_host)
		self._body_layout.setContentsMargins(0, 2, 0, 2)
		self._body_layout.setSpacing(8)
		self._body_host.hide()
		card_l.addWidget(self._body_host)

		action_row = QHBoxLayout()
		action_row.setContentsMargins(0, 6, 0, 0)
		action_row.setSpacing(8)
		action_row.addStretch()

		self._cancel_btn = styled_button(cancel_text)
		self._confirm_btn = styled_button(confirm_text, primary=True)
		self._cancel_btn.clicked.connect(self.reject)
		self._confirm_btn.clicked.connect(self.accept)

		action_row.addWidget(self._cancel_btn)
		action_row.addWidget(self._confirm_btn)
		card_l.addLayout(action_row)

		root.addWidget(self._card)

		self._card.setStyleSheet(
			f"""
			QFrame#DialogCard {{
				background: {qcolor_css(PANEL)};
				border: 1px solid {qcolor_css(DIVIDER)};
				border-radius: 4px;
			}}
			QLabel#DialogTitle {{
				color: {qcolor_css(TEXT)};
				font-size: 17px;
				font-weight: 600;
			}}
			QLabel#DialogMessage {{
				color: {qcolor_css(MUTED)};
				font-size: 13px;
			}}
			"""
		)

	def eventFilter(self, watched, event):
		if watched is self.parentWidget() and event.type() in (QEvent.Resize, QEvent.Move, QEvent.Show):
			self.setGeometry(self.parentWidget().rect())
		return super().eventFilter(watched, event)

	def set_title(self, title: str) -> None:
		self._title.setText(title)

	def set_message(self, message: str) -> None:
		self._message.setText(message)
		self._message.setVisible(bool(message))

	def set_actions(self, confirm_text: str = "OK", cancel_text: str = "Cancel") -> None:
		self._confirm_btn.setText(confirm_text)
		self._cancel_btn.setText(cancel_text)

	def set_body(self, widget: Optional[QWidget]) -> None:
		while self._body_layout.count():
			item = self._body_layout.takeAt(0)
			child = item.widget()
			if child is not None:
				child.setParent(None)
		if widget is None:
			self._body_host.hide()
			return
		widget.setParent(self._body_host)
		self._body_layout.addWidget(widget)
		self._body_host.show()

	def open(self) -> None:
		self.setGeometry(self.parentWidget().rect())
		self._closing = False
		self._fade_anim.stop()
		self._opacity_effect.setOpacity(0.0)
		self.raise_()
		self.show()
		self._fade_anim.setStartValue(0.0)
		self._fade_anim.setEndValue(1.0)
		self._fade_anim.start()

	def close(self) -> None:
		if not self.isVisible():
			return
		self._closing = True
		self._fade_anim.stop()
		self._fade_anim.setStartValue(self._opacity_effect.opacity())
		self._fade_anim.setEndValue(0.0)
		self._fade_anim.start()

	def accept(self) -> None:
		self.accepted.emit()
		self.close()

	def reject(self) -> None:
		self.rejected.emit()
		self.close()

	def _on_fade_finished(self) -> None:
		if self._closing:
			self.hide()
			self._closing = False


class AnimatedProgressBar(QProgressBar):
	def __init__(self, parent: Optional[QWidget] = None):
		super().__init__(parent)
		self._value_anim = QPropertyAnimation(self, b"value", self)
		self._value_anim.setDuration(180)
		self._value_anim.setEasingCurve(QEasingCurve.OutCubic)

	def set_animated_value(self, value: int) -> None:
		value = max(self.minimum(), min(self.maximum(), int(value)))
		self._value_anim.stop()
		self._value_anim.setStartValue(self.value())
		self._value_anim.setEndValue(value)
		self._value_anim.start()


def styled_line_edit(placeholder: str = "", parent: Optional[QWidget] = None) -> QLineEdit:
	edit = QLineEdit(parent)
	if placeholder:
		edit.setPlaceholderText(placeholder)
	edit.setClearButtonEnabled(True)
	edit.setFixedHeight(36)
	edit.setStyleSheet(line_edit_stylesheet())
	return edit


def styled_button(text: str, parent: Optional[QWidget] = None, primary: bool = False) -> QPushButton:
	button = QPushButton(text, parent)
	button.setFixedHeight(38)
	button.setCursor(Qt.PointingHandCursor)
	button.setStyleSheet(primary_button_stylesheet() if primary else neutral_button_stylesheet())
	return button


def styled_checkbox(text: str, checked: bool = False, parent: Optional[QWidget] = None) -> QCheckBox:
	checkbox = QCheckBox(text, parent)
	checkbox.setChecked(checked)
	checkbox.setStyleSheet(
		f"""
		QCheckBox {{
			color: {qcolor_css(TEXT)};
			font-size: 14px;
			spacing: 8px;
		}}
		"""
	)
	return checkbox


def styled_switch(text: str, checked: bool = False, parent: Optional[QWidget] = None) -> QCheckBox:
	switch = ToggleSwitch(text, parent)
	switch.setChecked(checked)
	return switch


def styled_radio_button(text: str, checked: bool = False, parent: Optional[QWidget] = None) -> QRadioButton:
	radio = QRadioButton(text, parent)
	radio.setChecked(checked)
	radio.setStyleSheet(radio_button_stylesheet())
	return radio


def styled_combo_box(
	items: Optional[Sequence[str]] = None, parent: Optional[QWidget] = None
) -> QComboBox:
	combo = QComboBox(parent)
	combo.setFixedHeight(36)
	combo.setStyleSheet(combo_box_stylesheet())
	if items:
		combo.addItems(list(items))
	return combo


def styled_text_area(placeholder: str = "", parent: Optional[QWidget] = None) -> QPlainTextEdit:
	edit = QPlainTextEdit(parent)
	if placeholder:
		edit.setPlaceholderText(placeholder)
	edit.setMinimumHeight(100)
	edit.setStyleSheet(text_area_stylesheet())
	return edit


def styled_slider(
	value: int = 50,
	minimum: int = 0,
	maximum: int = 100,
	orientation: Qt.Orientation = Qt.Horizontal,
	parent: Optional[QWidget] = None,
) -> QSlider:
	slider = QSlider(orientation, parent)
	slider.setMinimum(minimum)
	slider.setMaximum(maximum)
	slider.setValue(value)
	slider.setStyleSheet(slider_stylesheet())
	return slider


def styled_progress_bar(
	value: int = 0,
	minimum: int = 0,
	maximum: int = 100,
	show_text: bool = True,
	parent: Optional[QWidget] = None,
) -> QProgressBar:
	bar = AnimatedProgressBar(parent)
	bar.setRange(minimum, maximum)
	bar.setValue(value)
	bar.setTextVisible(show_text)
	bar.setFixedHeight(8)
	bar.setStyleSheet(progress_bar_stylesheet())
	return bar


def styled_spin_box(
	value: int = 0,
	minimum: int = 0,
	maximum: int = 100,
	parent: Optional[QWidget] = None,
) -> QSpinBox:
	spin = QSpinBox(parent)
	spin.setRange(minimum, maximum)
	spin.setValue(value)
	spin.setFixedHeight(36)
	spin.setStyleSheet(spin_box_stylesheet())
	return spin


__all__ = [
	"ThemePalette",
	"set_theme",
	"set_theme_mode",
	"apply_theme_for_current_scheme",
	"get_theme",
	"DARK_PALETTE",
	"LIGHT_PALETTE",
	"ACCENT",
	"BG",
	"PANEL",
	"PANEL2",
	"TEXT",
	"MUTED",
	"DIVIDER",
	"qcolor_css",
	"make_glyph_icon",
	"line_edit_stylesheet",
	"primary_button_stylesheet",
	"neutral_button_stylesheet",
	"combo_box_stylesheet",
	"text_area_stylesheet",
	"radio_button_stylesheet",
	"switch_stylesheet",
	"slider_stylesheet",
	"progress_bar_stylesheet",
	"spin_box_stylesheet",
	"styled_line_edit",
	"styled_button",
	"styled_checkbox",
	"styled_switch",
	"styled_radio_button",
	"styled_combo_box",
	"styled_text_area",
	"styled_slider",
	"styled_progress_bar",
	"styled_spin_box",
	"GLYPH_GEAR",
	"GLYPH_SYSTEM",
	"GLYPH_NETWORK",
	"GLYPH_PERSONALIZE",
	"GLYPH_INTERNET",
	"GLYPH_DEVICES",
	"GLYPH_TIMELANG",
	"GLYPH_ACCESS",
	"GLYPH_UPDATE",
	"GLYPH_TEST",
	"GLYPH_CHEVRON_RIGHT",
	"GLYPH_BACK",
	"Divider",
	"HeaderBar",
	"NavRowItem",
	"SectionTitle",
	"SubHeading",
	"InfoRow",
	"ToggleSwitch",
	"InWindowDialog",
	"AnimatedProgressBar",
]
