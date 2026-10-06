"""Real mouse/keyboard -> Tauri ACL -> WebKit screenshot -> clipboard/save tests."""
import os,time,subprocess,json
from pathlib import Path
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Gdk
from PIL import Image
S=int(os.environ.get('GDK_SCALE','1'));OUT=Path(os.environ['SHOT_OUTPUT']);OUT.mkdir(parents=True,exist_ok=True)
def xd(*args):return subprocess.check_output(['xdotool',*map(str,args)],stderr=subprocess.DEVNULL,text=True).strip()
def pump():
    while Gtk.events_pending():Gtk.main_iteration_do(False)
def sleep(sec):
    deadline=time.monotonic()+sec
    while time.monotonic()<deadline:pump();time.sleep(.03)
def window(pattern,timeout=12):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        try:
            ids=xd('search','--onlyvisible','--name',pattern).splitlines()
            if ids:return ids[-1]
        except subprocess.CalledProcessError:pass
        sleep(.15)
    raise AssertionError('Missing window: '+pattern)
def geom(w):return {k:int(v) for k,v in (line.split('=') for line in xd('getwindowgeometry','--shell',w).splitlines()) if k in ['X','Y','WIDTH','HEIGHT']}
def shot(name):
    path=OUT/name;subprocess.run(['import','-window','root',str(path)],check=True);return Image.open(path).convert('RGB')
def key(k):xd('key','--clearmodifiers',k);sleep(.12)
def click(w,x,y):xd('mousemove','--window',w,int(x*S),int(y*S));xd('click',1);sleep(.2)
clipboard=Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
def clear_clip():clipboard.set_text('screenshot-e2e-sentinel',-1);pump();sleep(.1)
def await_png(name,timeout=22):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        pump();pix=clipboard.wait_for_image()
        if pix is not None:
            path=OUT/name;pix.savev(str(path),'png',[],[]);return Image.open(path).convert('RGB')
        sleep(.15)
    shot('failure.png');raise AssertionError('No clipboard PNG after real UI capture')
def count(im,c):return sum(all(abs(a-b)<10 for a,b in zip(px,c)) for px in im.getdata())
def open_chooser(main):
    xd('windowactivate','--sync',main);sleep(.3)
    g=geom(main);im=shot('before-open.png');pts=[]
    for y in range(g['Y']+5*S,g['Y']+50*S):
        for x in range(g['X']+g['WIDTH']//2,g['X']+g['WIDTH']-10*S):
            r,bg,b=im.getpixel((x,y))
            if r>180 and 65<bg<155 and b<90:pts.append((x,y))
    assert len(pts)>100,'Cannot find screenshot toolbar button'
    x=(min(p[0] for p in pts)+max(p[0] for p in pts))//2;y=(min(p[1] for p in pts)+max(p[1] for p in pts))//2
    xd('mousemove',x,y);xd('click',1);w=window('VibeZ · .*test 3');sleep(.7);return w
try:
    main=window('VibeZ 3 v3.0.2');sleep(4)
    for mode,tabs in [('visible',0),('full',1),('selection',2)]:
        dialog=open_chooser(main);shot('chooser.png');clear_clip()
        for _ in range(tabs):key('Tab')
        key('Return')
        if mode=='selection':
            sleep(.8);xd('mousemove','--window',main,224*S,178*S);xd('mousedown',1)
            xd('mousemove','--sync','--window',main,104*S,78*S);xd('mouseup',1)
        im=await_png(mode+'.png');dialog=window('VibeZ · .*test 3');sleep(.6);shot('preview-'+mode+'.png')
        assert count(im,(230,30,40))>5000,(mode,'red marker missing',im.size)
        blue=count(im,(30,60,230))
        if mode=='full':assert im.height>=1800 and blue>5000 and count(im,(0,200,180))>5000,('full page missing loaded bottom/sidebar',im.size,blue)
        else:assert blue<100,('offscreen pixels leaked',mode,blue)
        if mode=='selection':assert im.size==(120,100),im.size
        if mode=='visible':
            g=geom(main);assert abs(im.width-g['WIDTH']/S)<=2 and abs(im.height-(g['HEIGHT']/S-54))<=2,im.size
            assert count(im,(160,40,190))>5000,'Native canvas pixels missing with restrictive CSP'
            # Result focuses Copy. Tab reaches the real Save action and native chooser.
            key('Tab');key('Return');window('Screenshot opslaan|Save screenshot');sleep(.4)
            key('ctrl+l');xd('type','--clearmodifiers','--delay',1,str(OUT/'saved.png'));key('Return');sleep(.5)
            if not (OUT/'saved.png').exists():key('Return')
            end=time.monotonic()+6
            while not (OUT/'saved.png').exists() and time.monotonic()<end:sleep(.2)
            assert (OUT/'saved.png').exists(),'Native Save did not write PNG'
            saved=Image.open(OUT/'saved.png').convert('RGB');assert saved.size==im.size and saved.tobytes()==im.tobytes(),'Saved PNG differs from clipboard'
        key('Escape');sleep(.4)
        print('E2E_MODE_OK:',mode,im.size,'scale',S,flush=True)
    dialog=open_chooser(main);clear_clip();key('Tab');key('Tab');key('Return');sleep(.8);key('Escape')
    window('VibeZ · .*test 3');sleep(.5);assert clipboard.wait_for_image() is None,'Escape copied an unexpected screenshot'
    key('Return');im=await_png('after-cancel.png');assert im.width>120,'Chooser not reusable after Escape'
    print('SCREENSHOT_E2E_OK: real toolbar, 3 cards, 3 captures, restrictive CSP, canvas, native Save, Escape and retry; scale',S,flush=True)
except Exception:
    shot('failure.png');raise
