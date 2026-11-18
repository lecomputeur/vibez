"""Where the standalone UI checks place their test window: the native primary
monitor, the same screen the app itself opens on."""
import gi
gi.require_version('Gdk','3.0')
from gi.repository import Gdk

def safe_screen():
 display=Gdk.Display.get_default()
 if display is None:raise RuntimeError('No display for the test window')
 monitor=display.get_primary_monitor() or display.get_monitor(0)
 if monitor is None:raise RuntimeError('No monitor for the test window')
 g=monitor.get_geometry()
 return (g.x,g.y,g.width,g.height)
