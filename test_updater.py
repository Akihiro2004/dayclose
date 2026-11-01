import hashlib
import io
from pathlib import Path
import threading
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from PyQt6.QtWidgets import QApplication, QTabWidget
from app import App, SettingsPanel
from core import Store
from updater import (Release, UpdateError, UpdateController, allowed_url, check_release,
                     download_release, parse_release, version_tuple)


PAYLOAD = b'MZ' + b'test installer bytes' * 100
DIGEST = hashlib.sha256(PAYLOAD).hexdigest()


def metadata(version='1.0.1'):
    name = f'Dayclose-Setup-{version}.exe'
    return dict(tag_name='v' + version, draft=False, prerelease=False, body='A new release', assets=[
        dict(name=name, state='uploaded', size=len(PAYLOAD), digest='sha256:' + DIGEST,
             browser_download_url=f'https://github.com/Akihiro2004/dayclose/releases/download/v{version}/{name}')])


def parse_test_release(data, **kwargs):
    # Fixtures model an installed 1.0.0 independently of the version being built.
    return parse_release(data, current='1.0.0', **kwargs)


class ReleaseTests(TestCase):
    def test_numeric_versions_and_stable_releases_only(self):
        self.assertGreater(version_tuple('v1.10.0'), version_tuple('1.9.9'))
        self.assertEqual(parse_test_release(metadata()).version, '1.0.1')
        self.assertIsNone(parse_test_release(metadata('1.0.0')))
        self.assertIsNone(parse_test_release(metadata('0.9.0')))
        data = metadata()
        data['prerelease'] = True
        self.assertIsNone(parse_test_release(data))
        for value in ('1.2', 'v1.2.3-beta', '1.02.3', '../evil', None):
            with self.assertRaises(UpdateError):
                version_tuple(value)

    def test_missing_asset_bad_size_and_foreign_urls_are_rejected(self):
        for mutate in (
            lambda d: d.update(assets=[]),
            lambda d: d['assets'][0].update(size=0),
            lambda d: d['assets'][0].update(browser_download_url='https://evil.example/installer.exe'),
            lambda d: d['assets'][0].update(browser_download_url=d['assets'][0]['browser_download_url'].replace('Akihiro2004', 'someone-else')),
            lambda d: d['assets'][0].update(digest=None),
        ):
            data = metadata()
            mutate(data)
            with self.assertRaises(UpdateError):
                parse_test_release(data)
        self.assertFalse(allowed_url('http://github.com/installer.exe'))
        self.assertFalse(allowed_url('https://github.com.evil.example/installer.exe'))
        self.assertTrue(allowed_url('https://release-assets.githubusercontent.com/path'))

    def test_checksum_sidecar_fallback(self):
        data = metadata()
        asset = data['assets'][0]
        asset.pop('digest')
        data['assets'].append(dict(name=asset['name'] + '.sha256', state='uploaded',
                                  browser_download_url=asset['browser_download_url'] + '.sha256'))
        self.assertEqual(parse_test_release(data, read_small=lambda _: f'{DIGEST}  {asset["name"]}'.encode()).sha256, DIGEST)
        with self.assertRaises(UpdateError):
            parse_test_release(data, read_small=lambda _: b'not a checksum')

    def test_offline_private_and_rate_limit_messages(self):
        for failure, text in ((HTTPError('', 404, '', {}, None), 'No public release'),
                              (HTTPError('', 403, '', {}, None), 'limiting'),
                              (URLError('offline'), 'connection')):
            with self.assertRaisesRegex(UpdateError, text):
                check_release(opener=lambda _, error=failure: (_ for _ in ()).throw(error))

    def test_valid_corrupt_truncated_and_cancelled_downloads(self):
        release = parse_test_release(metadata())
        with TemporaryDirectory() as path:
            folder = Path(path)
            result = download_release(release, folder, threading.Event(), opener=lambda _: io.BytesIO(PAYLOAD))
            self.assertEqual(result.read_bytes(), PAYLOAD)
            for payload in (b'MZbad', PAYLOAD[:-1], b'ZZ' + PAYLOAD[2:], PAYLOAD + b'extra'):
                with self.assertRaises(UpdateError):
                    download_release(release, folder, threading.Event(), opener=lambda _: io.BytesIO(payload))
                self.assertEqual(result.read_bytes(), PAYLOAD)
                self.assertEqual(list(folder.glob('*.part')), [])
            cancel = threading.Event()
            cancel.set()
            with self.assertRaisesRegex(UpdateError, 'cancelled'):
                download_release(release, folder, cancel, opener=lambda _: io.BytesIO(PAYLOAD))
            self.assertEqual(list(folder.glob('*.part')), [])


class UpdateUiTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])
        cls.qt.setStyle('Fusion')
        cls.qt.setQuitOnLastWindowClosed(False)

    def test_notice_updates_tab_and_install_are_explicit(self):
        with TemporaryDirectory() as folder:
            store = Store(Path(folder) / 'reminders.db')
            update = UpdateController(Path(folder))
            window = App(store, dry_run=True, updater=update)
            window.show()
            settings = SettingsPanel(store, window.appearance, window, update)
            try:
                self.assertTrue(window.update_button.isHidden())
                self.assertEqual(settings.findChild(QTabWidget).tabText(3), 'Updates')
                update.checked(parse_test_release(metadata()))
                self.assertFalse(window.update_button.isHidden())
                self.assertIn('1.0.1', window.update_button.text())
                self.assertEqual(settings.updates_panel.notes.toPlainText(), 'A new release')
                with patch.object(update, 'download') as download:
                    settings.updates_panel.act()
                    download.assert_called_once()
                calls = []
                update.install_ready.connect(lambda: calls.append(True))
                update.downloaded(Path(folder) / 'installer.exe')
                self.assertEqual(calls, [])
                settings.updates_panel.act()
                self.assertEqual(calls, [True])
            finally:
                settings.close()
                window.close()
                self.qt.processEvents()
                store.close()

    def test_network_check_runs_in_background_and_error_keeps_app_usable(self):
        with TemporaryDirectory() as folder:
            controller = UpdateController(Path(folder))
            with patch('updater.check_release', side_effect=UpdateError('No public release yet')):
                controller.check()
                self.assertTrue(controller.busy)
                self.assertTrue(controller.worker.wait(5000))
                self.qt.processEvents()
                self.assertEqual(controller.state, 'error')
                self.assertIn('No public release', controller.message)
                self.assertFalse(controller.busy)
