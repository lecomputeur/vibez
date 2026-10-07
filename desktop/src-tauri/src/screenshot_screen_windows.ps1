$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type -ReferencedAssemblies System.Windows.Forms,System.Drawing -TypeDefinition @'
using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Runtime.InteropServices;
using System.Windows.Forms;
public sealed class VibeZScreenSelection : Form {
    [DllImport("user32.dll")] static extern IntPtr SetThreadDpiAwarenessContext(IntPtr value);
    readonly Bitmap frozen;
    readonly Timer expiry = new Timer();
    Point start, end;
    bool selecting;
    string result = "CANCEL";
    VibeZScreenSelection(Rectangle screen, Bitmap pixels) {
        frozen = pixels;
        FormBorderStyle = FormBorderStyle.None;
        StartPosition = FormStartPosition.Manual;
        Bounds = screen;
        TopMost = true;
        ShowInTaskbar = false;
        KeyPreview = true;
        DoubleBuffered = true;
        Cursor = Cursors.Cross;
        BackColor = Color.Black;
        expiry.Interval = 120000;
        expiry.Tick += delegate { Close(); };
        Shown += delegate { Activate(); Focus(); expiry.Start(); };
        KeyDown += delegate(object sender, KeyEventArgs e) { if (e.KeyCode == Keys.Escape) Close(); };
        MouseDown += delegate(object sender, MouseEventArgs e) {
            if (e.Button == MouseButtons.Right) { Close(); return; }
            if (e.Button != MouseButtons.Left) return;
            selecting = true; start = end = e.Location; Capture = true; Invalidate();
        };
        MouseMove += delegate(object sender, MouseEventArgs e) { if (selecting) { end = e.Location; Invalidate(); } };
        MouseUp += delegate(object sender, MouseEventArgs e) {
            if (!selecting || e.Button != MouseButtons.Left) return;
            end = e.Location; Capture = false;
            Rectangle rect = Rectangle.Intersect(Selection(), new Rectangle(Point.Empty, frozen.Size));
            if (rect.Width >= 4 && rect.Height >= 4) {
                using (Bitmap crop = frozen.Clone(rect, PixelFormat.Format32bppArgb))
                using (MemoryStream stream = new MemoryStream()) {
                    crop.Save(stream, ImageFormat.Png);
                    if (stream.Length > 24 * 1024 * 1024) throw new InvalidOperationException("Screenshot is too large");
                    result = Convert.ToBase64String(stream.ToArray());
                }
            }
            Close();
        };
    }
    Rectangle Selection() { return Rectangle.FromLTRB(Math.Min(start.X,end.X),Math.Min(start.Y,end.Y),Math.Max(start.X,end.X),Math.Max(start.Y,end.Y)); }
    protected override void OnPaint(PaintEventArgs e) {
        e.Graphics.DrawImageUnscaled(frozen, 0, 0);
        using (Brush shade = new SolidBrush(Color.FromArgb(72, Color.Black))) e.Graphics.FillRectangle(shade, ClientRectangle);
        if (!selecting) return;
        Rectangle rect = Rectangle.Intersect(Selection(), new Rectangle(Point.Empty, frozen.Size));
        if (rect.Width == 0 || rect.Height == 0) return;
        e.Graphics.DrawImage(frozen, rect, rect, GraphicsUnit.Pixel);
        using (Pen border = new Pen(Color.FromArgb(255,107,53), 2)) e.Graphics.DrawRectangle(border,rect);
    }
    protected override void Dispose(bool disposing) { if (disposing) { expiry.Dispose(); } base.Dispose(disposing); }
    public static string Select() {
        // Use physical screen coordinates, including negative monitor origins.
        try { SetThreadDpiAwarenessContext(new IntPtr(-4)); } catch (EntryPointNotFoundException) { }
        Rectangle screen = SystemInformation.VirtualScreen;
        if (screen.Width < 1 || screen.Height < 1 || (long)screen.Width * screen.Height > 36000000)
            throw new InvalidOperationException("Combined desktop exceeds screenshot pixel limit");
        using (Bitmap pixels = new Bitmap(screen.Width,screen.Height,PixelFormat.Format32bppArgb)) {
            using (Graphics g = Graphics.FromImage(pixels)) g.CopyFromScreen(screen.Location,Point.Empty,screen.Size,CopyPixelOperation.SourceCopy);
            using (VibeZScreenSelection window = new VibeZScreenSelection(screen,pixels)) {
                Application.Run(window);
                return window.result;
            }
        }
    }
}
'@
[Console]::Write([VibeZScreenSelection]::Select())
