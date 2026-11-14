using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;
using System.Windows.Forms;

internal static class Launcher
{
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern IntPtr FindWindow(string className, string windowName);
    [DllImport("user32.dll")]
    private static extern bool ShowWindow(IntPtr handle, int command);
    [DllImport("user32.dll")]
    private static extern bool SetForegroundWindow(IntPtr handle);

    [STAThread]
    private static void Main()
    {
        bool created;
        string root = AppDomain.CurrentDomain.BaseDirectory;
        using (var mutex = new Mutex(true, "Local\\LeanPlan-" + root.GetHashCode().ToString("X"), out created))
        {
            if (!created)
            {
                IntPtr window = FindWindow(null, "Lean Plan");
                if (window != IntPtr.Zero) { ShowWindow(window, 9); SetForegroundWindow(window); }
                return;
            }
            try
            {
                string python = Path.Combine(root, ".runtime", "pythonw.exe");
                string app = Path.Combine(root, "app.py");
                if (!File.Exists(python) || !File.Exists(app))
                    throw new FileNotFoundException("Keep Lean Plan.exe together with app.py, static, leanplan and .runtime. Move the whole folder if needed.");
                var info = new ProcessStartInfo(python, "\"" + app + "\"");
                info.WorkingDirectory = root;
                info.UseShellExecute = false;
                info.CreateNoWindow = true;
                info.EnvironmentVariables["PYTHONUTF8"] = "1";
                info.EnvironmentVariables["PYTHONDONTWRITEBYTECODE"] = "1";
                using (var process = Process.Start(info))
                {
                    process.WaitForExit();
                    if (process.ExitCode != 0)
                        MessageBox.Show("Lean Plan could not start. See data\\app.log for details, or run Start Lean Plan.cmd to see the error.", "Lean Plan", MessageBoxButtons.OK, MessageBoxIcon.Error);
                }
            }
            catch (Exception error)
            {
                MessageBox.Show(error.Message, "Lean Plan", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
            finally { mutex.ReleaseMutex(); }
        }
    }
}
