const { BrowserWindow, clipboard, desktopCapturer, dialog, ipcMain, screen } = require('electron');
const path = require('path');
const { t, uiBundle } = require('./i18n');

let hostWindow = null;
let vibeContents = null;
let overlayWindows = [];
let captures = new Map();
let captureInProgress = false;
let ipcRegistered = false;
let languageGetter = () => 'en';

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function currentLanguage() {
  try { return languageGetter() || 'en'; } catch (_) { return 'en'; }
}

function screenshotText(language) {
  return {
    noSource: t(language, 'noSource'),
    noDisplays: t(language, 'noDisplays'),
    failedTitle: t(language, 'shotFailed'),
    failedMessage: t(language, 'shotFailedMessage'),
  };
}

function getOrderedDisplays() {
  return screen.getAllDisplays().slice().sort((a, b) => {
    if (a.bounds.x !== b.bounds.x) return a.bounds.x - b.bounds.x;
    return a.bounds.y - b.bounds.y;
  });
}

function getCaptureOrderedDisplays() {
  const displays = getOrderedDisplays();
  const primaryId = String(screen.getPrimaryDisplay().id);
  const primary = displays.find((display) => String(display.id) === primaryId);
  const others = displays.filter((display) => String(display.id) !== primaryId);
  return primary ? [primary, ...others] : displays;
}

function restoreHost() {
  captureInProgress = false;
  if (!hostWindow || hostWindow.isDestroyed()) return;
  if (!hostWindow.isVisible()) hostWindow.show();
  if (hostWindow.isMinimized()) hostWindow.restore();
  hostWindow.focus();
}

function closeOverlays(restore = true) {
  const windows = overlayWindows.slice();
  overlayWindows = [];
  captures.clear();
  for (const win of windows) {
    if (!win || win.isDestroyed()) continue;
    win.removeAllListeners('closed');
    win.close();
  }
  if (restore) restoreHost();
}

async function getCaptureForDisplay(display, language) {
  const factor = display.scaleFactor || 1;
  const thumbnailSize = {
    width: Math.max(1, Math.round(display.bounds.width * factor)),
    height: Math.max(1, Math.round(display.bounds.height * factor)),
  };
  const sources = await desktopCapturer.getSources({ types: ['screen'], thumbnailSize, fetchWindowIcons: false });
  let source = sources.find((item) => String(item.display_id) === String(display.id));
  if (!source) {
    const captureOrder = getCaptureOrderedDisplays();
    const index = captureOrder.findIndex((item) => String(item.id) === String(display.id));
    if (index >= 0 && index < sources.length) source = sources[index];
  }
  if (!source || source.thumbnail.isEmpty()) throw new Error(screenshotText(language).noSource);
  return source.thumbnail;
}

async function createOverlay(display, image, language) {
  const overlay = new BrowserWindow({
    ...display.bounds,
    show: false,
    frame: false,
    resizable: false,
    movable: false,
    minimizable: false,
    maximizable: false,
    fullscreenable: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
    },
  });

  overlayWindows.push(overlay);
  captures.set(overlay.webContents.id, { display, image });
  overlay.on('closed', () => {
    overlayWindows = overlayWindows.filter((win) => win !== overlay);
    captures.delete(overlay.webContents.id);
    if (captureInProgress && overlayWindows.length === 0) restoreHost();
  });

  await overlay.loadFile(path.join(__dirname, 'screenshot-overlay.html'));
  const ui = uiBundle(language);
  await overlay.webContents.executeJavaScript(`
    window.__vibezSetScreenshotText?.(${JSON.stringify({
      language: ui.language,
      dir: ui.dir,
      title: t(language, 'selectShot'),
      hint: t(language, 'selectHint'),
    })});
    window.__vibezSetScreenshot(${JSON.stringify(image.toDataURL())});
  `);
  return overlay;
}

async function startScreenshot() {
  if (!hostWindow || hostWindow.isDestroyed() || !vibeContents || vibeContents.isDestroyed() || captureInProgress) return false;
  captureInProgress = true;
  let language = currentLanguage();

  try {
    const displays = getOrderedDisplays();
    if (!displays.length) throw new Error(screenshotText(language).noDisplays);
    await wait(80);

    const frozenDisplays = [];
    for (const display of displays) {
      frozenDisplays.push({ display, image: await getCaptureForDisplay(display, language) });
    }

    const overlays = [];
    for (const frozen of frozenDisplays) overlays.push(await createOverlay(frozen.display, frozen.image, language));
    for (const overlay of overlays) overlay.showInactive();

    const cursorDisplay = screen.getDisplayNearestPoint(screen.getCursorScreenPoint());
    const active = overlays.find((overlay) => {
      const capture = captures.get(overlay.webContents.id);
      return capture && String(capture.display.id) === String(cursorDisplay.id);
    }) || overlays[0];
    if (active && !active.isDestroyed()) active.focus();
    return true;
  } catch (error) {
    console.error('Screenshot failed:', error);
    closeOverlays(false);
    restoreHost();
    const text = screenshotText(language);
    await dialog.showMessageBox(hostWindow, {
      type: 'error',
      title: text.failedTitle,
      message: text.failedMessage,
      detail: error.message,
    });
    return false;
  }
}

function crop(capture, rect) {
  if (!capture || !rect) return null;
  const { image, display } = capture;
  const pixels = image.getSize();
  const sx = pixels.width / display.bounds.width;
  const sy = pixels.height / display.bounds.height;
  const x = Math.max(0, Math.round(Number(rect.x) * sx));
  const y = Math.max(0, Math.round(Number(rect.y) * sy));
  const width = Math.min(pixels.width - x, Math.max(1, Math.round(Number(rect.width) * sx)));
  const height = Math.min(pixels.height - y, Math.max(1, Math.round(Number(rect.height) * sy)));
  if (![x, y, width, height].every(Number.isFinite) || width < 2 || height < 2) return null;
  return image.crop({ x, y, width, height });
}

async function detectCodeMode() {
  if (!vibeContents || vibeContents.isDestroyed()) return false;
  try {
    return await vibeContents.executeJavaScript(`
      (() => {
        const active = [...document.querySelectorAll('[aria-current="page"],[aria-selected="true"],[data-state="active"],[data-active="true"]')]
          .map((el) => (el.textContent || '').trim().toLowerCase()).join(' ');
        const context = [location.pathname, document.title, active].join(' ').toLowerCase();
        return /(^|[\\s/_-])code($|[\\s/_-])/.test(context);
      })();
    `);
  } catch (_) {
    return false;
  }
}

async function focusComposer() {
  if (!vibeContents || vibeContents.isDestroyed()) return false;
  try {
    const result = await vibeContents.executeJavaScript(`
      (() => {
        const visible = (el) => {
          if (!el || !el.isConnected) return false;
          const r = el.getBoundingClientRect();
          const s = getComputedStyle(el);
          return r.width >= 80 && r.height >= 12 && s.display !== 'none' && s.visibility !== 'hidden';
        };
        const candidates = [...document.querySelectorAll('textarea,[contenteditable="true"],[role="textbox"]')]
          .filter(visible)
          .sort((a, b) => b.getBoundingClientRect().bottom - a.getBoundingClientRect().bottom);
        const editor = candidates[0];
        if (editor) {
          editor.focus({ preventScroll: true });
          return true;
        }
        const frame = [...document.querySelectorAll('iframe')].filter(visible)
          .sort((a, b) => (b.getBoundingClientRect().width * b.getBoundingClientRect().height) - (a.getBoundingClientRect().width * a.getBoundingClientRect().height))[0];
        if (frame) {
          frame.contentWindow?.focus();
          frame.focus({ preventScroll: true });
          return true;
        }
        return false;
      })();
    `);
    return Boolean(result);
  } catch (error) {
    console.error('Could not focus Vibe composer:', error);
    return false;
  }
}

async function attach(image) {
  if (!image || image.isEmpty() || !vibeContents || vibeContents.isDestroyed()) return;
  restoreHost();
  clipboard.writeImage(image);

  if (await detectCodeMode()) {
    await dialog.showMessageBox(hostWindow, {
      type: 'info',
      title: 'Use screenshot in Vibe Code',
      message: 'The screenshot is on your clipboard. Save it inside your project and reference that file in Vibe Code.',
      detail: 'This behaviour matches the VibeZ 1.x Code workflow. Direct image pasting remains available in Chat and Work.',
      buttons: ['OK'],
    });
    return;
  }

  await wait(140);
  await focusComposer();
  await wait(180);
  vibeContents.paste();
}

function registerIpc() {
  if (ipcRegistered) return;
  ipcRegistered = true;

  ipcMain.on('vibez:screenshot:start', (event) => {
    if (vibeContents && !vibeContents.isDestroyed() && event.sender.id === vibeContents.id) startScreenshot();
  });

  ipcMain.on('vibez:screenshot:finish', async (event, rect) => {
    const capture = captures.get(event.sender.id);
    if (!capture) return;
    const image = crop(capture, rect);
    closeOverlays(false);
    restoreHost();
    if (image && !image.isEmpty()) await attach(image);
  });

  ipcMain.on('vibez:screenshot:cancel', (event) => {
    if (captures.has(event.sender.id)) closeOverlays(true);
  });
}

function setupScreenshot(win, contents, getLanguage) {
  hostWindow = win;
  vibeContents = contents;
  if (typeof getLanguage === 'function') languageGetter = getLanguage;
  registerIpc();

  contents.on('before-input-event', (event, input) => {
    const modifier = process.platform === 'darwin' ? input.meta : input.control;
    if (modifier && input.shift && String(input.key || '').toLowerCase() === 's') {
      event.preventDefault();
      startScreenshot();
    }
  });

  return { startScreenshot };
}

module.exports = { setupScreenshot };
