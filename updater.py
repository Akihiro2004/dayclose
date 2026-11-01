"""Public GitHub releases, verified downloads, and a non-blocking Qt update controller."""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, unquote
from urllib.request import Request, HTTPRedirectHandler, build_opener

from PyQt6.QtCore import QObject, QThread, pyqtSignal
from version import APP_VERSION, RELEASE_REPOSITORY

MAX_INSTALLER = 512 * 1024 * 1024
RELEASES_URL = f'https://github.com/{RELEASE_REPOSITORY}/releases'


class UpdateError(Exception):
    pass


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r'v?(0|[1-9]\d{0,5})\.(0|[1-9]\d{0,5})\.(0|[1-9]\d{0,5})', value):
        raise UpdateError('Release versions must use vMAJOR.MINOR.PATCH, for example v1.0.1.')
    return tuple(int(part) for part in value.removeprefix('v').split('.'))


def allowed_url(url):
    parsed = urlparse(url)
    host = parsed.hostname or ''
    return (parsed.scheme == 'https' and not parsed.username and not parsed.password and
            parsed.port in (None, 443) and
            (host in ('github.com', 'api.github.com') or host.endswith('.githubusercontent.com')))


class GitHubRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not allowed_url(newurl):
            raise UpdateError('GitHub redirected the download to an unexpected address.')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def open_url(url):
    if not allowed_url(url):
        raise UpdateError('The update address is not a supported GitHub HTTPS address.')
    request = Request(url, headers={'User-Agent': f'Dayclose/{APP_VERSION}',
                                   'Accept': 'application/vnd.github+json' if 'api.github.com/' in url else 'application/octet-stream',
                                   'X-GitHub-Api-Version': '2022-11-28'})
    return build_opener(GitHubRedirect()).open(request, timeout=20)


def asset_url(asset, expected_name):
    url = asset.get('browser_download_url', '')
    parsed = urlparse(url)
    prefix = f'/{RELEASE_REPOSITORY}/releases/download/'
    if (not allowed_url(url) or parsed.hostname != 'github.com' or not parsed.path.startswith(prefix) or
            unquote(parsed.path.rsplit('/', 1)[-1]) != expected_name or parsed.query or parsed.fragment):
        raise UpdateError('The release installer address does not belong to the Dayclose repository.')
    return url


@dataclass(frozen=True)
class Release:
    version: str
    name: str
    url: str
    size: int
    sha256: str
    notes: str
    page: str


def parse_release(data, current=APP_VERSION, read_small=None):
    if not isinstance(data, dict):
        raise UpdateError('GitHub returned an invalid release response.')
    if data.get('draft') or data.get('prerelease'):
        return None
    tag = data.get('tag_name', '')
    if version_tuple(tag) <= version_tuple(current):
        return None
    version = tag.removeprefix('v')
    name = f'Dayclose-Setup-{version}.exe'
    assets = data.get('assets', [])
    if not isinstance(assets, list):
        raise UpdateError('The release asset list is invalid.')
    matches = [a for a in assets if isinstance(a, dict) and a.get('name') == name and a.get('state') == 'uploaded']
    if len(matches) != 1:
        raise UpdateError(f'The release is missing its Windows installer: {name}')
    asset = matches[0]
    url = asset_url(asset, name)
    size = asset.get('size', 0)
    if type(size) is not int or not 0 < size <= MAX_INSTALLER:
        raise UpdateError('The release installer has an invalid size.')
    digest = asset.get('digest') or ''
    if re.fullmatch(r'sha256:[a-fA-F0-9]{64}', digest):
        sha256 = digest.split(':')[1].lower()
    else:
        checksums = [a for a in assets if isinstance(a, dict) and a.get('name') == name + '.sha256' and a.get('state') == 'uploaded']
        if len(checksums) != 1 or read_small is None:
            raise UpdateError('This release has no SHA-256 checksum. Upload the installer checksum alongside it.')
        text = read_small(asset_url(checksums[0], name + '.sha256')).decode('ascii').strip()
        match = re.fullmatch(r'([a-fA-F0-9]{64})(?:[ \t]+\*?' + re.escape(name) + r')?', text)
        if not match:
            raise UpdateError('The release checksum file is invalid.')
        sha256 = match.group(1).lower()
    page = f'{RELEASES_URL}/tag/{tag}'
    return Release(version, name, url, size, sha256, str(data.get('body') or '')[:20000], page)


def check_release(current=APP_VERSION, opener=open_url):
    def read_small(url):
        with opener(url) as response:
            contents = response.read(2 * 1024 * 1024 + 1)
        if len(contents) > 2 * 1024 * 1024:
            raise UpdateError('The update response is too large.')
        return contents
    try:
        body = read_small(f'https://api.github.com/repos/{RELEASE_REPOSITORY}/releases/latest')
        return parse_release(json.loads(body), current, read_small)
    except HTTPError as error:
        if error.code == 404:
            raise UpdateError('No public release is available yet. The repository may be private or have no published release.') from error
        if error.code in (403, 429):
            raise UpdateError('GitHub is limiting update checks. Please try again later.') from error
        raise UpdateError(f'GitHub could not check for updates (HTTP {error.code}).') from error
    except (URLError, TimeoutError, OSError) as error:
        raise UpdateError('Could not reach GitHub. Check your connection and try again.') from error
    except (ValueError, UnicodeError) as error:
        raise UpdateError('GitHub returned an unreadable release response.') from error


def download_release(release, folder, cancel, progress=lambda _: None, opener=open_url):
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / release.name
    handle, temporary = tempfile.mkstemp(prefix='download-', suffix='.part', dir=folder)
    temporary = Path(temporary)
    try:
        digest = hashlib.sha256()
        count = 0
        started = time.monotonic()
        with os.fdopen(handle, 'wb') as output, opener(release.url) as response:
            while True:
                if cancel.is_set():
                    raise UpdateError('Download cancelled. You can try again whenever you are ready.')
                if time.monotonic() - started > 30 * 60:
                    raise UpdateError('The download took too long. Please try again.')
                chunk = response.read(128 * 1024)
                if not chunk:
                    break
                count += len(chunk)
                if count > release.size or count > MAX_INSTALLER:
                    raise UpdateError('The installer is larger than the release metadata says.')
                digest.update(chunk)
                output.write(chunk)
                progress(min(100, int(count * 100 / release.size)))
        if count != release.size or digest.hexdigest() != release.sha256:
            raise UpdateError('Installer verification failed. Nothing was installed; download it again.')
        with temporary.open('rb') as downloaded:
            if downloaded.read(2) != b'MZ':
                raise UpdateError('The downloaded file is not a Windows installer.')
        if cancel.is_set():
            raise UpdateError('Download cancelled. Nothing was installed.')
        temporary.replace(target)
        return target
    finally:
        temporary.unlink(missing_ok=True)


def launch_helper(installer, release, folder, dry_run=False):
    if not getattr(sys, 'frozen', False):
        raise UpdateError('Install updates from the packaged Dayclose app. Source mode can check and download updates.')
    helper = Path(sys._MEIPASS) / 'Dayclose.UpdateHelper.exe'
    cached_helper = folder / 'Dayclose.UpdateHelper.exe'
    shutil.copy2(helper, cached_helper)
    args = [str(cached_helper), str(installer.resolve()), release.sha256,
            str(Path(sys.executable).parent.resolve()), str(folder.parent.resolve()),
            str(os.getpid()), release.version, 'true' if dry_run else 'false']
    return subprocess.Popen(args, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


class UpdateWorker(QThread):
    result = pyqtSignal(object)
    error = pyqtSignal(str)
    progress = pyqtSignal(int)

    def __init__(self, operation, parent=None):
        super().__init__(parent)
        self.operation = operation

    def run(self):
        try:
            self.result.emit(self.operation(self.progress.emit))
        except Exception as error:
            self.error.emit(str(error) if isinstance(error, UpdateError) else 'The update could not finish. Please check your connection and try again.')


class UpdateController(QObject):
    changed = pyqtSignal()
    install_ready = pyqtSignal()

    def __init__(self, folder, parent=None):
        super().__init__(parent)
        self.folder = folder / 'updates'
        self.release = None
        self.installer = None
        self.worker = None
        self.state = 'idle'
        self.message = 'Check GitHub for the latest stable release.'
        self.percent = 0
        self.cancel_event = threading.Event()

    @property
    def busy(self):
        return self.worker is not None

    def start(self, operation, result):
        if self.busy:
            return
        worker = UpdateWorker(operation, self)
        self.worker = worker
        worker.result.connect(result)
        worker.error.connect(self.failed)
        worker.progress.connect(self.progress)
        worker.finished.connect(self.finished)
        worker.finished.connect(worker.deleteLater)
        worker.start()
        self.changed.emit()

    def check(self):
        if self.busy:
            return
        self.state, self.message = 'checking', 'Checking GitHub…'
        self.start(lambda _: check_release(), self.checked)

    def checked(self, release):
        self.release, self.installer = release, None
        self.state = 'available' if release else 'current'
        self.message = f'Dayclose {release.version} is ready to download.' if release else f'You are up to date. Dayclose {APP_VERSION} is the latest available version.'
        self.changed.emit()

    def download(self):
        if self.busy or not self.release:
            return
        self.cancel_event.clear()
        self.state, self.percent, self.message = 'downloading', 0, 'Downloading the installer…'
        release = self.release
        self.start(lambda progress: download_release(release, self.folder, self.cancel_event, progress), self.downloaded)

    def downloaded(self, path):
        self.installer, self.state, self.message = path, 'ready', 'Installer verified. Ready to install and restart.'
        self.changed.emit()

    def progress(self, percent):
        self.percent = percent
        self.changed.emit()

    def failed(self, message):
        self.state, self.message = 'error', message
        self.changed.emit()

    def finished(self):
        self.worker = None
        self.changed.emit()

    def cancel(self):
        self.cancel_event.set()

    def stop(self):
        self.cancel()
        if self.worker:
            self.worker.wait()
