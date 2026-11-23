using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Reflection;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;

internal static class Launcher
{
    [STAThread]
    private static int Main(string[] args)
    {
        bool check = args.Length == 1 && args[0] == "--check";
        bool unattended = args.Length == 1 && args[0] == "--run";
        if (args.Length != 0 && !check && !unattended) return 2;
        using (var gate = new Mutex(false, @"Local\SentryVid007FlashAndStart"))
        {
            bool owner;
            try { owner = gate.WaitOne(0); }
            catch (AbandonedMutexException) { owner = true; }
            if (!owner)
            {
                if (args.Length == 0)
                    MessageBox.Show("已有一个烧录任务正在运行。", "SENTRY");
                return 3;
            }
            try
            {
                if (check || unattended) return Run(check, _ => { });
                Application.EnableVisualStyles();
                Application.SetCompatibleTextRenderingDefault(false);
                using (var window = new LaunchWindow()) Application.Run(window);
                return 0;
            }
            finally { gate.ReleaseMutex(); }
        }
    }

    internal static string ProjectDirectory()
    {
        string here = AppDomain.CurrentDomain.BaseDirectory;
        string configured = Environment.GetEnvironmentVariable("SENTRY_SYSTEM_ROOT");
        return String.IsNullOrWhiteSpace(configured) ? here : configured;
    }

    internal static int Run(bool check, Action<string> update)
    {
        StreamWriter log = null;
        object outputLock = new object();
        Action<string> write = line =>
        {
            if (String.IsNullOrEmpty(line)) return;
            lock (outputLock)
            {
                if (log != null) log.WriteLine(line);
                update(line);
            }
        };
        try
        {
            string project = ProjectDirectory();
            string folder = Path.Combine(project, "launcher", "logs");
            Directory.CreateDirectory(folder);
            string path = Path.Combine(folder, DateTime.Now.ToString("yyyyMMdd-HHmmss-fff") + ".log");
            log = new StreamWriter(path, false, new UTF8Encoding(false)) { AutoFlush = true };
            write("日志 " + path);
            string script;
            using (Stream resource = Assembly.GetExecutingAssembly().GetManifestResourceStream("FlashAndStart.ps1"))
            using (var reader = new StreamReader(resource, Encoding.UTF8)) script = reader.ReadToEnd();
            string powershell = Path.Combine(Environment.SystemDirectory, @"WindowsPowerShell\v1.0\powershell.exe");
            var options = new ProcessStartInfo(powershell, "-NoProfile -NonInteractive -EncodedCommand " +
                Convert.ToBase64String(Encoding.Unicode.GetBytes(script)))
            {
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                StandardOutputEncoding = Encoding.UTF8,
                StandardErrorEncoding = Encoding.UTF8,
                WorkingDirectory = project
            };
            options.EnvironmentVariables["SENTRY_LAUNCHER_PROJECT"] = project;
            options.EnvironmentVariables["SENTRY_LAUNCHER_CHECK"] = check ? "1" : "0";
            if (String.IsNullOrWhiteSpace(options.EnvironmentVariables["SENTRY_RK_KEY"]))
                options.EnvironmentVariables["SENTRY_RK_KEY"] = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
                    ".ssh", "id_ed25519");
            using (var process = new Process { StartInfo = options })
            {
                process.OutputDataReceived += (sender, data) => write(data.Data);
                process.ErrorDataReceived += (sender, data) => write(data.Data);
                process.Start();
                process.BeginOutputReadLine();
                process.BeginErrorReadLine();
                process.WaitForExit();
                return process.ExitCode;
            }
        }
        catch (Exception error)
        {
            write("[ERROR] " + error.Message);
            return 1;
        }
        finally { if (log != null) log.Dispose(); }
    }
}

internal sealed class LaunchWindow : Form
{
    private readonly Label status;
    private readonly ProgressBar progress;
    private readonly TextBox output;
    private readonly Button close;
    private bool working;
    private string error;

    internal LaunchWindow()
    {
        Text = "SENTRY FPGA / RK / ESP32 联合系统";
        StartPosition = FormStartPosition.CenterScreen;
        ClientSize = new Size(744, 478);
        MinimumSize = new Size(640, 420);
        Font = new Font("Microsoft YaHei UI", 10);
        BackColor = Color.FromArgb(244, 248, 246);

        var title = new Label { Text = "一键烧录 · 中文界面 · 联网检查", AutoSize = true,
            Location = new Point(24, 20), Font = new Font("Microsoft YaHei UI", 18, FontStyle.Bold) };
        status = new Label { Text = "正在准备…", AutoSize = true, Location = new Point(26, 67) };
        progress = new ProgressBar { Location = new Point(26, 98), Size = new Size(692, 12),
            Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right, Maximum = 6 };
        output = new TextBox { ReadOnly = true, Multiline = true, WordWrap = false, ScrollBars = ScrollBars.Both,
            BackColor = Color.White, ForeColor = Color.FromArgb(25, 46, 48),
            Location = new Point(26, 128), Size = new Size(692, 280),
            Anchor = AnchorStyles.Top | AnchorStyles.Bottom | AnchorStyles.Left | AnchorStyles.Right };
        close = new Button { Text = "关闭", Enabled = false, Location = new Point(616, 424),
            Size = new Size(102, 34), Anchor = AnchorStyles.Bottom | AnchorStyles.Right };
        close.Click += (sender, args) => Close();
        Controls.AddRange(new Control[] { title, status, progress, output, close });
        Shown += (sender, args) => Start();
        FormClosing += (sender, args) =>
        {
            if (working && args.CloseReason == CloseReason.UserClosing) args.Cancel = true;
        };
    }

    private async void Start()
    {
        working = true;
        int result = await Task.Run(() => Launcher.Run(false,
            line => BeginInvoke((Action)(() => ShowLine(line)))));
        working = false;
        close.Enabled = true;
        if (result != 0)
            status.Text = String.IsNullOrEmpty(error) ? "未完成。请查看下方日志。" : error;
    }

    private void ShowLine(string line)
    {
        output.AppendText(line + Environment.NewLine);
        Match stage = Regex.Match(line, @"^\[STAGE ([1-6])\] (.+)$");
        if (stage.Success)
        {
            progress.Value = Int32.Parse(stage.Groups[1].Value);
            status.Text = stage.Groups[2].Value;
        }
        if (line.StartsWith("[ERROR] ", StringComparison.Ordinal))
        {
            error = line.Substring(8);
            status.Text = error;
        }
    }
}
