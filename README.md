# Dayclose

A local Windows reminder manager with a dedicated shutdown review shortcut.

## Use

Run `release\Dayclose-Setup-1.0.0.exe` to install for your Windows account.
The installer adds Start menu shortcuts, optional desktop shortcuts, and an entry
in Windows Settings > Apps > Installed apps. No Python installation is required.
Uninstalling removes the application but keeps your reminders for a later reinstall.

For portable use, run `dist\Dayclose.exe` to manage reminders, or run it with
`--shutdown` to review reminders before shutting down. `install-shortcuts.ps1` is
an alternative for portable use only; keep that executable in its project folder
after creating portable shortcuts. Prefer the installer for normal use.

1. Add a reminder with a title, optional notes, status, and daily time window.
2. Use **Review & Shut Down** when you finish using the computer.
3. Read reminders and optionally mark finished tasks Completed.
4. Choose **Shut down…**, then confirm. **Stay on** or closing the window leaves the computer on.

**Preview shutdown** is safe to try: it never executes a shutdown command.
Even an empty review requires a click and confirmation before real shutdown.

## Appearance and navigation

Open **Settings > Appearance** to choose **System**, **Light**, or **Dark**.
The main interface is monochrome; Dark uses neutral dark-gray surfaces.
Changes apply immediately to the manager, editor, dialogs, and shutdown review.
System follows Windows' color scheme. Your selection is saved alongside reminder
data in `appearance.ini`; separately launched windows pick up changes within 15 seconds.
Uninstalling and reinstalling preserves this preference and your reminders.

**Settings > Library** controls sorting (newest, title, or due now first), the
default status filter for new manager windows, and notes previews.
**Settings > Data** can create a consistent SQLite reminder backup while the app
is running, or open your data folder. Backups contain reminders, not preferences.
Use **Reactivate** to return a paused or completed reminder to Active.

Use the search field to find reminder titles or notes, and the status menu to
filter Active, Paused, or Completed reminders. Shutdown review always shows all
currently due reminders, independent of the manager's filters.

## Reminder rules

- **Active**: appears in shutdown review when inside its time window.
- **Paused**: saved, but excluded from shutdown review.
- **Completed**: saved, but excluded until manually changed back to Active.
- **All day**: eligible at any time while Active.
- Time ranges repeat every day, using the computer's current local timezone.
- Start is included; end is excluded. 18:00–23:00 shows at 18:00 but not 23:00.
- Overnight ranges work: 22:00–02:00 shows before and after midnight.
- Equal start and end are rejected; select All day instead.
- A review refreshes every 15 seconds, on demand, and before shutdown confirmation.
- Status and reminder edits save immediately. Completing an item is permanent until you reactivate it.

This version uses daily times, not calendar date ranges or per-weekday schedules.
It has no background service, automatic shutdown, cloud account, or network access.
Windows' regular Shut down button bypasses this application.

## Storage

Data lives in `%LOCALAPPDATA%\BeforeYouGo\reminders.db` using SQLite transactions.
Multiple manager and review windows share the same database. Close all application
windows before copying this file for a backup. Data is local and is not encrypted.
Replacing the executable does not remove saved reminders.

## Shutdown behavior

After explicit confirmation, the app requests `shutdown.exe /s /t 0`, without `/f`.
Windows may let another application block shutdown for unsaved work. There is no
automatic countdown and no attempt to bypass Windows Update or other shutdown blockers.
Actual power-off is deliberately excluded from automated testing.

Microsoft reference: https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/shutdown

## Development

Python 3.12 with PyQt6. Install development dependencies with
`python -m pip install -r requirements.txt`. PyInstaller is needed for packaging;
Inno Setup 6 is needed to build the installer.

```powershell
python app.py
python app.py --shutdown --dry-run --data-dir .\test-data
python -m unittest -v test_reminders
.\build.ps1
.\build-installer.ps1
.\install-shortcuts.ps1
```

`verify-installer.ps1` tests a fresh installation, safe preview launch, and uninstall
in an isolated project folder. It refuses to run over an existing installed copy.

The bundled executable does not require Python to be installed. The application
and installer are unsigned. Windows may display an unknown-publisher or SmartScreen
prompt; creating an installer does not establish publisher trust or app reputation.
