// Runs outside Dayclose so its executable is unlocked during replacement.
using System;
using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;
using System.Threading;
using System.Windows.Forms;

internal static class UpdateHelper {
    static string Quote(string value) {
        if (value.IndexOf('"') >= 0) throw new Exception("An update path contains an invalid quote.");
        return "\"" + value.TrimEnd('\\') + "\"";
    }

    [STAThread]
    static int Main(string[] args) {
        string app = null, data = null, log = null;
        bool dryRun = false;
        try {
            if (args.Length != 7) throw new Exception("Invalid update handoff.");
            string installer = Path.GetFullPath(args[0]);
            string digest = args[1].ToLowerInvariant();
            string directory = Path.GetFullPath(args[2]);
            data = Path.GetFullPath(args[3]);
            int parentId = Int32.Parse(args[4]);
            string expectedVersion = args[5];
            dryRun = Boolean.Parse(args[6]);
            app = Path.Combine(directory, "Dayclose.exe");
            string updates = Path.Combine(data, "updates");
            Directory.CreateDirectory(updates);
            log = Path.Combine(updates, "last-update.txt");
            if (!File.Exists(installer) || !File.Exists(app) || digest.Length != 64)
                throw new Exception("The update installer or current application is missing.");

            if (parentId > 0) {
                try {
                    using (Process parent = Process.GetProcessById(parentId)) {
                        if (!parent.WaitForExit(120000)) throw new Exception("Dayclose did not close. Save your work and try again.");
                    }
                } catch (ArgumentException) { /* It has already exited. */ }
            }
            // The PyInstaller parent can outlive its Python child briefly.
            bool unlocked = false;
            for (int attempt = 0; attempt < 60; attempt++) {
                try {
                    using (File.Open(app, FileMode.Open, FileAccess.ReadWrite, FileShare.None)) { }
                    unlocked = true;
                    break;
                } catch (IOException) { Thread.Sleep(500); }
            }
            if (!unlocked) throw new Exception("Another Dayclose window is still open. Close it before updating. No application was forced to close.");

            using (SHA256 sha = SHA256.Create())
            using (FileStream stream = File.OpenRead(installer)) {
                string actual = BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
                if (actual != digest) throw new Exception("The installer checksum changed. Download the update again.");
            }
            File.WriteAllText(log, "Installing Dayclose " + expectedVersion);
            string installLog = Path.Combine(updates, "installer.log");
            var setup = new ProcessStartInfo(installer,
                "/SP- /SILENT /SUPPRESSMSGBOXES /NORESTART /RESTARTEXITCODE=3010 /NOCLOSEAPPLICATIONS /NORESTARTAPPLICATIONS /DIR=" + Quote(directory) + " /LOG=" + Quote(installLog));
            setup.UseShellExecute = false;
            int code;
            using (Process process = Process.Start(setup)) {
                process.WaitForExit();
                code = process.ExitCode;
            }
            if (code == 3010) throw new Exception("Windows needs a restart to finish updating Dayclose. Your computer was not restarted automatically.");
            if (code != 0) throw new Exception("The installer did not complete (exit code " + code + "). You can try again. Details: " + installLog);
            string installedVersion = FileVersionInfo.GetVersionInfo(app).ProductVersion.Trim();
            if (installedVersion != expectedVersion)
                throw new Exception("The installed version did not match the release. Please run the installer manually.");
            File.WriteAllText(log, "Updated successfully to Dayclose " + expectedVersion);
            Restart(app, data, dryRun);
            return 0;
        } catch (Exception error) {
            try { if (log != null) File.WriteAllText(log, "Update failed: " + error.Message); } catch { }
            MessageBox.Show(error.Message, "Dayclose could not finish updating", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            try { if (app != null && data != null && File.Exists(app)) Restart(app, data, dryRun); } catch { }
            return 1;
        }
    }

    static void Restart(string app, string data, bool dryRun) {
        var start = new ProcessStartInfo(app, "--data-dir " + Quote(data) + (dryRun ? " --dry-run" : ""));
        start.WorkingDirectory = Path.GetDirectoryName(app);
        start.UseShellExecute = false;
        // An old shutdown review always reopens as the reminder manager.
        Process.Start(start);
    }
}
