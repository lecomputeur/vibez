"""Real two-output X11 regression: chooser placement, manual move, cancel, paste."""
import os, time, subprocess, json, base64, io
from pathlib import Path
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk
from PIL import Image
OUT = Path(os.environ['SHOT_OUTPUT'])
clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
def xd(*args):
    return subprocess.check_output(['xdotool', *map(str, args)], text=True, stderr=subprocess.DEVNULL).strip()
def sleep(seconds):
    end = time.monotonic()+seconds
    while time.monotonic() < end:
        while Gtk.events_pending(): Gtk.main_iteration_do(False)
        time.sleep(.025)
def window(pattern, timeout=12):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        try:
            ids=xd('search', '--onlyvisible', '--name', pattern).splitlines()
            if ids: return ids[-1]
        except subprocess.CalledProcessError: pass
        sleep(.1)
    raise AssertionError('Missing window: '+pattern)
def geom(w):
    return {k:int(v) for k,v in (line.split('=') for line in xd('getwindowgeometry','--shell',w).splitlines()) if k in ('X','Y','WIDTH','HEIGHT')}
def shot(name):
    subprocess.run(['import','-window','root',str(OUT/name)],check=True)
    return Image.open(OUT/name).convert('RGB')
def key(k):
    xd('key','--clearmodifiers',k);sleep(.15)
def click(w,x,y):
    xd('mousemove','--window',w,x,y);xd('click',1);sleep(.1)
def move_main(main,x):
    xd('windowsize','--sync',main,1000,720)
    xd('windowmove','--sync',main,x,80)
    xd('windowactivate','--sync',main);sleep(.6)
def open_chooser(main,other_x):
    g=geom(main);image=shot('before-open.png');orange=[]
    for y in range(g['Y']+5,g['Y']+50):
        for x in range(g['X']+g['WIDTH']//2,g['X']+g['WIDTH']-10):
            r,green,b=image.getpixel((x,y))
            if r>180 and 65<green<155 and b<90:orange.append((x,y))
    assert len(orange)>100, 'Screenshot toolbar button missing'
    x=(min(p[0] for p in orange)+max(p[0] for p in orange))//2
    y=(min(p[1] for p in orange)+max(p[1] for p in orange))//2
    # Move the pointer away too: this must be parent centering, not mouse placement.
    xd('mousemove',x,y,'click',1,'mousemove',other_x,50)
    dialog=window('VibeZ · .*');sleep(.65)
    return dialog

def check_monitor(main,dialog,label):
    m,d=geom(main),geom(dialog)
    side=0 if m['X']+m['WIDTH']//2<1280 else 1280
    assert d['X']>=side and d['X']+d['WIDTH']<=side+1280,(label,'chooser on wrong monitor',m,d)
    assert 0<=d['Y'] and d['Y']+d['HEIGHT']<=900,(label,'chooser off work area',d)
    assert abs((m['X']+m['WIDTH']/2)-(d['X']+d['WIDTH']/2))<45,(label,'not centered on VibeZ',m,d)
    assert d['WIDTH']<=282 and d['HEIGHT']<=202,(label,'compact size changed',d)
    shot(label+'.png')
    print('MONITOR_OK:',label,'parent',m,'chooser',d,flush=True)
    return d

def paste_events():
    try:return json.loads((OUT/'paste-events.json').read_text())
    except (FileNotFoundError,json.JSONDecodeError):return []

def captured_png():
    end=time.monotonic()+15
    while time.monotonic()<end:
        image=clipboard.wait_for_image()
        if image:
            path=OUT/'clipboard.png';image.savev(str(path),'png',[],[])
            return Image.open(path).convert('RGB')
        sleep(.1)
    raise AssertionError('Missing screenshot PNG')
try:
    display=Gdk.Display.get_default()
    assert display.get_n_monitors()==2, 'Test requires two distinct GDK monitors'
    monitors=[]
    for i in range(display.get_n_monitors()):
        r=display.get_monitor(i).get_geometry();monitors.append([r.x,r.y,r.width,r.height])
    (OUT/'gdk-monitors.json').write_text(json.dumps(monitors))
    assert sorted(r[0] for r in monitors)==[0,1280],monitors
    main=window('VibeZ 3 v3.0.3');sleep(4)
    # The previous generic center() opened on the primary (left) output here.
    move_main(main,1400);dialog=open_chooser(main,50)
    d=check_monitor(main,dialog,'right-nonprimary-first-open')
    # Relocation must remain under user control after opening, with no snap-back.
    xd('windowmove','--sync',dialog,d['X']+65,d['Y']+55);sleep(.35)
    relocated=geom(dialog);sleep(1.2)
    assert geom(dialog)==relocated,'Dialog snapped back after manual movement'
    assert relocated['X']>d['X']+40,('Manual relocation failed',d,relocated)
    key('Escape')
    move_main(main,100);dialog=open_chooser(main,2200)
    check_monitor(main,dialog,'left-after-moving-vibez');key('Escape')
    # The monitor is resolved again on reopening, not cached from the first run.
    move_main(main,1400);dialog=open_chooser(main,50)
    check_monitor(main,dialog,'right-after-moving-back')
    # Returning from a cancelled desktop capture must not reopen on the other output.
    clipboard.set_text('monitor-test-sentinel',-1);sleep(.1)
    click(dialog,150,123);window('^VibeZ screen selection$');sleep(.25);key('Escape')
    dialog=window('VibeZ · .*');sleep(.5)
    check_monitor(main,dialog,'right-after-cancel')
    assert clipboard.wait_for_image() is None and not paste_events(),'Cancel captured or pasted'
    # Real screenshot and automatic paste on the second monitor, with exact pixels.
    click(dialog,150,53);expected=captured_png()
    end=time.monotonic()+10
    while time.monotonic()<end:
        records=paste_events()
        if records and records[0].get('dataUrl'): break
        sleep(.1)
    assert len(records)==1,'Missing or duplicate automatic image paste'
    entry=records[0]
    assert entry['draft']=='Bestaande concepttekst' and entry['submits']==0,'Draft changed or submitted'
    got=Image.open(io.BytesIO(base64.b64decode(entry['dataUrl'].split(',',1)[1]))).convert('RGB')
    assert got.size==expected.size and got.tobytes()==expected.tobytes(),'Second-monitor paste pixels differ'
    got.save(OUT/'second-monitor-pasted.png');sleep(.4)
    assert len(paste_events())==1,'Duplicate image insertion'
    print('SECOND_MONITOR_PASTE_OK:',got.size,'exact PNG; draft retained; no send',flush=True)
    # Also reverse primary designation; the parent's output must still win.
    subprocess.run(['xrandr','--output','DUMMY1','--primary'],check=True)
    sleep(.3);move_main(main,100);dialog=open_chooser(main,2200)
    check_monitor(main,dialog,'left-nonprimary-after-primary-switch');key('Escape')
    print('TWO_MONITOR_OK: initial placement; move/reopen; opposite pointer; manual relocation; cancellation; automatic image paste; switched primary',flush=True)
except Exception:
    shot('failure.png')
    raise
