"""Shared appearance, saved per data folder and applied to every open window."""
from pathlib import Path
from PyQt6.QtCore import QObject, QSettings, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

MODES = ('System', 'Light', 'Dark')
SORT_ORDERS = ('Newest first', 'Title A–Z', 'Due now first')
DEFAULT_FILTERS = ('All statuses', 'Active', 'Paused', 'Completed')
LIGHT = dict(bg='#f2f2f2', bg2='#f2f2f2', panel='#ffffff', text='#191919',
             secondary='#555555', muted='#686868', border='#dedede', field='#f7f7f7',
             button='#ebebeb', hover='#dedede', accent='#191919', accentHover='#353535',
             selected='#eeeeee', selectedBorder='#a0a0a0', selectedText='#111111',
             disabled='#969696', scroll='#bcbcbc', danger='#333333', dangerBg='#e6e6e6',
             green='#333333', greenBg='#eeeeee', amber='#555555', amberBg='#eeeeee',
             neutral='#666666', neutralBg='#eeeeee')
DARK = dict(bg='#202020', bg2='#202020', panel='#292929', text='#f4f4f4',
            secondary='#cccccc', muted='#b0b0b0', border='#444444', field='#242424',
            button='#383838', hover='#474747', accent='#f2f2f2', accentHover='#d8d8d8',
            selected='#3c3c3c', selectedBorder='#808080', selectedText='#ffffff',
            disabled='#858585', scroll='#686868', danger='#dddddd', dangerBg='#424242',
            green='#eeeeee', greenBg='#424242', amber='#d3d3d3', amberBg='#424242',
            neutral='#bcbcbc', neutralBg='#383838')

TEMPLATE = '''
QWidget { color: $text; font-family: 'Segoe UI Variable', 'Segoe UI'; font-size: 13px; }
QWidget#window, QDialog { background: $bg; }
QWidget#window { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 $bg,stop:1 $bg2); }
QLabel { background: transparent; }
QLabel#brand { font-size: 16px; font-weight: 650; letter-spacing: -0.3px; }
QLabel#eyebrow { color: $muted; font-size: 10px; font-weight: 600; letter-spacing: 1.6px; }
QLabel#heading { font-size: 30px; font-weight: 700; letter-spacing: -0.8px; }
QLabel#subtitle { color: $secondary; font-size: 13px; }
QLabel#muted { color: $muted; font-size: 12px; }
QLabel#section { color: $muted; font-size: 10px; font-weight: 650; letter-spacing: 1.2px; }
QLabel#detailTitle { font-size: 22px; font-weight: 650; }
QLabel#badge { border-radius: 9px; padding: 5px 10px; font-size: 10px; font-weight: 600; }
QLabel#summary { color: $secondary; font-size: 12px; }
QFrame#panel { background: $panel; border: 1px solid $border; border-radius: 18px; }
QFrame#line { background: $border; max-height: 1px; border: none; }
QPushButton { background: $button; border: 1px solid transparent; border-radius: 10px; padding: 10px 14px; font-weight: 600; }
QPushButton:hover { background: $hover; }
QPushButton:pressed { background: $border; }
QPushButton:focus { border: 1px solid $accent; }
QPushButton:disabled { color: $disabled; background: $field; }
QPushButton#primary { background: $accent; color: $primaryText; }
QPushButton#primary:hover { background: $accentHover; }
QPushButton#primary:disabled { color: $disabled; background: $button; }
QPushButton#danger { color: $danger; background: transparent; text-align: left; padding-left: 0; }
QPushButton#danger:hover { background: $dangerBg; }
QPushButton#quiet { color: $secondary; background: transparent; }
QPushButton#quiet:hover { background: $button; }
QListWidget { background: transparent; border: none; outline: none; padding: 0; }
QPlainTextEdit { background: transparent; border: none; padding: 0; color: $secondary; selection-background-color: $selectedBorder; }
QPlainTextEdit#input, QLineEdit, QComboBox, QTimeEdit { background: $field; border: 1px solid $border; border-radius: 9px; padding: 9px 10px; selection-background-color: $selectedBorder; }
QPlainTextEdit#input:focus, QLineEdit:focus, QComboBox:focus, QTimeEdit:focus { border: 1px solid $accent; }
QComboBox#appearance { padding: 6px 10px; min-width: 78px; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: $panel; color: $text; selection-background-color: $selected; selection-color: $selectedText; padding: 4px; border: 1px solid $border; }
QLineEdit:disabled, QTimeEdit:disabled { background: $button; color: $disabled; }
QCheckBox { spacing: 9px; padding: 5px 0; }
QSplitter::handle { background: transparent; }
QScrollBar:vertical { background: transparent; width: 9px; margin: 2px; }
QScrollBar::handle:vertical { background: $scroll; border-radius: 3px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QToolTip { background: $panel; color: $text; padding: 7px; border: 1px solid $border; }
QTabWidget::pane { border: 1px solid $border; border-radius: 12px; background: $panel; }
QWidget#settingsPage { background: $panel; }
QTabBar::tab { padding: 10px 18px; margin-right: 6px; margin-bottom: 8px; background: $button; border-radius: 8px; color: $secondary; }
QTabBar::tab:selected { background: $accent; color: $primaryText; }
QTabBar::tab:focus { border: 1px solid $muted; }
'''


def stylesheet(dark=False):
    colors = (DARK if dark else LIGHT) | {'primaryText': '#191919' if dark else '#ffffff'}
    result = TEMPLATE
    # Replace longer tokens first so accentHover is not consumed by accent.
    for key in sorted(colors, key=len, reverse=True):
        result = result.replace('$' + key, colors[key])
    return result


class Appearance(QObject):
    changed = pyqtSignal()

    def __init__(self, path: Path, parent=None):
        super().__init__(parent)
        self.settings = QSettings(str(path), QSettings.Format.IniFormat)
        self.read_preferences()
        self.dark = False
        self.apply()
        QApplication.styleHints().colorSchemeChanged.connect(self.system_changed)

    @property
    def colors(self):
        return DARK if self.dark else LIGHT

    def system_changed(self, scheme):
        if self.mode == 'System':
            self.apply(scheme)

    def read_preferences(self):
        self.mode = self.settings.value('appearance', 'System')
        self.sort_order = self.settings.value('sort_order', 'Newest first')
        self.default_filter = self.settings.value('default_filter', 'All statuses')
        self.show_preview = str(self.settings.value('show_preview', 'true')).lower() not in ('false', '0')
        for name, options, default in (
            ('mode', MODES, 'System'), ('sort_order', SORT_ORDERS, 'Newest first'),
            ('default_filter', DEFAULT_FILTERS, 'All statuses'),
        ):
            if getattr(self, name) not in options:
                setattr(self, name, default)

    def snapshot(self):
        return self.mode, self.sort_order, self.default_filter, self.show_preview

    def set_mode(self, mode):
        self.update(mode, self.sort_order, self.default_filter, self.show_preview)

    def update(self, mode, sort_order, default_filter, show_preview):
        if mode not in MODES or sort_order not in SORT_ORDERS or default_filter not in DEFAULT_FILTERS:
            raise ValueError('Choose one of the available settings.')
        for key, value in (('appearance', mode), ('sort_order', sort_order),
                           ('default_filter', default_filter), ('show_preview', bool(show_preview))):
            self.settings.setValue(key, value)
        self.settings.sync()
        if self.settings.status() != QSettings.Status.NoError:
            raise OSError('Your settings could not be saved.')
        self.read_preferences()
        self.apply()

    def reload(self):
        self.settings.sync()
        if self.settings.status() != QSettings.Status.NoError:
            return
        previous = self.snapshot()
        self.read_preferences()
        if self.snapshot() != previous:
            self.apply()

    def apply(self, scheme=None):
        scheme = QApplication.styleHints().colorScheme() if scheme is None else scheme
        self.dark = self.mode == 'Dark' or (self.mode == 'System' and scheme == Qt.ColorScheme.Dark)
        c = self.colors
        palette = QPalette()
        for role, color in {
            QPalette.ColorRole.Window: c['bg'], QPalette.ColorRole.WindowText: c['text'],
            QPalette.ColorRole.Base: c['field'], QPalette.ColorRole.AlternateBase: c['panel'],
            QPalette.ColorRole.Text: c['text'], QPalette.ColorRole.Button: c['button'],
            QPalette.ColorRole.ButtonText: c['text'], QPalette.ColorRole.Highlight: c['selectedBorder'],
            QPalette.ColorRole.HighlightedText: c['text'], QPalette.ColorRole.ToolTipBase: c['panel'],
            QPalette.ColorRole.ToolTipText: c['text'], QPalette.ColorRole.PlaceholderText: c['muted'],
            QPalette.ColorRole.Link: c['accent'],
        }.items():
            palette.setColor(role, QColor(color))
        for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
            palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(c['disabled']))
        QApplication.instance().setPalette(palette)
        QApplication.instance().setStyleSheet(stylesheet(self.dark))
        self.changed.emit()

