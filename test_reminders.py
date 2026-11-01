from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from unittest.mock import Mock, patch
from PyQt6.QtCore import QTime, Qt
from PyQt6.QtWidgets import QApplication, QMessageBox, QDialog
from core import Reminder, Store
from app import App, Editor, request_shutdown, STYLE, SettingsPanel
from appearance import Appearance, LIGHT, DARK, stylesheet


class RulesTests(TestCase):
    def due(self, item, time):
        return item.due(datetime.fromisoformat(f'2026-11-01T{time}:00'))

    def test_day_window_boundaries(self):
        item = Reminder('Test', all_day=False, start='09:00', end='17:00')
        for time, expected in [('08:59', False), ('09:00', True), ('16:59', True), ('17:00', False)]:
            self.assertEqual(self.due(item, time), expected)

    def test_overnight_boundaries(self):
        item = Reminder('Test', all_day=False, start='22:00', end='02:00')
        for time, expected in [('21:59', False), ('22:00', True), ('23:59', True), ('00:00', True), ('01:59', True), ('02:00', False), ('12:00', False)]:
            self.assertEqual(self.due(item, time), expected)

    def test_all_day_and_statuses(self):
        item = Reminder('Test')
        for time in ('00:00', '12:00', '23:59'):
            self.assertTrue(self.due(item, time))
        for status in ('Paused', 'Completed'):
            item.status = status
            self.assertFalse(self.due(item, '12:00'))

    def test_validation(self):
        for kwargs in ({'title': ' '}, {'title': 'x' * 201}, {'start': '24:00'}, {'end': '10:60'}, {'start': '9:00'}, {'start': '０９:００'}, {'status': 'Unknown'}, {'all_day': False, 'start': '09:00', 'end': '09:00'}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                Reminder(**({'title': 'Test'} | kwargs)).validate()

    def test_shutdown_command_is_non_forcing(self):
        runner = Mock(return_value=Mock(returncode=0))
        request_shutdown(runner)
        self.assertEqual(runner.call_args.args[0][1:], ['/s', '/t', '0'])
        runner.return_value = Mock(returncode=1, stderr='Access denied', stdout='')
        with self.assertRaisesRegex(OSError, 'Access denied'):
            request_shutdown(runner)


class StorageTests(TestCase):
    def test_crud_reopen_and_concurrent_windows(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'reminders.db'
            first = Store(path)
            second = Store(path)
            item = Reminder('Back up project', notes='Café 日本語\nSecond line')
            first.save(item)
            self.assertEqual(second.list()[0].notes, item.notes)
            item.status = 'Paused'
            second.save(item)
            self.assertEqual(first.list()[0].status, 'Paused')
            first.close()
            first = Store(path)
            self.assertEqual(first.list()[0].title, item.title)
            first.delete(item.id)
            with self.assertRaises(ValueError):
                second.save(item)
            self.assertEqual(first.list(), [])
            first.close()
            second.close()

    def test_failed_validation_does_not_replace_saved_data(self):
        with TemporaryDirectory() as folder:
            store = Store(Path(folder) / 'test.db')
            item = Reminder('Saved')
            store.save(item)
            item.title = ''
            with self.assertRaises(ValueError):
                store.save(item)
            self.assertEqual(store.list()[0].title, 'Saved')
            store.close()


class GuiTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])
        cls.qt.setStyle('Fusion')
        cls.qt.setStyleSheet(STYLE)
        cls.qt.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.folder = TemporaryDirectory()
        self.store = Store(Path(self.folder.name) / 'test.db')
        self.windows = []

    def tearDown(self):
        for window in self.windows:
            window.close()
        self.qt.processEvents()
        self.store.close()
        self.folder.cleanup()

    def window(self, review=False):
        window = App(self.store, review=review, dry_run=True)
        self.windows.append(window)
        window.show()
        self.qt.processEvents()
        return window

    def test_editor_review_completion_and_safe_preview(self):
        manager = self.window()
        self.assertFalse(manager.edit_button.isEnabled())
        editor = Editor(self.store)
        editor.title.setText('UI test reminder')
        editor.notes.setPlainText('Example notes')
        editor.save()
        self.assertEqual(editor.result(), QDialog.DialogCode.Accepted)
        manager.refresh()
        self.assertEqual(len(manager.items), 1)
        editor = Editor(self.store, manager.selected())
        editor.title.setText('Edited reminder')
        editor.save()
        self.assertEqual(self.store.list()[0].title, 'Edited reminder')
        for status in ('Paused', 'Completed'):
            self.store.save(Reminder('Hidden ' + status, status=status))
        self.store.save(Reminder('Outside window', all_day=False,
                               start=f'{(datetime.now().hour + 2) % 24:02}:00',
                               end=f'{(datetime.now().hour + 3) % 24:02}:00'))
        review = self.window(True)
        self.assertEqual(len(review.items), 1)
        with patch('app.request_shutdown') as shutdown, patch('app.QMessageBox.question', return_value=QMessageBox.StandardButton.Yes), patch('app.QMessageBox.information') as info:
            review.shutdown()
            shutdown.assert_not_called()
            info.assert_called_once()
        with patch('app.request_shutdown') as shutdown, patch('app.QMessageBox.question', return_value=QMessageBox.StandardButton.No):
            review.dry_run = False
            review.shutdown()
            shutdown.assert_not_called()
        review.complete()
        self.assertEqual(len(review.items), 0)
        self.assertEqual(self.store.list()[-1].status, 'Completed')
        self.assertTrue(review.shutdown_button.isEnabled())

    def test_invalid_editor_and_time_picker(self):
        editor = Editor(self.store)
        editor.all_day.setChecked(False)
        self.assertTrue(editor.start.isEnabled())
        editor.title.setText('Time test')
        editor.start.setTime(QTime(9, 0))
        editor.end.setTime(QTime(9, 0))
        with patch('app.QMessageBox.warning') as warning:
            editor.save()
            warning.assert_called_once()
        self.assertEqual(self.store.list(), [])
        editor.end.setTime(QTime(17, 0))
        editor.save()
        self.assertEqual(self.store.list()[0].end, '17:00')

    def test_delete_confirmation_and_refresh(self):
        self.store.save(Reminder('Delete me'))
        manager = self.window()
        with patch('app.QMessageBox.question', return_value=QMessageBox.StandardButton.No):
            manager.delete()
        self.assertEqual(len(self.store.list()), 1)
        with patch('app.QMessageBox.question', return_value=QMessageBox.StandardButton.Yes):
            manager.delete()
        self.assertEqual(self.store.list(), [])
        self.assertFalse(manager.complete_button.isEnabled())

    def test_shutdown_success_failure_and_storage_failure_are_mocked(self):
        review = self.window(True)
        review.dry_run = False
        with patch('app.request_shutdown') as shutdown, patch('app.QMessageBox.question', return_value=QMessageBox.StandardButton.Yes), patch.object(self.qt, 'quit') as quit_app:
            review.shutdown()
            shutdown.assert_called_once()
            quit_app.assert_called_once()
        with patch('app.request_shutdown', side_effect=OSError('denied')), patch('app.QMessageBox.question', return_value=QMessageBox.StandardButton.Yes), patch('app.QMessageBox.critical') as error:
            review.shutdown()
            error.assert_called_once()
            self.assertFalse(review.sending)
        with patch.object(self.store, 'list', side_effect=ValueError('Bad data')), patch('app.QMessageBox.critical'), patch('app.request_shutdown') as shutdown:
            review.shutdown()
            shutdown.assert_not_called()
            self.assertFalse(review.shutdown_button.isEnabled())

    def test_minimum_layout_keeps_actions_visible(self):
        self.store.save(Reminder('Long reminder ' * 14, notes='Long notes\n' * 100))
        for review in (False, True):
            window = self.window(review)
            window.resize(800, 650)
            self.qt.processEvents()
            for child in window.findChildren(__import__('PyQt6.QtWidgets', fromlist=['QPushButton']).QPushButton):
                if child.isVisible():
                    position = child.mapTo(window, child.rect().bottomRight())
                    self.assertLess(position.y(), window.height())
                    self.assertLess(position.x(), window.width())

    def test_completion_does_not_overwrite_newer_notes(self):
        self.store.save(Reminder('Concurrent'))
        window = self.window()
        item = self.store.list()[0]
        item.notes = 'Updated from another window'
        self.store.save(item)
        window.complete()
        self.assertEqual(self.store.list()[0].notes, item.notes)
        self.assertEqual(self.store.list()[0].status, 'Completed')

    def test_appearance_persists_and_updates_other_windows(self):
        self.store.save(Reminder('Keep my data', notes='Do not change'))
        manager = self.window()
        review = manager.preview()
        before = self.store.list()
        settings = SettingsPanel(self.store, manager.appearance, manager)
        settings.mode_combo.setCurrentText('Dark')
        self.qt.processEvents()
        self.assertTrue(manager.appearance.dark)
        self.assertEqual(review.appearance.mode, 'Dark')
        editor = Editor(self.store, before[0], manager)
        self.assertEqual(editor.palette().color(editor.foregroundRole()).name(), DARK['text'])
        reopened = Appearance(Path(self.folder.name) / 'appearance.ini')
        self.assertEqual(reopened.mode, 'Dark')
        reopened.set_mode('Light')
        manager.refresh()
        self.assertFalse(manager.appearance.dark)
        self.assertEqual(review.appearance.mode, 'Light')
        self.assertEqual(self.store.list(), before)
        review.close()

    def test_system_appearance_follows_signal_and_manual_choice_stays(self):
        manager = self.window()
        appearance = manager.appearance
        appearance.set_mode('System')
        appearance.system_changed(Qt.ColorScheme.Dark)
        self.assertTrue(appearance.dark)
        appearance.system_changed(Qt.ColorScheme.Light)
        self.assertFalse(appearance.dark)
        appearance.set_mode('Dark')
        appearance.system_changed(Qt.ColorScheme.Light)
        self.assertTrue(appearance.dark)
        with self.assertRaises(ValueError):
            appearance.set_mode('Unrecognized')

    def test_search_notes_and_status_filters(self):
        self.store.save(Reminder('Backup', notes='Copy the important files'))
        self.store.save(Reminder('Desk', status='Paused'))
        manager = self.window()
        manager.search.setText('IMPORTANT')
        self.assertEqual([r.title for r in manager.items.values()], ['Backup'])
        manager.status_filter.setCurrentText('Paused')
        self.assertEqual(manager.items, {})
        self.assertFalse(manager.edit_button.isEnabled())
        manager.search.clear()
        self.assertEqual([r.title for r in manager.items.values()], ['Desk'])
        manager.status_filter.setCurrentText('All statuses')
        self.assertEqual(len(manager.items), 2)

    def test_theme_tokens_resolve_and_empty_dark_review_stays_safe(self):
        self.assertNotIn('$', stylesheet(True))
        self.assertNotIn('$', stylesheet(False))
        review = self.window(True)
        review.appearance.set_mode('Dark')
        self.assertFalse(review.edit_button.isEnabled())
        self.assertTrue(review.shutdown_button.isEnabled())
        with patch('app.request_shutdown') as shutdown, patch('app.QMessageBox.question', return_value=QMessageBox.StandardButton.Yes), patch('app.QMessageBox.information'):
            review.shutdown()
            shutdown.assert_not_called()

    def test_library_settings_sort_filter_and_compact_rows(self):
        self.store.save(Reminder('Zebra', status='Paused'))
        self.store.save(Reminder('Apple'))
        manager = self.window()
        settings = SettingsPanel(self.store, manager.appearance, manager)
        settings.sort_combo.setCurrentText('Title A–Z')
        self.assertEqual([r.title for r in manager.items.values()], ['Apple', 'Zebra'])
        settings.sort_combo.setCurrentText('Due now first')
        self.assertEqual(next(iter(manager.items.values())).title, 'Apple')
        settings.preview_check.setChecked(False)
        self.assertEqual(manager.list_widget.item(0).sizeHint().height(), 76)
        settings.filter_combo.setCurrentText('Paused')
        another = manager.manage()
        self.assertEqual([r.title for r in another.items.values()], ['Zebra'])
        review = manager.preview()
        self.assertEqual([r.title for r in review.items.values()], ['Apple'])
        reopened = Appearance(Path(self.folder.name) / 'appearance.ini')
        self.assertFalse(reopened.show_preview)
        self.assertEqual(reopened.default_filter, 'Paused')
        self.assertEqual(reopened.sort_order, 'Due now first')
        another.close()
        review.close()

    def test_settings_backup_and_cancel_preserve_live_database(self):
        self.store.save(Reminder('Backup this', notes='Café 日本語', all_day=False, start='22:00', end='02:00'))
        manager = self.window()
        settings = SettingsPanel(self.store, manager.appearance, manager)
        destination = Path(self.folder.name) / 'backup.db'
        with patch('app.QFileDialog.getSaveFileName', return_value=(str(destination), '')), patch('app.QMessageBox.information'):
            settings.backup()
        copy = Store(destination)
        self.assertEqual(copy.list(), self.store.list())
        copy.close()
        with self.assertRaises(ValueError):
            self.store.backup(self.store.path)
        with patch('app.QFileDialog.getSaveFileName', return_value=('', '')), patch.object(self.store, 'backup') as backup:
            settings.backup()
            backup.assert_not_called()
        self.assertEqual(self.store.list()[0].title, 'Backup this')

    def test_completed_and_paused_reminders_can_be_reactivated(self):
        self.store.save(Reminder('Again', status='Completed'))
        manager = self.window()
        self.assertEqual(manager.complete_button.text(), 'Reactivate')
        manager.complete()
        self.assertEqual(self.store.list()[0].status, 'Active')
        manager.complete()
        self.assertEqual(self.store.list()[0].status, 'Completed')

    def test_both_palettes_are_neutral_grays(self):
        for palette in (LIGHT, DARK):
            for color in palette.values():
                self.assertEqual(color[1:3], color[3:5])
                self.assertEqual(color[3:5], color[5:7])


if __name__ == '__main__':
    main()
