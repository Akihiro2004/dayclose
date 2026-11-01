"""Dayclose: a local reminder manager and explicit shutdown review."""
import argparse
from datetime import datetime
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

from PyQt6.QtCore import Qt, QTime, QTimer, QSize, QRectF, QUrl
from PyQt6.QtGui import QFont, QIcon, QPainter, QColor, QPixmap, QKeySequence, QShortcut, QDesktopServices
from PyQt6.QtWidgets import (
    QApplication, QWidget, QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QListWidget, QListWidgetItem, QPlainTextEdit,
    QLineEdit, QComboBox, QCheckBox, QTimeEdit, QMessageBox, QSplitter,
    QSizePolicy, QStyledItemDelegate, QStyle, QAbstractSpinBox, QTabWidget, QFileDialog, QProgressBar,
)
from core import Reminder, Store, STATUSES
from version import APP_VERSION
from updater import UpdateController, UpdateError, RELEASES_URL, launch_helper

from appearance import Appearance, MODES, SORT_ORDERS, DEFAULT_FILTERS, stylesheet

STYLE = stylesheet()


def label(text, name=None, wrap=False):
    widget = QLabel(text)
    if name:
        widget.setObjectName(name)
    widget.setWordWrap(wrap)
    return widget


def button(text, callback, name=None):
    widget = QPushButton(text)
    if name:
        widget.setObjectName(name)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    widget.clicked.connect(callback)
    return widget


def app_icon():
    bundled = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent)) / 'assets' / 'dayclose.ico'
    if bundled.exists():
        return QIcon(str(bundled))
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor('#303030'))
    painter.drawRoundedRect(0, 0, 64, 64, 15, 15)
    painter.setPen(QColor('white'))
    font = QFont('Segoe UI', 36)
    font.setWeight(QFont.Weight.Light)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, '✓')
    painter.end()
    return QIcon(pixmap)


def request_shutdown(runner=subprocess.run):
    # /t > 0 implies /f on Windows; never force-close unsaved work.
    executable = str(Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'shutdown.exe')
    result = runner([executable, '/s', '/t', '0'], capture_output=True, text=True,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), timeout=15)
    if result.returncode:
        raise OSError(result.stderr.strip() or result.stdout.strip() or f'Windows returned error {result.returncode}.')


class ReminderDelegate(QStyledItemDelegate):
    """Elided visual rows; the full reminder remains available to accessibility."""
    def __init__(self, appearance, parent):
        super().__init__(parent)
        self.appearance = appearance

    def paint(self, painter, option, index):
        item = index.data(Qt.ItemDataRole.UserRole + 1)
        if item is None:
            return
        c = self.appearance.colors
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        rect = QRectF(option.rect.adjusted(2, 4, -2, -4))
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor(c['selectedBorder']) if selected else Qt.PenStyle.NoPen)
        painter.setBrush(QColor(c['selected'] if selected else c['field'] if hovered else c['panel']))
        painter.drawRoundedRect(rect, 12, 12)
        status = {'Active': 'green', 'Paused': 'amber', 'Completed': 'neutral'}[item.status]
        x, y = int(rect.x()), int(rect.y())
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(c[status + 'Bg']))
        painter.drawRoundedRect(QRectF(x + 14, y + 16, 30, 30), 10, 10)
        painter.setPen(QColor(c[status]))
        mark = QFont('Segoe UI', 11)
        mark.setWeight(QFont.Weight.DemiBold)
        painter.setFont(mark)
        painter.drawText(QRectF(x + 14, y + 16, 30, 30), Qt.AlignmentFlag.AlignCenter,
                         '✓' if item.status == 'Completed' else 'Ⅱ' if item.status == 'Paused' else '•')
        text_x = x + 56
        width = int(rect.width()) - 70
        font = QFont('Segoe UI', 10)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(QColor(c['selectedText'] if selected else c['text']))
        title = painter.fontMetrics().elidedText(item.title, Qt.TextElideMode.ElideRight, width)
        painter.drawText(text_x, y + 29, title)
        font.setPointSize(9)
        font.setWeight(QFont.Weight.Normal)
        painter.setFont(font)
        painter.setPen(QColor(c['secondary']))
        preview = ' '.join(item.notes.split()) or 'No notes added'
        if self.appearance.show_preview:
            painter.drawText(text_x, y + 50, painter.fontMetrics().elidedText(preview, Qt.TextElideMode.ElideRight, width))
        painter.setPen(QColor(c[status]))
        caption = f'{item.status}  ·  {item.schedule}'
        painter.drawText(text_x, y + (73 if self.appearance.show_preview else 51), painter.fontMetrics().elidedText(caption, Qt.TextElideMode.ElideRight, width))
        painter.restore()


class App(QWidget):
    def __init__(self, store, review=False, dry_run=False, parent=None, appearance=None, updater=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.store, self.review, self.dry_run = store, review, dry_run
        self.appearance = appearance or Appearance(store.path.parent / 'appearance.ini', self)
        self.updater = updater
        self.items = {}
        self.children_windows = []
        self.sending = False
        self.setObjectName('window')
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle('Dayclose' + (' · Shutdown review' if review else ' · Reminders'))
        self.setWindowIcon(app_icon())
        self.resize(1120, 760)
        self.setMinimumSize(800, 650)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 26, 32, 24)
        layout.setSpacing(0)
        top = QHBoxLayout()
        top.addWidget(label('Dayclose', 'brand'))
        top.addStretch()
        self.update_button = button('Update available', self.open_updates, 'primary')
        self.update_button.hide()
        top.addWidget(self.update_button)
        self.clock = label('', 'muted')
        top.addWidget(self.clock)
        top.addSpacing(18)
        top.addWidget(button('Settings', self.open_settings))
        layout.addLayout(top)
        layout.addSpacing(18)
        layout.addWidget(label('Before you call it a day.' if review else 'A clearer end to your day.', 'heading'))
        layout.addSpacing(6)
        layout.addWidget(label('Review what needs your attention before you power off.' if review else 'Keep the little things here. Leave with a lighter mind.', 'subtitle', True))
        layout.addSpacing(24)
        toolbar = QHBoxLayout()
        self.summary = label('', 'summary')
        toolbar.addWidget(self.summary)
        toolbar.addStretch()
        toolbar.addWidget(button('Refresh', self.refresh, 'quiet'))
        if review:
            toolbar.addWidget(button('Manage reminders', self.manage))
        else:
            toolbar.addWidget(button('Preview', self.preview, 'quiet'))
            toolbar.addWidget(button('+  New reminder', lambda: self.edit(), 'primary'))
        layout.addLayout(toolbar)
        layout.addSpacing(12)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(18)
        self.splitter.setChildrenCollapsible(False)
        left = QFrame()
        left.setObjectName('panel')
        left.setMinimumWidth(300)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(16, 18, 16, 12)
        left_layout.setSpacing(10)
        left_layout.addWidget(label('YOUR SHUTDOWN CHECKLIST' if review else 'REMINDER LIBRARY', 'section'))
        self.search = QLineEdit()
        self.search.setPlaceholderText('Search reminders and notes')
        self.search.setAccessibleName('Search reminders')
        self.search.textChanged.connect(lambda _: self.refresh())
        self.status_filter = QComboBox()
        self.status_filter.setAccessibleName('Filter reminders by status')
        self.status_filter.addItems(DEFAULT_FILTERS)
        self.status_filter.setCurrentText(self.appearance.default_filter)
        self.status_filter.currentTextChanged.connect(lambda _: self.refresh())
        if not review:
            filters = QHBoxLayout()
            filters.addWidget(self.search, 1)
            filters.addWidget(self.status_filter)
            left_layout.addLayout(filters)
        self.list_widget = QListWidget()
        self.list_widget.setAccessibleName('Reminders')
        self.list_widget.setSpacing(1)
        self.list_widget.setMouseTracking(True)
        self.list_widget.setItemDelegate(ReminderDelegate(self.appearance, self.list_widget))
        self.list_widget.currentItemChanged.connect(self.selection)
        self.list_widget.itemDoubleClicked.connect(lambda _: self.edit_selected())
        left_layout.addWidget(self.list_widget, 1)
        self.empty = label('All clear for now.\nNo active reminders in this time window.' if review else 'A clear head starts here.\nAdd your first reminder to get started.', 'subtitle', True)
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(self.empty, 1)
        self.splitter.addWidget(left)
        right = QFrame()
        right.setObjectName('panel')
        right.setMinimumWidth(280)
        details = QVBoxLayout(right)
        details.setContentsMargins(24, 22, 24, 18)
        details.setSpacing(12)
        badge_row = QHBoxLayout()
        self.badge = label('DETAILS', 'badge')
        badge_row.addWidget(self.badge)
        badge_row.addStretch()
        details.addLayout(badge_row)
        self.detail_title = label('The details make it easier.', 'detailTitle', True)
        self.detail_title.setMaximumHeight(84)
        self.detail_title.setTextFormat(Qt.TextFormat.PlainText)
        details.addWidget(self.detail_title)
        self.schedule_label = label('', 'muted', True)
        details.addWidget(self.schedule_label)
        line = QFrame()
        line.setObjectName('line')
        line.setFixedHeight(1)
        details.addWidget(line)
        details.addWidget(label('NOTES', 'section'))
        self.notes = QPlainTextEdit()
        self.notes.setReadOnly(True)
        self.notes.setAccessibleName('Reminder notes')
        details.addWidget(self.notes, 1)
        self.edit_button = button('Edit reminder', self.edit_selected)
        self.complete_button = button('Mark completed', self.complete)
        detail_actions = QHBoxLayout()
        detail_actions.addWidget(self.edit_button)
        detail_actions.addWidget(self.complete_button)
        self.edit_button.setText('Edit')
        details.addLayout(detail_actions)
        self.delete_button = button('Delete reminder', self.delete, 'danger')
        if not review:
            details.addWidget(self.delete_button)
        self.splitter.addWidget(right)
        self.splitter.setSizes([510, 400])
        layout.addWidget(self.splitter, 1)
        layout.addSpacing(18)
        footer = QHBoxLayout()
        footer.setSpacing(12)
        footnote = label('Daily windows · Local time\nCompleted reminders stay hidden until reactivated.', 'muted', True)
        footnote.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        footer.addWidget(footnote, 1)
        if review:
            footer.addWidget(button('Stay on', self.close))
            self.shutdown_button = button('Test shutdown…' if dry_run else 'Shut down…', self.shutdown, 'primary')
            footer.addWidget(self.shutdown_button)
        else:
            footer.addWidget(button('Review and shut down', self.open_review, 'primary'))
        layout.addLayout(footer)
        QShortcut(QKeySequence('Ctrl+N'), self, activated=lambda: self.edit())
        QShortcut(QKeySequence('F5'), self, activated=self.refresh)
        QShortcut(QKeySequence('Ctrl+,'), self, activated=self.open_settings)
        QShortcut(QKeySequence('Escape'), self, activated=self.close)
        self.timer = QTimer(self)
        self.timer.setInterval(15000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.appearance.changed.connect(self.appearance_changed)
        self.refresh()
        self.appearance_changed()
        if self.updater:
            self.updater.changed.connect(self.update_notice)
            self.update_notice()

    def update_notice(self):
        self.update_button.setVisible(self.updater.release is not None)
        if self.updater.release:
            self.update_button.setText(f'Update {self.updater.release.version}')

    def open_updates(self):
        dialog = SettingsPanel(self.store, self.appearance, self, self.updater)
        dialog.tabs.setCurrentIndex(3)
        dialog.exec()
        dialog.deleteLater()

    def open_settings(self):
        dialog = SettingsPanel(self.store, self.appearance, self, self.updater)
        dialog.exec()
        dialog.deleteLater()

    def appearance_changed(self):
        self.list_widget.viewport().update()
        self.refresh()
        self.selection()
        # Match the native Windows title bar to the chosen appearance.
        if os.name == 'nt':
            import ctypes
            dark = ctypes.c_int(self.appearance.dark)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(int(self.winId())), 20,
                                                       ctypes.byref(dark), ctypes.sizeof(dark))

    def error(self, error):
        QMessageBox.critical(self, 'Could not complete that action', str(error))

    def selected(self):
        current = self.list_widget.currentItem()
        return self.items.get(current.data(Qt.ItemDataRole.UserRole)) if current else None

    def selection(self, *_):
        item = self.selected()
        self.edit_button.setEnabled(item is not None)
        self.delete_button.setEnabled(item is not None)
        self.complete_button.setEnabled(item is not None)
        self.complete_button.setText('Mark completed' if item is None or item.status == 'Active' else 'Reactivate')
        self.detail_title.setText(item.title if item else 'You’re all set.' if self.review else 'The details make it easier.')
        self.detail_title.setToolTip(item.title if item else '')
        self.badge.setText(item.status.upper() if item else 'ALL CLEAR' if self.review else 'DETAILS')
        c = self.appearance.colors
        status = {'Active': 'green', 'Paused': 'amber', 'Completed': 'neutral'}.get(item.status if item else '', 'neutral')
        self.badge.setStyleSheet(f"color:{c[status]};background:{c[status + 'Bg']};")
        self.schedule_label.setText(f'{item.schedule} · Every day' if item else 'Nothing needs your attention right now.' if self.review else 'Select a reminder to see its notes and schedule.')
        self.notes.setPlainText(item.notes or 'No notes added.' if item else '')

    def refresh(self):
        self.appearance.reload()
        try:
            items = self.store.list()
        except (sqlite3.Error, ValueError, OSError) as error:
            if self.review:
                self.shutdown_button.setEnabled(False)
            self.error(error)
            return False
        now = datetime.now()
        due = [item for item in items if item.due(now)]
        visible = due if self.review else items
        if self.appearance.sort_order == 'Title A–Z':
            visible = sorted(visible, key=lambda item: (item.title.casefold(), item.id))
        elif self.appearance.sort_order == 'Due now first':
            visible = sorted(visible, key=lambda item: (not item.due(now), -item.id))
        if not self.review:
            query = self.search.text().strip().casefold()
            status = self.status_filter.currentText()
            visible = [item for item in visible if
                       (status == 'All statuses' or item.status == status) and
                       (not query or query in (item.title + '\n' + item.notes).casefold())]
            self.empty.setText('No matching reminders.\nTry another search or status.' if items else
                               'A clear head starts here.\nAdd your first reminder to get started.')
        selected = self.selected()
        # Keep focus and the notes scroll position when the data has not changed.
        changed = (list(self.items.values()) != visible or
                   getattr(self, 'last_show_preview', None) != self.appearance.show_preview)
        self.last_show_preview = self.appearance.show_preview
        self.items = {item.id: item for item in visible}
        if changed:
            self.list_widget.blockSignals(True)
            self.list_widget.clear()
            selected_row = 0
            for index, item in enumerate(visible):
                row = QListWidgetItem(f'{item.title}\n{item.schedule}   ·   {item.status}')
                row.setData(Qt.ItemDataRole.UserRole, item.id)
                row.setData(Qt.ItemDataRole.UserRole + 1, item)
                row.setToolTip(item.title)
                row.setSizeHint(QSize(0, 98 if self.appearance.show_preview else 76))
                self.list_widget.addItem(row)
                if selected and selected.id == item.id:
                    selected_row = index
            self.list_widget.setCurrentRow(selected_row)
            self.list_widget.blockSignals(False)
        self.list_widget.setVisible(bool(visible))
        self.empty.setVisible(not visible)
        if changed or not visible:
            self.selection()
        self.summary.setText(f'{len(due)} reminder' + ('' if len(due) == 1 else 's') + ' to review' if self.review else f'{len(items)} saved   ·   {len(due)} due now')
        self.clock.setText(now.strftime('%a, %d %b  ·  %H:%M'))
        if self.review:
            self.shutdown_button.setEnabled(True)
        # The initial empty state must also disable the action buttons.
        if not visible:
            self.selection()
        return True

    def edit_selected(self):
        if self.selected():
            self.edit(self.selected())

    def edit(self, item=None):
        editor = Editor(self.store, item, self)
        if editor.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def complete(self):
        item = self.selected()
        if item:
            try:
                # Reload so a stale detail pane cannot overwrite another window's edits.
                latest = next((r for r in self.store.list() if r.id == item.id), None)
                if latest is None:
                    raise ValueError('This reminder was deleted in another window. Refresh and try again.')
                latest.status = 'Completed' if latest.status == 'Active' else 'Active'
                self.store.save(latest)
                self.refresh()
            except (sqlite3.Error, ValueError, OSError) as error:
                self.error(error)

    def delete(self):
        item = self.selected()
        if item and QMessageBox.question(self, 'Delete reminder?', f'Delete “{item.title}”?\nThis cannot be undone.', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            try:
                self.store.delete(item.id)
                self.refresh()
            except (sqlite3.Error, OSError) as error:
                self.error(error)

    def preview(self):
        return self.new_window(True, True)

    def open_review(self):
        return self.new_window(True, self.dry_run)

    def manage(self):
        return self.new_window(False, self.dry_run)

    def new_window(self, review, dry_run):
        window = App(self.store, review, dry_run, self, self.appearance, self.updater)
        self.children_windows.append(window)
        window.destroyed.connect(lambda: self.children_windows.remove(window) if window in self.children_windows else None)
        window.show()
        return window

    def shutdown(self):
        if self.sending or not self.refresh():
            return
        self.sending = True
        try:
            text = 'This is a preview. No shutdown command will run.' if self.dry_run else 'Save your work first.\nShut down this computer now?'
            response = QMessageBox.question(self, 'Test shutdown' if self.dry_run else 'Ready to shut down?', text, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if response != QMessageBox.StandardButton.Yes:
                return
            if self.dry_run:
                QMessageBox.information(self, 'Preview complete', 'Your reminders are ready. Your computer will stay on.')
            else:
                request_shutdown()
                QApplication.instance().quit()
        except (OSError, subprocess.SubprocessError) as error:
            self.error(error)
        finally:
            self.sending = False

    def closeEvent(self, event):
        self.timer.stop()
        super().closeEvent(event)


class UpdatesPanel(QWidget):
    def __init__(self, updater, parent=None):
        super().__init__(parent)
        self.updater = updater
        self.setObjectName('settingsPage')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(10)
        layout.addWidget(label('Keep Dayclose up to date.', 'detailTitle'))
        layout.addWidget(label(f'Installed version {APP_VERSION}', 'muted'))
        self.status = label('', 'subtitle', True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setAccessibleName('Update download progress')
        layout.addWidget(self.progress)
        self.notes = QPlainTextEdit()
        self.notes.setReadOnly(True)
        self.notes.setAccessibleName('Release notes')
        self.notes.setPlaceholderText('Release notes will appear here when an update is available.')
        layout.addWidget(self.notes, 1)
        actions = QHBoxLayout()
        self.check_button = button('Check for updates', updater.check)
        self.install_button = button('Download update', self.act, 'primary')
        self.cancel_button = button('Cancel download', updater.cancel)
        actions.addWidget(self.check_button)
        actions.addWidget(self.install_button)
        actions.addWidget(self.cancel_button)
        layout.addLayout(actions)
        layout.addWidget(button('View releases on GitHub', lambda: QDesktopServices.openUrl(QUrl(RELEASES_URL)), 'quiet'))
        updater.changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        update = self.updater
        self.status.setText(update.message)
        self.progress.setVisible(update.state == 'downloading')
        self.progress.setValue(update.percent)
        self.check_button.setEnabled(not update.busy)
        self.install_button.setVisible(update.release is not None)
        self.install_button.setEnabled(not update.busy)
        self.install_button.setText('Install and restart' if update.installer else 'Download update')
        self.cancel_button.setVisible(update.state == 'downloading')
        notes = update.release.notes if update.release else ''
        if self.notes.toPlainText() != notes:
            self.notes.setPlainText(notes)

    def act(self):
        if self.updater.installer:
            self.updater.install_ready.emit()
        else:
            self.updater.download()


class SettingsPanel(QDialog):
    def __init__(self, store, appearance, parent=None, updater=None):
        super().__init__(parent)
        self.store, self.appearance = store, appearance
        self.setWindowTitle('Dayclose · Settings')
        self.setWindowIcon(app_icon())
        self.resize(660, 570)
        self.setMinimumSize(580, 530)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        layout.addWidget(label('Settings', 'heading'))
        layout.addWidget(label('A little more your way.', 'subtitle'))
        tabs = self.tabs = QTabWidget()
        tabs.setAccessibleName('Settings categories')
        layout.addWidget(tabs, 1)
        appearance_page, library_page, data_page = QWidget(), QWidget(), QWidget()
        for page in (appearance_page, library_page, data_page):
            page.setObjectName('settingsPage')
        tabs.addTab(appearance_page, 'Appearance')
        tabs.addTab(library_page, 'Library')
        tabs.addTab(data_page, 'Data')
        if updater is None:
            updater = UpdateController(store.path.parent, self)
        self.updates_panel = UpdatesPanel(updater, self)
        tabs.addTab(self.updates_panel, 'Updates')
        appearance_layout = QVBoxLayout(appearance_page)
        appearance_layout.setContentsMargins(22, 24, 22, 22)
        appearance_layout.setSpacing(12)
        appearance_layout.addWidget(label('Color scheme', 'detailTitle'))
        appearance_layout.addWidget(label('Neutral surfaces. Black and white essentials.', 'subtitle', True))
        self.mode_combo = QComboBox()
        self.mode_combo.setAccessibleName('Color scheme')
        self.mode_combo.addItems(MODES)
        appearance_layout.addWidget(self.mode_combo)
        appearance_layout.addWidget(label('System follows Windows. Light uses white surfaces; Dark uses dark gray.\nYour choice applies to all Dayclose windows.', 'muted', True))
        appearance_layout.addStretch()
        library_layout = QVBoxLayout(library_page)
        library_layout.setContentsMargins(22, 24, 22, 22)
        library_layout.setSpacing(12)
        library_layout.addWidget(label('Sort reminders'))
        self.sort_combo = QComboBox()
        self.sort_combo.setAccessibleName('Sort reminders')
        self.sort_combo.addItems(SORT_ORDERS)
        library_layout.addWidget(self.sort_combo)
        library_layout.addWidget(label('Default status filter'))
        self.filter_combo = QComboBox()
        self.filter_combo.setAccessibleName('Default status filter')
        self.filter_combo.addItems(DEFAULT_FILTERS)
        library_layout.addWidget(self.filter_combo)
        library_layout.addWidget(label('Used when opening a new manager window. Shutdown review always shows all due reminders.', 'muted', True))
        self.preview_check = QCheckBox('Show notes previews in the reminder list')
        library_layout.addWidget(self.preview_check)
        library_layout.addStretch()
        data_layout = QVBoxLayout(data_page)
        data_layout.setContentsMargins(22, 24, 22, 22)
        data_layout.setSpacing(14)
        data_layout.addWidget(label('Your reminders stay on this computer.', 'detailTitle', True))
        data_layout.addWidget(label('Make a reminder database backup, or open the folder that holds your data and settings.', 'subtitle', True))
        path_label = label(str(store.path.parent.resolve()), 'muted', True)
        path_label.setTextFormat(Qt.TextFormat.PlainText)
        path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        data_layout.addWidget(path_label)
        data_layout.addWidget(button('Create reminder backup…', self.backup))
        data_layout.addWidget(button('Open data folder', self.open_folder))
        data_layout.addWidget(label('A backup contains reminders, statuses, schedules, and notes. Appearance and library preferences remain in the settings file.', 'muted', True))
        data_layout.addStretch()
        footer = QHBoxLayout()
        self.saved_label = label(f'Dayclose {APP_VERSION} · Changes save automatically', 'muted')
        footer.addWidget(self.saved_label)
        footer.addStretch()
        footer.addWidget(button('Done', self.accept, 'primary'))
        layout.addLayout(footer)
        self.sync_controls()
        self.mode_combo.currentTextChanged.connect(self.save)
        self.sort_combo.currentTextChanged.connect(self.save)
        self.filter_combo.currentTextChanged.connect(self.save)
        self.preview_check.toggled.connect(self.save)
        self.appearance.changed.connect(self.sync_controls)

    def sync_controls(self):
        for control, value in ((self.mode_combo, self.appearance.mode),
                               (self.sort_combo, self.appearance.sort_order),
                               (self.filter_combo, self.appearance.default_filter),
                               (self.preview_check, self.appearance.show_preview)):
            control.blockSignals(True)
            if isinstance(control, QCheckBox):
                control.setChecked(value)
            else:
                control.setCurrentText(value)
            control.blockSignals(False)

    def save(self, *_):
        try:
            self.appearance.update(self.mode_combo.currentText(), self.sort_combo.currentText(),
                                   self.filter_combo.currentText(), self.preview_check.isChecked())
            self.saved_label.setText(f'Dayclose {APP_VERSION} · Changes saved')
        except (ValueError, OSError) as error:
            self.sync_controls()
            QMessageBox.warning(self, 'Could not save settings', str(error))

    def backup(self):
        filename, _ = QFileDialog.getSaveFileName(self, 'Create reminder backup',
                         str(Path.home() / f'Dayclose-backup-{datetime.now():%Y-%m-%d-%H%M%S}.db'),
                         'SQLite database (*.db)')
        if not filename:
            return
        try:
            self.store.backup(Path(filename))
            QMessageBox.information(self, 'Backup created', f'Your reminders were backed up to:\n{filename}')
        except (ValueError, OSError, sqlite3.Error) as error:
            QMessageBox.warning(self, 'Could not create backup', str(error))

    def open_folder(self):
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.store.path.parent.resolve()))):
            QMessageBox.warning(self, 'Could not open folder', 'Open the data folder using the path shown above.')


class Editor(QDialog):
    def __init__(self, store, item=None, parent=None):
        super().__init__(parent)
        self.store, self.item = store, item
        self.setWindowTitle('Edit reminder' if item else 'New reminder')
        self.setWindowIcon(app_icon())
        self.setMinimumSize(500, 590)
        self.resize(560, 680)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(10)
        layout.addWidget(label('A NOTE TO FUTURE YOU', 'eyebrow'))
        layout.addWidget(label('Edit your reminder.' if item else 'Make a little room.', 'detailTitle'))
        layout.addSpacing(6)
        item = item or Reminder('')
        title_label = label('Title')
        layout.addWidget(title_label)
        self.title = QLineEdit(item.title)
        self.title.setPlaceholderText('What would you like to remember?')
        self.title.setMaxLength(200)
        self.title.setAccessibleName('Reminder title')
        title_label.setBuddy(self.title)
        layout.addWidget(self.title)
        layout.addWidget(label('Status'))
        self.status = QComboBox()
        self.status.setAccessibleName('Reminder status')
        self.status.addItems(STATUSES)
        self.status.setCurrentText(item.status)
        layout.addWidget(self.status)
        self.all_day = QCheckBox('All day')
        self.all_day.setChecked(bool(item.all_day))
        self.all_day.toggled.connect(self.toggle_time)
        layout.addWidget(self.all_day)
        times = QHBoxLayout()
        times.addWidget(label('From'))
        self.start = QTimeEdit(QTime.fromString(item.start, 'HH:mm'))
        self.start.setDisplayFormat('HH:mm')
        self.start.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.start.setAccessibleName('Start time')
        times.addWidget(self.start, 1)
        times.addSpacing(12)
        times.addWidget(label('Until'))
        self.end = QTimeEdit(QTime.fromString(item.end, 'HH:mm'))
        self.end.setDisplayFormat('HH:mm')
        self.end.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.end.setAccessibleName('End time')
        times.addWidget(self.end, 1)
        layout.addLayout(times)
        layout.addWidget(label('Repeats daily while Active. Uses your computer’s local time.\n22:00–02:00 crosses midnight. The end time is excluded.', 'muted', True))
        layout.addWidget(label('Notes'))
        self.notes = QPlainTextEdit(item.notes)
        self.notes.setObjectName('input')
        self.notes.setAccessibleName('Reminder notes')
        self.notes.setPlaceholderText('A few details to help future you. Optional.')
        layout.addWidget(self.notes, 1)
        layout.addWidget(label('Paused and Completed reminders stay out of shutdown review.', 'muted', True))
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(button('Cancel', self.reject))
        self.save_button = button('Save reminder', self.save, 'primary')
        self.save_button.setDefault(True)
        actions.addWidget(self.save_button)
        layout.addLayout(actions)
        QShortcut(QKeySequence('Ctrl+Return'), self, activated=self.save)
        self.toggle_time()
        self.title.setFocus()

    def toggle_time(self):
        self.start.setEnabled(not self.all_day.isChecked())
        self.end.setEnabled(not self.all_day.isChecked())

    def save(self):
        item = Reminder(title=self.title.text(), notes=self.notes.toPlainText(), status=self.status.currentText(),
                        start=self.start.time().toString('HH:mm'), end=self.end.time().toString('HH:mm'),
                        all_day=self.all_day.isChecked(), id=self.item.id if self.item else None)
        try:
            self.store.save(item)
        except (ValueError, OSError, sqlite3.Error) as error:
            QMessageBox.warning(self, 'Could not save reminder', str(error))
            return
        self.accept()


def main():
    parser = argparse.ArgumentParser(description='Dayclose reminder manager')
    parser.add_argument('--shutdown', action='store_true', help='Open shutdown review')
    parser.add_argument('--dry-run', action='store_true', help='Never execute a shutdown command')
    parser.add_argument('--data-dir', type=Path, help='Use a separate local data folder')
    args = parser.parse_args()
    if os.name == 'nt':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('Dayclose.Desktop')
    application = QApplication(sys.argv[:1])
    application.setApplicationName('Dayclose')
    application.setStyle('Fusion')
    application.setStyleSheet(STYLE)
    application.setWindowIcon(app_icon())
    folder = args.data_dir or Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'BeforeYouGo'
    store = None
    try:
        store = Store(folder / 'reminders.db')
        updater = UpdateController(folder, application)
        window = App(store, args.shutdown, args.dry_run, updater=updater)
        def install_update():
            if not updater.installer or not updater.release:
                return
            if any(isinstance(widget, Editor) and widget.isVisible() for widget in application.topLevelWidgets()):
                QMessageBox.information(window, 'Save your reminder first', 'Save or close all reminder editors before installing an update.')
                return
            if QMessageBox.question(window, 'Install update and restart?',
                    f'Install Dayclose {updater.release.version}? Dayclose will close and reopen after installation. Your reminders and settings will be kept.',
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                return
            try:
                if not getattr(sys, 'frozen', False):
                    raise UpdateError('Use the packaged Dayclose app to install updates. Source mode can check and download updates.')
                updater.folder.mkdir(parents=True, exist_ok=True)
                store.backup(updater.folder / f'pre-update-{datetime.now():%Y%m%d-%H%M%S}.db')
                window.appearance.settings.sync()
                launch_helper(updater.installer, updater.release, updater.folder, args.dry_run)
            except (OSError, ValueError, sqlite3.Error, UpdateError) as error:
                window.error(error)
                return
            application.quit()
        updater.install_ready.connect(install_update)
        application.aboutToQuit.connect(updater.stop)
        if not args.shutdown:
            QTimer.singleShot(1500, updater.check)
        window.show()
        application.exec()
    except (OSError, ValueError, sqlite3.Error) as error:
        QMessageBox.critical(None, 'Dayclose could not start', f'Your reminders could not be opened.\n{error}\n\nData location: {folder}')
    finally:
        if store:
            store.close()


if __name__ == '__main__':
    main()
