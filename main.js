const {
  app,
  BrowserWindow,
  Menu,
  Tray,
  globalShortcut,
  ipcMain,
  shell,
  dialog,
  clipboard,
  nativeImage,
  session,
  systemPreferences,
} = require('electron');
const { autoUpdater } = require('electron-updater');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { setupScreenshot } = require('./screenshot');
const { createSettingsStore } = require('./settings-store');
const { resolveLanguage, t, uiBundle } = require('./i18n');
const { ACCOUNT_WORDS } = require('./ui-detection');

const REPO_URL = 'https://github.com/lecomputeur/vibez';
const RELEASES_URL = `${REPO_URL}/releases/latest`;
const VIBE_URL = 'https://vibe.mistral.ai/';
const APP_PROTOCOL = 'vibez';
const SCREENSHOT_BUTTON_LAYOUT = Object.freeze({
  minWidth: 146,
  maxWidth: 228,
  height: 48,
  gap: 10,
  fallbackRightOffset: 330,
  fallbackTop: 5,
  edgePadding: 8,
  maxTopBand: 90,
  minMainWidth: 620,
});

if (process.argv.includes('--version')) {
  console.log(require('./package.json').version);
  process.exit(0);
}

app.setName('VibeZ');

const settingsStore = createSettingsStore(path.join(app.getPath('userData'), 'settings.json'));
let settings = settingsStore.read();

if (settings.hardwareAcceleration === 'disabled') {
  app.disableHardwareAcceleration();
} else if (settings.hardwareAcceleration === 'enabled') {
  app.commandLine.appendSwitch('ignore-gpu-blocklist');
  app.commandLine.appendSwitch('enable-gpu-rasterization');
}

if (process.platform === 'linux' && settings.displayBackend === 'wayland') {
  app.commandLine.appendSwitch('enable-features', 'UseOzonePlatform');
  app.commandLine.appendSwitch('ozone-platform', 'wayland');
} else if (process.platform === 'linux' && settings.displayBackend === 'x11') {
  app.commandLine.appendSwitch('ozone-platform', 'x11');
}

let mainWindow = null;
let settingsWindow = null;
let screenshotButtonWindow = null;
let screenshotButtonNativeReady = false;
let tray = null;
let isQuitting = false;
let manualUpdateCheck = false;
let updaterHandlersInstalled = false;
let initialActionHandled = false;

function selectedLanguage() {
  const osLocale = app.isReady()
    ? app.getLocale()
    : (process.env.LC_ALL || process.env.LC_MESSAGES || process.env.LANG || 'en');
  return resolveLanguage(settings.language, osLocale);
}

function currentUiBundle() {
  return uiBundle(selectedLanguage());
}

function uiText() {
  return currentUiBundle().strings;
}

function windowTitle() {
  return `VibeZ v${app.getVersion()}`;
}

function showMessageBox(options, parent = settingsWindow || mainWindow) {
  const win = parent && !parent.isDestroyed?.() ? parent : null;
  return win ? dialog.showMessageBox(win, options) : dialog.showMessageBox(options);
}

function isTrustedMistralUrl(value) {
  try {
    const url = new URL(value);
    const host = url.hostname.toLowerCase();
    return url.protocol === 'https:' && (host === 'mistral.ai' || host.endsWith('.mistral.ai'));
  } catch (_) {
    return false;
  }
}

function isSafeExternalUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' || url.protocol === 'http:';
  } catch (_) {
    return false;
  }
}

function ensureMainVisible() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  if (mainWindow.isMinimized()) mainWindow.restore();
  if (!mainWindow.isVisible()) mainWindow.show();
  mainWindow.focus();
}

function isTransientWebUiError(error) {
  const message = String(error?.message || error || '').toLowerCase();
  return !mainWindow ||
    mainWindow.isDestroyed() ||
    mainWindow.webContents.isDestroyed() ||
    mainWindow.webContents.isLoadingMainFrame() ||
    message.includes('object has been destroyed') ||
    message.includes('execution context was destroyed') ||
    message.includes('frame was disposed') ||
    message.includes('navigat');
}

function warnWebUiError(context, error) {
  if (!isTransientWebUiError(error)) console.warn(`[VibeZ] ${context}:`, error);
}

async function positionScreenshotButton() {
  if (!mainWindow || mainWindow.isDestroyed() || !screenshotButtonWindow || screenshotButtonWindow.isDestroyed()) return;
  const bounds = mainWindow.getContentBounds();
  const buttonBounds = screenshotButtonWindow.getBounds();
  const width = Math.max(SCREENSHOT_BUTTON_LAYOUT.minWidth, buttonBounds.width || SCREENSHOT_BUTTON_LAYOUT.minWidth);
  const height = SCREENSHOT_BUTTON_LAYOUT.height;
  const gap = SCREENSHOT_BUTTON_LAYOUT.gap;
  let x = Math.round(bounds.x + bounds.width - SCREENSHOT_BUTTON_LAYOUT.fallbackRightOffset);
  let y = Math.round(bounds.y + SCREENSHOT_BUTTON_LAYOUT.fallbackTop);

  try {
    const anchor = await mainWindow.webContents.executeJavaScript(`
      (() => {
        const visible = (el) => {
          if (!el || !el.isConnected) return false;
          const r = el.getBoundingClientRect();
          const s = getComputedStyle(el);
          return r.width > 18 && r.height > 18 && r.top >= 0 && r.top < 120 && s.display !== 'none' && s.visibility !== 'hidden';
        };
        const textOf = (el) => [el.innerText, el.textContent, el.getAttribute('aria-label'), el.getAttribute('title')]
          .filter(Boolean).join(' ').replace(/\s+/g, ' ').trim().toLowerCase();
        const accountWords = ${JSON.stringify(ACCOUNT_WORDS)};
        const nodes = [...document.querySelectorAll('button,a,[role="button"]')]
          .filter(visible)
          .map((el) => ({ el, text: textOf(el), rect: el.getBoundingClientRect() }))
          .filter((item) => item.rect.left > window.innerWidth * 0.55);
        const accountMatches = nodes.filter((item) => accountWords.some((word) => item.text === word || item.text.includes(word)));
        if (accountMatches.length) {
          const left = Math.min(...accountMatches.map((item) => item.rect.left));
          const top = Math.min(...accountMatches.map((item) => item.rect.top));
          const bottom = Math.max(...accountMatches.map((item) => item.rect.bottom));
          return { left, top, width: 0, height: bottom - top };
        }
        const match = nodes
          .filter((item) => item.rect.width >= 55 && item.rect.width <= 240)
          .sort((a, b) => b.rect.right - a.rect.right)[0];
        if (!match) return null;
        const r = match.rect;
        return { left: r.left, top: r.top, width: r.width, height: r.height };
      })()
    `);
    if (anchor && Number.isFinite(anchor.left)) {
      x = Math.round(bounds.x + anchor.left - width - gap);
      y = Math.round(bounds.y + anchor.top + (anchor.height - height) / 2);
    }
  } catch (error) {
    warnWebUiError('Could not position Screenshot button', error);
  }

  const minX = bounds.x + SCREENSHOT_BUTTON_LAYOUT.edgePadding;
  const maxX = bounds.x + bounds.width - width - SCREENSHOT_BUTTON_LAYOUT.edgePadding;
  const minY = bounds.y + 2;
  const maxY = bounds.y + Math.min(SCREENSHOT_BUTTON_LAYOUT.maxTopBand, bounds.height - height - 2);
  x = Math.max(minX, Math.min(maxX, x));
  y = Math.max(minY, Math.min(maxY, y));
  screenshotButtonWindow.setBounds({ x, y, width, height }, false);
}

function shouldShowScreenshotButton() {
  return Boolean(
    settings.showScreenshotButton &&
    screenshotButtonNativeReady &&
    mainWindow &&
    !mainWindow.isDestroyed() &&
    mainWindow.isVisible() &&
    mainWindow.isFocused() &&
    !mainWindow.isMinimized() &&
    mainWindow.getBounds().width >= SCREENSHOT_BUTTON_LAYOUT.minMainWidth
  );
}

function refreshScreenshotButtonVisibility() {
  if (!screenshotButtonWindow || screenshotButtonWindow.isDestroyed()) return;
  if (shouldShowScreenshotButton()) {
    positionScreenshotButton();
    screenshotButtonWindow.showInactive();
  } else {
    screenshotButtonWindow.hide();
  }
}

async function suppressInjectedScreenshotButton() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  if (!screenshotButtonNativeReady && settings.showScreenshotButton) return;
  try {
    await mainWindow.webContents.insertCSS('#vibez-screenshot-button{display:none !important;visibility:hidden !important;pointer-events:none !important;}');
  } catch (error) {
    warnWebUiError('Could not suppress injected Screenshot button', error);
  }
}

async function syncNativeScreenshotButtonText() {
  if (!screenshotButtonWindow || screenshotButtonWindow.isDestroyed()) return;
  const ui = currentUiBundle();
  const shortcut = String(settings.screenshotShortcut || '')
    .replace('CommandOrControl', process.platform === 'darwin' ? 'Cmd' : 'Ctrl')
    .replace('Super', process.platform === 'darwin' ? 'Cmd' : 'Super');
  try {
    const desiredWidth = await screenshotButtonWindow.webContents.executeJavaScript(`
      window.__vibezSetUi?.(${JSON.stringify({ language: ui.language, dir: ui.dir, label: ui.strings.screenshot, shortcut })}) || ${SCREENSHOT_BUTTON_LAYOUT.minWidth}
    `);
    const bounds = screenshotButtonWindow.getBounds();
    const width = Math.max(SCREENSHOT_BUTTON_LAYOUT.minWidth, Math.min(SCREENSHOT_BUTTON_LAYOUT.maxWidth, Number(desiredWidth) || SCREENSHOT_BUTTON_LAYOUT.minWidth));
    if (bounds.width !== width) screenshotButtonWindow.setBounds({ ...bounds, width }, false);
    await positionScreenshotButton();
  } catch (error) {
    console.error('Could not localize Screenshot button:', error);
  }
}

async function triggerScreenshot() {
  if (!mainWindow || mainWindow.isDestroyed()) return false;

  if (process.platform === 'darwin' && typeof systemPreferences.getMediaAccessStatus === 'function') {
    const status = systemPreferences.getMediaAccessStatus('screen');
    if (status === 'denied' || status === 'restricted') {
      ensureMainVisible();
      const text = uiText();
      const result = await showMessageBox({
        type: 'warning',
        title: `VibeZ · ${text.shotFailed}`,
        message: text.shotFailedMessage,
        detail: 'macOS requires Screen & System Audio Recording (Screen Recording) permission for screenshots. Enable VibeZ in System Settings → Privacy & Security, then try again.',
        buttons: [text.settings, text.close],
        defaultId: 0,
        cancelId: 1,
      });
      if (result.response === 0) {
        shell.openExternal('x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture').catch((error) => console.warn('Could not open macOS Screen Recording settings:', error));
      }
      return false;
    }
  }

  ensureMainVisible();
  screenshotButtonWindow?.hide();

  if (mainWindow.webContents.isLoadingMainFrame()) {
    mainWindow.webContents.once('did-finish-load', () => setTimeout(triggerScreenshot, 120));
    return true;
  }

  try {
    const triggered = await mainWindow.webContents.executeJavaScript(`
      (() => {
        if (!window.vibez || typeof window.vibez.captureScreenshot !== 'function') return false;
        window.vibez.captureScreenshot();
        return true;
      })();
    `);
    if (!triggered) throw new Error('Screenshot bridge is not ready.');
    return true;
  } catch (error) {
    console.error('Could not start screenshot:', error);
    refreshScreenshotButtonVisibility();
    const text = uiText();
    await showMessageBox({
      type: 'error',
      title: `VibeZ · ${text.screenshot}`,
      message: text.shotStartError,
      detail: error.message,
    });
    return false;
  }
}

function createScreenshotButtonWindow() {
  if (!mainWindow || mainWindow.isDestroyed() || screenshotButtonWindow) return;

  screenshotButtonWindow = new BrowserWindow({
    width: SCREENSHOT_BUTTON_LAYOUT.minWidth,
    height: SCREENSHOT_BUTTON_LAYOUT.height,
    show: false,
    frame: false,
    transparent: true,
    resizable: false,
    movable: false,
    minimizable: false,
    maximizable: false,
    fullscreenable: false,
    skipTaskbar: true,
    hasShadow: false,
    alwaysOnTop: true,
    focusable: false,
    parent: mainWindow,
    webPreferences: {
      preload: path.join(__dirname, 'native-button-preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
    },
  });

  screenshotButtonWindow.setMenuBarVisibility(false);
  screenshotButtonWindow.loadFile(path.join(__dirname, 'screenshot-button.html')).then(async () => {
    screenshotButtonNativeReady = true;
    await syncNativeScreenshotButtonText();
    suppressInjectedScreenshotButton();
    refreshScreenshotButtonVisibility();
  }).catch((error) => {
    console.error('Native Screenshot button failed to load; keeping web fallback:', error);
    screenshotButtonNativeReady = false;
    screenshotButtonWindow?.destroy();
    screenshotButtonWindow = null;
  });

  screenshotButtonWindow.on('closed', () => {
    screenshotButtonWindow = null;
    screenshotButtonNativeReady = false;
  });
}

function setupContextMenu() {
  mainWindow.webContents.on('context-menu', (event, params) => {
    event.preventDefault();
    const selection = params.selectionText?.trim();
    const template = [];
    const text = uiText();

    if (params.isEditable) {
      template.push(
        { label: text.paste, click: () => mainWindow?.webContents.paste(), accelerator: 'Ctrl+V' },
        { label: text.copy, role: 'copy', enabled: Boolean(selection) },
        { label: text.cut, role: 'cut', enabled: Boolean(selection) },
        { label: text.selectAll, role: 'selectAll' },
      );
    } else if (selection) {
      template.push({ label: text.copy, role: 'copy' });
    }

    if (selection) {
      if (template.length) template.push({ type: 'separator' });
      template.push(
        { label: text.searchGoogle, click: () => shell.openExternal(`https://www.google.com/search?q=${encodeURIComponent(selection)}`) },
        { label: text.searchDuck, click: () => shell.openExternal(`https://duckduckgo.com/?q=${encodeURIComponent(selection)}`) },
      );
    }

    if (!template.length) {
      template.push(
        { label: text.screenshot, click: triggerScreenshot },
        { label: text.settings, click: openSettings },
      );
    }

    Menu.buildFromTemplate(template).popup({ window: mainWindow, x: params.x, y: params.y });
  });
}

function setupNavigationSecurity(win) {
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (isTrustedMistralUrl(url)) {
      return {
        action: 'allow',
        overrideBrowserWindowOptions: {
          autoHideMenuBar: true,
          webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
            sandbox: true,
          },
        },
      };
    }

    if (isSafeExternalUrl(url) && settings.openExternalLinks) {
      shell.openExternal(url);
      return { action: 'deny' };
    }

    return isSafeExternalUrl(url)
      ? { action: 'allow', overrideBrowserWindowOptions: { autoHideMenuBar: true, webPreferences: { nodeIntegration: false, contextIsolation: true, sandbox: true } } }
      : { action: 'deny' };
  });

  win.webContents.on('will-navigate', (event, url) => {
    try {
      const protocol = new URL(url).protocol;
      if (protocol !== 'https:' && protocol !== 'http:') event.preventDefault();
    } catch (_) {
      event.preventDefault();
    }
  });
}

function updateBrowserLanguage(win) {
  if (!win || win.isDestroyed()) return;
  rebuildTray();
  buildApplicationMenu();
  syncNativeScreenshotButtonText();
}

function applyZoom() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  try { mainWindow.webContents.setZoomFactor(settings.zoomFactor); } catch (error) { warnWebUiError('Could not apply zoom', error); }
}

function registerGlobalScreenshot() {
  globalShortcut.unregisterAll();
  if (!settings.globalScreenshot) return true;
  try {
    return globalShortcut.register(settings.screenshotShortcut, triggerScreenshot);
  } catch (error) {
    console.error('Could not register global screenshot shortcut:', error);
    return false;
  }
}

function autostartCommand() {
  if (process.env.FLATPAK_ID) return `flatpak run ${process.env.FLATPAK_ID} --hidden`;
  const executable = process.env.APPIMAGE || process.execPath;
  return `"${String(executable).replace(/"/g, '\\"')}" --hidden`;
}

function syncAutostart(enabled) {
  if (!app.isPackaged) return true;
  try {
    if (process.platform === 'win32') {
      app.setLoginItemSettings({
        openAtLogin: Boolean(enabled),
        path: process.execPath,
        args: ['--hidden'],
      });
      return app.getLoginItemSettings().openAtLogin === Boolean(enabled);
    }

    if (process.platform === 'darwin') {
      app.setLoginItemSettings({
        openAtLogin: Boolean(enabled),
        openAsHidden: true,
      });
      return app.getLoginItemSettings().openAtLogin === Boolean(enabled);
    }

    const dir = path.join(os.homedir(), '.config', 'autostart');
    const file = path.join(dir, 'vibez.desktop');
    if (!enabled) {
      try { fs.unlinkSync(file); } catch (error) { if (error.code !== 'ENOENT') throw error; }
      return true;
    }
    fs.mkdirSync(dir, { recursive: true });
    const desktop = [
      '[Desktop Entry]',
      'Type=Application',
      'Name=VibeZ',
      `Comment=${uiText().desktopClient}`,
      `Exec=${autostartCommand()}`,
      'Terminal=false',
      'X-GNOME-Autostart-enabled=true',
      '',
    ].join('\n');
    fs.writeFileSync(file, desktop, 'utf8');
    return true;
  } catch (error) {
    console.error('Could not update autostart:', error);
    return false;
  }
}

function createMainWindow() {
  if (mainWindow && !mainWindow.isDestroyed()) return mainWindow;

  const startHidden = process.argv.includes('--hidden');
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 720,
    minHeight: 520,
    show: !startHidden,
    autoHideMenuBar: true,
    backgroundColor: '#111216',
    title: windowTitle(),
    icon: path.join(__dirname, 'icon.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      spellcheck: true,
    },
  });

  mainWindow.webContents.on('before-input-event', (_event, input) => {
    if (input.control && input.shift && String(input.key || '').toLowerCase() === 's') screenshotButtonWindow?.hide();
  });

  setupScreenshot(mainWindow, selectedLanguage);
  setupContextMenu();
  setupNavigationSecurity(mainWindow);
  createScreenshotButtonWindow();

  mainWindow.webContents.on('did-finish-load', () => {
    updateBrowserLanguage(mainWindow);
    applyZoom();
    suppressInjectedScreenshotButton();
    if (!initialActionHandled) {
      initialActionHandled = true;
      setTimeout(() => handleCommandLine(process.argv), 180);
    }
  });
  mainWindow.webContents.on('did-navigate-in-page', () => {
    updateBrowserLanguage(mainWindow);
    suppressInjectedScreenshotButton();
  });
  mainWindow.webContents.on('page-title-updated', (event) => {
    event.preventDefault();
    mainWindow?.setTitle(windowTitle());
  });

  mainWindow.on('move', positionScreenshotButton);
  mainWindow.on('resize', refreshScreenshotButtonVisibility);
  mainWindow.on('maximize', () => setTimeout(refreshScreenshotButtonVisibility, 40));
  mainWindow.on('unmaximize', () => setTimeout(refreshScreenshotButtonVisibility, 40));
  mainWindow.on('show', refreshScreenshotButtonVisibility);
  mainWindow.on('focus', () => setTimeout(refreshScreenshotButtonVisibility, 100));
  mainWindow.on('blur', () => screenshotButtonWindow?.hide());
  mainWindow.on('hide', () => screenshotButtonWindow?.hide());
  mainWindow.on('minimize', (event) => {
    screenshotButtonWindow?.hide();
    if (settings.minimizeToTray) {
      event.preventDefault();
      mainWindow.hide();
    }
  });
  mainWindow.on('close', (event) => {
    if (!isQuitting && settings.closeToTray) {
      event.preventDefault();
      mainWindow.hide();
    }
  });
  mainWindow.on('closed', () => {
    screenshotButtonWindow?.destroy();
    screenshotButtonWindow = null;
    mainWindow = null;
  });

  mainWindow.loadURL(VIBE_URL);
  return mainWindow;
}

function buildApplicationMenu() {
  const text = uiText();
  const template = [
    {
      label: 'VibeZ',
      submenu: [
        { label: text.screenshot, accelerator: 'CommandOrControl+Shift+S', click: triggerScreenshot },
        { label: text.settings, accelerator: 'CommandOrControl+,', click: openSettings },
        { label: text.updates, click: () => checkForUpdates(true) },
        { label: text.about, click: showAbout },
        { type: 'separator' },
        { label: text.quit, accelerator: 'CommandOrControl+Q', click: quitApp },
      ],
    },
    { role: 'editMenu' },
    { role: 'viewMenu' },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

function trayTemplate() {
  const text = uiText();
  return [
    { label: text.open, click: ensureMainVisible },
    { label: text.screenshot, click: triggerScreenshot },
    { type: 'separator' },
    { label: text.settings, click: openSettings },
    { label: text.updates, click: () => checkForUpdates(true) },
    { label: text.about, click: showAbout },
    { type: 'separator' },
    { label: text.quit, click: quitApp },
  ];
}

function createTray() {
  if (tray) return;
  try {
    let image = nativeImage.createFromPath(path.join(__dirname, 'icon.png'));
    if (!image.isEmpty()) image = image.resize({ width: 22, height: 22 });
    tray = new Tray(image);
    tray.setToolTip(windowTitle());
    tray.on('click', ensureMainVisible);
    rebuildTray();
  } catch (error) {
    console.error('Could not create system tray icon:', error);
    tray = null;
  }
}

function rebuildTray() {
  if (!tray) return;
  tray.setContextMenu(Menu.buildFromTemplate(trayTemplate()));
  tray.setToolTip(windowTitle());
}

function quitApp() {
  isQuitting = true;
  app.quit();
}

function operatingSystemName() {
  if (process.platform === 'win32') return `Windows ${os.release()}`;
  if (process.platform === 'darwin') return `macOS ${os.release()}`;
  try {
    const text = fs.readFileSync('/etc/os-release', 'utf8');
    const match = text.match(/^PRETTY_NAME=(.*)$/m);
    return match ? match[1].replace(/^"|"$/g, '') : `Linux ${os.release()}`;
  } catch (_) {
    return `Linux ${os.release()}`;
  }
}

function systemInfoText() {
  const lines = [
    `VibeZ: ${app.getVersion()}`,
    `Electron: ${process.versions.electron}`,
    `Chromium: ${process.versions.chrome}`,
    `Node.js: ${process.versions.node}`,
    `OS: ${operatingSystemName()}`,
    `OS version: ${typeof os.version === 'function' ? os.version() : os.release()}`,
    `Architecture: ${process.arch}`,
    `Platform: ${process.platform}`,
    `Hardware acceleration setting: ${settings.hardwareAcceleration}`,
  ];

  if (process.platform === 'linux') {
    lines.push(
      `Session: ${process.env.XDG_SESSION_TYPE || 'unknown'}`,
      `Desktop: ${process.env.XDG_CURRENT_DESKTOP || 'unknown'}`,
      `Display backend setting: ${settings.displayBackend}`,
      `Flatpak: ${process.env.FLATPAK_ID || 'no'}`,
      `AppImage: ${process.env.APPIMAGE ? 'yes' : 'no'}`,
    );
  }

  if (process.platform === 'darwin' && typeof systemPreferences.getMediaAccessStatus === 'function') {
    lines.push(`Screen recording permission: ${systemPreferences.getMediaAccessStatus('screen')}`);
  }

  return lines.join('\n');
}

async function showAbout() {
  const text = uiText();
  const result = await showMessageBox({
    type: 'info',
    title: `${text.about} · ${windowTitle()}`,
    message: windowTitle(),
    detail: `${text.desktopClient}\n\n${systemInfoText()}`,
    buttons: [text.copySystem, 'GitHub', text.reportProblem, text.close],
    defaultId: 3,
    cancelId: 3,
  });
  if (result.response === 0) clipboard.writeText(systemInfoText());
  if (result.response === 1) shell.openExternal(REPO_URL);
  if (result.response === 2) shell.openExternal(`${REPO_URL}/issues/new`);
  return true;
}

function openSettings() {
  if (settingsWindow && !settingsWindow.isDestroyed()) {
    settingsWindow.show();
    settingsWindow.focus();
    return;
  }
  settingsWindow = new BrowserWindow({
    width: 820,
    height: 760,
    minWidth: 700,
    minHeight: 560,
    parent: mainWindow || undefined,
    title: uiText().settingsTitle,
    autoHideMenuBar: true,
    backgroundColor: '#111216',
    icon: path.join(__dirname, 'icon.png'),
    webPreferences: {
      preload: path.join(__dirname, 'settings-preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
    },
  });
  settingsWindow.setMenuBarVisibility(false);
  settingsWindow.loadFile(path.join(__dirname, 'settings.html'));
  settingsWindow.on('closed', () => { settingsWindow = null; });
}

function validSettingsSender(event) {
  return Boolean(settingsWindow && !settingsWindow.isDestroyed() && event.sender.id === settingsWindow.webContents.id);
}

function installIpcHandlers() {
  ipcMain.on('vibez:native-screenshot', (event) => {
    if (screenshotButtonWindow && !screenshotButtonWindow.isDestroyed() && event.sender.id === screenshotButtonWindow.webContents.id) triggerScreenshot();
  });

  ipcMain.handle('vibez:settings:get', (event) => {
    if (!validSettingsSender(event)) throw new Error('Unauthorized settings request.');
    return { settings, ui: currentUiBundle(), platform: process.platform };
  });

  ipcMain.handle('vibez:settings:save', async (event, patch) => {
    if (!validSettingsSender(event)) throw new Error('Unauthorized settings request.');
    const previous = settings;
    settings = settingsStore.patch(patch);
    const displayBackendChanged = process.platform === 'linux' && previous.displayBackend !== settings.displayBackend;
    const restartRequired = previous.hardwareAcceleration !== settings.hardwareAcceleration || displayBackendChanged || previous.language !== settings.language;
    const shortcutRegistered = registerGlobalScreenshot();
    const autostartApplied = syncAutostart(settings.startAtLogin);
    applyZoom();
    autoUpdater.autoInstallOnAppQuit = Boolean(settings.installUpdatesOnQuit);
    refreshScreenshotButtonVisibility();
    suppressInjectedScreenshotButton();
    rebuildTray();
    buildApplicationMenu();
    await syncNativeScreenshotButtonText();
    return { settings, ui: currentUiBundle(), platform: process.platform, restartRequired, shortcutRegistered, autostartApplied };
  });

  ipcMain.handle('vibez:updates:check', (event) => {
    if (!validSettingsSender(event)) throw new Error('Unauthorized update request.');
    checkForUpdates(true);
    return true;
  });

  ipcMain.handle('vibez:about:show', (event) => {
    if (!validSettingsSender(event)) throw new Error('Unauthorized about request.');
    return showAbout();
  });

  ipcMain.handle('vibez:data:reset', async (event) => {
    if (!validSettingsSender(event)) throw new Error('Unauthorized data request.');
    const targetSession = mainWindow?.webContents.session || session.defaultSession;
    await targetSession.clearCache();
    await targetSession.clearStorageData();
    mainWindow?.reload();
    return true;
  });

  ipcMain.handle('vibez:external:open', (event, url) => {
    if (!validSettingsSender(event) || !isSafeExternalUrl(url)) throw new Error('Invalid external URL.');
    shell.openExternal(url);
    return true;
  });

  ipcMain.on('vibez:settings:close', (event) => {
    if (validSettingsSender(event)) settingsWindow?.close();
  });
}

function installUpdaterHandlers() {
  if (updaterHandlersInstalled) return;
  updaterHandlersInstalled = true;
  autoUpdater.autoDownload = true;
  autoUpdater.autoInstallOnAppQuit = Boolean(settings.installUpdatesOnQuit);

  autoUpdater.on('update-available', (info) => console.log(`VibeZ update available: ${info.version}`));
  autoUpdater.on('update-not-available', () => {
    if (!manualUpdateCheck) return;
    manualUpdateCheck = false;
    const text = uiText();
    showMessageBox({ type: 'info', title: `VibeZ · ${text.updates}`, message: text.latest });
  });
  autoUpdater.on('error', (error) => {
    console.error('VibeZ updater error:', error);
    if (!manualUpdateCheck) return;
    manualUpdateCheck = false;
    const text = uiText();
    showMessageBox({ type: 'error', title: `VibeZ · ${text.updates}`, message: text.updateFailed, detail: error.message });
  });
  autoUpdater.on('update-downloaded', async (info) => {
    manualUpdateCheck = false;
    const text = uiText();
    const result = await showMessageBox({
      type: 'info',
      title: text.updateReady,
      message: t(selectedLanguage(), 'readyInstall', { version: info.version }),
      buttons: [text.restartUpdate, text.later],
      defaultId: 0,
      cancelId: 1,
    });
    if (result.response === 0) {
      isQuitting = true;
      autoUpdater.quitAndInstall(false, true);
    }
  });
}

function checkForUpdates(manual = false) {
  manualUpdateCheck = Boolean(manual);
  const text = uiText();
  if (!app.isPackaged) {
    if (manual) showMessageBox({ type: 'info', title: `VibeZ · ${text.updates}`, message: text.installedOnly });
    return;
  }
  if (process.env.FLATPAK_ID) {
    if (manual) showMessageBox({ type: 'info', title: `VibeZ · ${text.updates}`, message: text.flatpakBuild, buttons: [text.openReleases, text.close], defaultId: 0 }).then((result) => { if (result.response === 0) shell.openExternal(RELEASES_URL); });
    return;
  }
  installUpdaterHandlers();
  autoUpdater.checkForUpdates().catch((error) => console.error('Update check failed:', error));
}

function configureSessionSecurity() {
  const ses = session.defaultSession;
  ses.setPermissionCheckHandler((_webContents, _permission, requestingOrigin) => isTrustedMistralUrl(requestingOrigin));
  ses.setPermissionRequestHandler((webContents, _permission, callback, details) => {
    callback(isTrustedMistralUrl(details.requestingUrl || webContents.getURL()));
  });
}

function commandAction(argv) {
  const args = Array.isArray(argv) ? argv : [];
  if (args.includes('--screenshot')) return 'screenshot';
  if (args.includes('--settings')) return 'settings';
  const protocolUrl = args.find((arg) => typeof arg === 'string' && arg.startsWith(`${APP_PROTOCOL}://`));
  if (protocolUrl) {
    try {
      const parsed = new URL(protocolUrl);
      const action = `${parsed.hostname}${parsed.pathname}`.replace(/^\/+|\/+$/g, '').toLowerCase();
      if (action.startsWith('screenshot')) return 'screenshot';
      if (action.startsWith('settings')) return 'settings';
    } catch (_) {}
  }
  return 'open';
}

function handleCommandLine(argv) {
  const action = commandAction(argv);
  if (action === 'screenshot') triggerScreenshot();
  else if (action === 'settings') openSettings();
  else if (!(Array.isArray(argv) && argv.includes('--hidden'))) ensureMainVisible();
}

const gotSingleInstanceLock = app.requestSingleInstanceLock();
if (!gotSingleInstanceLock) {
  app.quit();
} else {
  app.on('second-instance', (_event, commandLine) => handleCommandLine(commandLine));
}

app.on('open-url', (event, url) => {
  event.preventDefault();
  handleCommandLine([url]);
});

app.whenReady().then(() => {
  if (!gotSingleInstanceLock) return;
  if (app.isPackaged) {
    try { app.setAsDefaultProtocolClient(APP_PROTOCOL); } catch (error) { console.error('Could not register vibez:// protocol:', error); }
  }
  configureSessionSecurity();
  installIpcHandlers();
  createMainWindow();
  createTray();
  buildApplicationMenu();
  registerGlobalScreenshot();
  syncAutostart(settings.startAtLogin);

  if (app.isPackaged) {
    installUpdaterHandlers();
    if (settings.autoUpdates && !process.env.FLATPAK_ID) checkForUpdates(false);
  }
});

app.on('before-quit', () => { isQuitting = true; });
app.on('will-quit', () => globalShortcut.unregisterAll());
app.on('window-all-closed', () => {
  if (process.platform === 'darwin' && !isQuitting) return;
  if (isQuitting || !settings.closeToTray) {
    isQuitting = true;
    app.quit();
  }
});
app.on('activate', () => {
  if (!mainWindow || mainWindow.isDestroyed()) createMainWindow();
  ensureMainVisible();
});
