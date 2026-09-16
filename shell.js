const back = document.getElementById('back');
const forward = document.getElementById('forward');
const reload = document.getElementById('reload');
const screenshot = document.getElementById('screenshot');
const settings = document.getElementById('settings');
const screenshotLabel = document.getElementById('screenshot-label');
const settingsLabel = document.getElementById('settings-label');
const loadingLine = document.getElementById('loading-line');

function applyState(state = {}) {
  back.disabled = !state.canGoBack;
  forward.disabled = !state.canGoForward;
  screenshot.hidden = state.showScreenshotButton === false;
  loadingLine.classList.toggle('active', Boolean(state.loading));

  if (state.ui?.screenshot) {
    screenshotLabel.textContent = state.ui.screenshot;
    screenshot.setAttribute('aria-label', state.ui.screenshot);
    screenshot.title = state.shortcut ? `${state.ui.screenshot} (${state.shortcut})` : state.ui.screenshot;
  }
  if (state.ui?.settings) {
    settingsLabel.textContent = state.ui.settings;
    settings.setAttribute('aria-label', state.ui.settings);
    settings.title = state.ui.settings;
  }

  document.documentElement.dir = state.dir || 'ltr';
  document.documentElement.lang = state.language || 'en';
}

back.addEventListener('click', () => window.vibezShell.action('back'));
forward.addEventListener('click', () => window.vibezShell.action('forward'));
reload.addEventListener('click', () => window.vibezShell.action('reload'));
screenshot.addEventListener('click', () => window.vibezShell.action('screenshot'));
settings.addEventListener('click', () => window.vibezShell.action('settings'));

window.vibezShell.onState(applyState);
window.vibezShell.getState().then(applyState).catch(() => {});
