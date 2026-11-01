# Dayclose releases and in-app updates

Dayclose checks **Akihiro2004/dayclose** for the latest published stable GitHub
release. No GitHub account or token is bundled in the app. The repository must be
public for users to check and download updates. Drafts and prereleases are ignored.

The current version remains **1.0.0**. Changing only release notes or replacing the
installer under v1.0.0 does not create an update for existing 1.0.0 installations.
For a future update, choose a higher version such as 1.0.1.

## Prepare and publish

1. Set `APP_VERSION` in `version.py` to the new version. This is the single source
   for the app, Windows executable metadata, and installer version.
2. Run `./build-installer.ps1` on Windows. It runs tests, compiles the update helper,
   bundles the application, and builds the installer and checksum.
3. Publish a stable GitHub Release tagged `vX.Y.Z`, with both files attached:
   - `Dayclose-Setup-X.Y.Z.exe`
   - `Dayclose-Setup-X.Y.Z.exe.sha256`
4. Mark the stable release as the latest release on GitHub.

Alternatively, commit the version change and push a matching `vX.Y.Z` tag. The
included GitHub Actions workflow builds on Windows and creates a **draft** release
with the installer and checksum. Review its release notes and publish it when ready.
The workflow rejects a tag that does not match the app version.

The workflow needs GitHub Actions enabled with permission to create releases.

## What users see

- The manager checks once after startup, without blocking the interface.
- A new-release button appears when a higher stable version is available.
- **Settings > Updates** offers checking, release notes, download progress, and
  cancellation. Automatic checks never download or install by themselves.
- After downloading, choose **Install and restart** and confirm.
- Editors must be saved or closed. A reminder database snapshot is made before
  installation under the data folder's `updates` directory.
- A separate helper waits for Dayclose to exit, checks the installer checksum
  again, runs the installer in the current application directory, then reopens
  the manager with the same data folder. It never initiates computer shutdown.
- The helper does not force-close other Dayclose processes. If another copy is
  open, close it before updating. Failure details are shown, and the app is
  reopened when possible. Logs are in `updates/last-update.txt` and `installer.log`.
- Notes and preferences stay in the existing data directory. Source mode can
  check and download updates; installation requires the packaged executable.

## Verification and limits

Downloads must match the expected installer asset name, published size, and
GitHub's SHA-256 asset digest (or the matching checksum sidecar). Addresses and
redirects are restricted to GitHub HTTPS hosts. Invalid, incomplete, oversized,
or cancelled downloads are not executed. A checksum detects corruption; it does
not replace Windows publisher signing. Releases and the GitHub account must be
kept secure.

`python -m unittest discover -v` covers version selection, checksums, URL rules,
download failures, cancellation, and update UI states. `verify-installer.ps1`
tests the actual local helper, installer, restart, and reminder/settings retention
in an isolated directory. It uses the current installer for handoff testing;
higher-version selection is tested with release fixtures.

Verify the live GitHub download path after publishing a public release. The local
checks do not establish clean-machine compatibility or SmartScreen reputation.

References:
- https://docs.github.com/en/rest/releases/releases#get-the-latest-release
- https://jrsoftware.org/ishelp/topic_setupcmdline.htm
