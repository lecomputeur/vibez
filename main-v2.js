const {
  app,
  BrowserWindow,
  WebContentsView,
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
const { setupScreenshot } = require('./screenshot-v2');
const { createSettingsStore } = require('./settings-store');
const { resolveLanguage, t, uiBundle } = require('./i18n');

const REPO_URL = 'https://github.com/lecomputeur/vibez';
const RELEASES_URL = `${REPO_URL}/releases/latest`;
const MICROSOFT_STORE_URL = 'https://apps.microsoft.com/detail/9NR7L2G4MS08';
const VIBE_URL = 'https://vibe.mistral.ai/';
const APP_PROTOCOL = 'vibez';
const LATEST_RELEASE_API = 'https://api.github.com/repos/lecomputeur/vibez/releases/latest';
const TOOLBAR_HEIGHT = 54;

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
let vibeView = null;
let settingsWindow = null;
let tray = null;
let screenshotController = null;
let isQuitting = false;
let manualUpdateCheck = false;
let updaterHandlersInstalled = false;
let initialActionHandled = false;
let vibeLoading = false;

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

function vibeContents() {
  if (!vibeView || vibeView.webContents.isDestroyed()) return null;
  return vibeView.webContents;
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

function compareVersions(left, right) {
  const parse = (value) => String(value || '')
    .replace(/^v/i, '')
    .split('-')[0]
    .split('.')
    .map((part) => Number.parseInt(part, 10) || 0);
  const a = parse(left);
  const b = parse(right);
  const length = Math.max(a.length, b.length, 3);
  for (let index = 0; index < length; index += 1) {
    const av = a[index] || 0;
    const bv = b[index] || 0;
    if (av !== bv) return av > bv ? 1 : -1;
  }
  return 0;
}

async function fetchLatestRelease() {
  const response = await fetch(LATEST_RELEASE_API, {
    headers: {
      Accept: 'application/vnd.github+json',
      'User-Agent': `VibeZ/${app.getVersion()}`,
    },
  });
  if (!response.ok) throw new Error(`GitHub update check failed (HTTP ${response.status}).`);
  const release = await response.json();
  const version = String(release.tag_name || release.name || '').replace(/^v/i, '').trim();
  if (!version) throw new Error('GitHub release response did not contain a version.');
  return {
    version,
    url: isSafeExternalUrl(release.html_url) ? release.html_url : RELEASES_URL,
  };
}

async function checkMacUpdates(manual = false) {
  const text = uiText();
  try {
    const latest = await fetchLatestRelease();
    if (compareVersions(latest.version, app.getVersion()) > 0) {
      const result = await showMessageBox({
        type: 'info',
        title: `VibeZ · ${text.updates}`,
        message: `${text.updateReady} — VibeZ ${latest.version}`,
        buttons: [text.openReleases, text.later],
        defaultId: 0,
        cancelId: 1,
      });
      if (result.response === 0) await shell.openExternal(latest.url);
      return true;
    }
    if (manual) {
      await showMessageBox({ type: 'info', title: `VibeZ · ${text.updates}`, message: text.latest });
    }
    return false;
  } catch (error) {
    console.error('macOS update check failed:', error);
    if (manual) {
      await showMessageBox({
        type: 'error',
        title: `VibeZ · ${text.updates}`,
        message: text.updateFailed,
        detail: error.message,
      });
    }
    return false;
  }
}

function ensureMainVisible() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  if (mainWindow.isMinimized()) mainWindow.restore();
  if (!mainWindow.isVisible()) mainWindow.show();
  mainWindow.focus();
}

function navigationHistory() {
  return vibeContents()?.navigationHistory || null;
}

function shellState() {
  const ui = currentUiBundle();
  const history = navigationHistory();
  const shortcut = String(settings.screenshotShortcut || '')
    .replace('CommandOrControl', process.platform === 'darwin' ? 'Cmd' : 'Ctrl')
    .replace('Super', process.platform === 'darwin' ? 'Cmd' : 'Super');
  return {
    canGoBack: Boolean(history?.canGoBack()),
    canGoForward: Boolean(history?.canGoForward()),
    loading: vibeLoading,
    showScreenshotButton: settings.showScreenshotButton,
    shortcut,
    language: ui.language,
    dir: ui.dir,
    ui: {
      screenshot: ui.strings.screenshot,
      settings: ui.strings.settings,
    },
  };
}

function sendShellState() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  mainWindow.webContents.send('vibez:shell:state', shellState());
}

function layoutVibeView() {
  if (!mainWindow || mainWindow.isDestroyed() || !vibeView) return;
  const bounds = mainWindow.getContentBounds();
  vibeView.setBounds({
    x: 0,
    y: TOOLBAR_HEIGHT,
    width: Math.max(1, bounds.width),
    height: Math.max(1, bounds.height - TOOLBAR_HEIGHT),
  });
}

function applyZoom() {
  const contents = vibeContents();
  if (!contents) return;
  try { contents.setZoomFactor(settings.zoomFactor); } catch (error) { console.warn('Could not apply Vibe zoom:', error); }
}

async function triggerScreenshot() {
  if (!mainWindow || mainWindow.isDestroyed() || !screenshotController) return false;

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
        shell.openExternal('x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture')
          .catch((error) => console.warn('Could not open macOS Screen Recording settings:', error));
      }
      return false;
    }
  }

  ensureMainVisible();
  return screenshotController.startScreenshot();
}

function setupContextMenu(contents) {
  contents.on('context-menu', (event, params) => {
    event.preventDefault();
    const selection = params.selectionText?.trim();
    const template = [];
    const text = uiText();

    if (params.isEditable) {
      template.push(
        { label: text.paste, click: () => contents.paste(), accelerator: 'Ctrl+V' },
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

    Menu.buildFromTemplate(template).popup({
      window: mainWindow,
      x: params.x,
      y: params.y + TOOLBAR_HEIGHT,
    });
  });
}

function setupNavigationSecurity(contents) {
  contents.setWindowOpenHandler(({ url }) => {
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
      ? {
          action: 'allow',
          overrideBrowserWindowOptions: {
            autoHideMenuBar: true,
            webPreferences: { nodeIntegration: false, contextIsolation: true, sandbox: true },
          },
        }
      : { action: 'deny' };
  });

  contents.on('will-navigate', (event, url) => {
    try {
      const protocol = new URL(url).protocol;
      if (protocol !== 'https:' && protocol !== 'http:') event.preventDefault();
    } catch (_) {
      event.preventDefault();
    }
  });
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
      app.setLoginItemSettings({ openAtLogin: Boolean(enabled), path: process.execPath, args: ['--hidden'] });
      return app.getLoginItemSettings().openAtLogin === Boolean(enabled);
    }
    if (process.platform === 'darwin') {
      app.setLoginItemSettings({ openAtLogin: Boolean(enabled), openAsHidden: true });
      return app.getLoginItemSettings().openAtLogin === Boolean(enabled);
    }

    const dir = path.join(os.homedir(), '.config', 'autostart');
    const file = path.join(dir, 'vibez.desktop');
    if (!enabled) {
      try { fs.unlinkSync(file); } catch (error) { if (error.code !== 'ENOENT') throw error; }
      return true;
    }
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(file, [
      '[Desktop Entry]',
      'Type=Application',
      'Name=VibeZ',
      `Comment=${uiText().desktopClient}`,
      `Exec=${autostartCommand()}`,
      'Terminal=false',
      'X-GNOME-Autostart-enabled=true',
      '',
    ].join('\n'), 'utf8');
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
    width: 1280,
    height: 840,
    minWidth: 760,
    minHeight: 560,
    show: !startHidden,
    autoHideMenuBar: true,
    backgroundColor: '#111216',
    title: windowTitle(),
    icon: path.join(__dirname, 'icon.png'),
    webPreferences: {
      preload: path.join(__dirname, 'shell-preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
    },
  });
  mainWindow.setMenuBarVisibility(false);

  vibeView = new WebContentsView({
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      spellcheck: true,
    },
  });
  mainWindow.contentView.addChildView(vibeView);
  layoutVibeView();

  const contents = vibeView.webContents;
  screenshotController = setupScreenshot(mainWindow, contents, selectedLanguage);
  setupContextMenu(contents);
  setupNavigationSecurity(contents);

  contents.on('did-start-loading', () => { vibeLoading = true; sendShellState(); });
  contents.on('did-stop-loading', () => { vibeLoading = false; sendShellState(); });
  contents.on('did-finish-load', () => {
    applyZoom();
    sendShellState();
    rebuildTray();
    buildApplicationMenu();
    if (!initialActionHandled) {
      initialActionHandled = true;
      setTimeout(() => handleCommandLine(process.argv), 180);
    }
  });
  contents.on('did-navigate', sendShellState);
  contents.on('did-navigate-in-page', sendShellState);
  contents.on('page-title-updated', () => sendShellState());

  mainWindow.on('resize', layoutVibeView);
  mainWindow.on('show', sendShellState);
  mainWindow.on('focus', sendShellState);
  mainWindow.on('minimize', (event) => {
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
    try { vibeView?.webContents.close(); } catch (_) {}
    vibeView = null;
    screenshotController = null;
    mainWindow = null;
  });

  mainWindow.loadFile(path.join(__dirname, 'shell.html')).then(sendShellState);
  contents.loadURL(VIBE_URL);
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
    `Architecture: ${process.arch}`,
    `Platform: ${process.platform}`,
    `Hardware acceleration setting: ${settings.hardwareAcceleration}`,
  ];
  if (process.platform === 'linux') {
    lines.push(
      `Session: ${process.env.XDG_SESSION_TYPE || 'unknown'}`,
      `Desktop: ${process.env.XDG_CURRENT_DESKTOP || 'unknown'}`,
      `Display backend setting: ${settings.displayBackend}`,
    );
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
    buttons: [text.copySystem, 'GitHub', text.close],
    defaultId: 2,
    cancelId: 2,
  });
  if (result.response === 0) clipboard.writeText(systemInfoText());
  if (result.response === 1) shell.openExternal(REPO_URL);
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

function validShellSender(event) {
  return Boolean(mainWindow && !mainWindow.isDestroyed() && event.sender.id === mainWindow.webContents.id);
}

function doShellAction(action) {
  const contents = vibeContents();
  const history = navigationHistory();
  if (action === 'back' && history?.canGoBack()) history.goBack();
  else if (action === 'forward' && history?.canGoForward()) history.goForward();
  else if (action === 'reload') contents?.reload();
  else if (action === 'screenshot') triggerScreenshot();
  else if (action === 'settings') openSettings();
}

function installIpcHandlers() {
  ipcMain.handle('vibez:shell:get-state', (event) => {
    if (!validShellSender(event)) throw new Error('Unauthorized shell request.');
    return shellState();
  });

  ipcMain.on('vibez:shell:action', (event, action) => {
    if (!validShellSender(event)) return;
    doShellAction(action);
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
    if (process.platform !== 'darwin') autoUpdater.autoInstallOnAppQuit = Boolean(settings.installUpdatesOnQuit);
    rebuildTray();
    buildApplicationMenu();
    sendShellState();
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
    const contents = vibeContents();
    const targetSession = contents?.session || session.defaultSession;
    await targetSession.clearCache();
    await targetSession.clearStorageData();
    contents?.reload();
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
  if (process.windowsStore) {
    if (manual) shell.openExternal(MICROSOFT_STORE_URL);
    return;
  }
  if (process.env.FLATPAK_ID) {
    if (manual) showMessageBox({ type: 'info', title: `VibeZ · ${text.updates}`, message: text.flatpakBuild, buttons: [text.openReleases, text.close], defaultId: 0 }).then((result) => { if (result.response === 0) shell.openExternal(RELEASES_URL); });
    return;
  }
  if (process.platform === 'darwin') {
    void checkMacUpdates(manual);
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
    if (process.platform !== 'darwin') installUpdaterHandlers();
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
