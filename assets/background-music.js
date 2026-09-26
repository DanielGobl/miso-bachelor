'use strict';

function createBackgroundMusic({ preview, finaleBlocked }) {
  const STARTED_KEY = 'misos-bachelor-music-started-v1';
  const MUTED_KEY = 'misos-bachelor-music-muted-v1';
  const audio = document.getElementById('main-audio');
  const controls = document.getElementById('music-controls');
  const button = document.getElementById('music-mute');
  let started = false;
  let initializationStarted = false;
  let blocked = preview || finaleBlocked;
  let preparing = false;
  let pending = false;
  let playbackVersion = 0;
  let fadeTimer;
  let finishFade;

  try {
    // Existing started weekends also qualify, without requiring a new start tap.
    started = localStorage.getItem(STARTED_KEY) === 'true'
      || localStorage.getItem('misos-bachelor-onboarding-v1') === 'complete';
    audio.muted = localStorage.getItem(MUTED_KEY) === 'true';
  } catch { /* Keep session playback usable when storage is unavailable. */ }

  function updateControl() {
    controls.hidden = blocked || preparing;
    document.body.classList.toggle('normal-music', !controls.hidden);
    button.textContent = audio.muted ? '🔇' : '🔊';
    button.setAttribute('aria-label', audio.muted ? 'Zapnúť zvuk' : 'Stlmiť hudbu');
    button.setAttribute('aria-pressed', String(audio.muted));
  }

  function canPlay() { return started && !blocked && !preparing; }

  function tryPlay() {
    if (!canPlay() || pending || !audio.paused) return;
    pending = true;
    const version = playbackVersion;
    try {
      Promise.resolve(audio.play()).then(() => {
        if (!canPlay()) audio.pause();
      }).catch(() => {
        // Autoplay denial is expected: the next interaction retries silently.
      }).finally(() => {
        if (version === playbackVersion) pending = false;
      });
    } catch { pending = false; }
  }

  function cancelFade() {
    window.clearTimeout(fadeTimer);
    finishFade?.();
    finishFade = null;
  }

  function pause() {
    playbackVersion++;
    pending = false;
    audio.pause();
  }

  function prepareFinale() {
    cancelFade();
    preparing = true;
    updateControl();
    if (audio.paused || audio.muted) {
      pause();
      return Promise.resolve();
    }
    const initialVolume = audio.volume;
    const began = performance.now();
    return new Promise(resolve => {
      finishFade = resolve;
      function fade() {
        const fraction = Math.min(1, (performance.now() - began) / 250);
        audio.volume = initialVolume * (1 - fraction);
        if (fraction < 1) {
          fadeTimer = window.setTimeout(fade, 16);
        } else {
          pause();
          audio.volume = 1;
          finishFade = null;
          resolve();
        }
      }
      fade();
    });
  }

  function cancelFinale() {
    if (!preparing) return;
    cancelFade();
    preparing = false;
    audio.volume = 1;
    updateControl();
    tryPlay();
  }

  function stopForFinale() {
    blocked = true;
    preparing = false;
    cancelFade();
    pause();
    audio.volume = 1;
    updateControl();
  }

  button.addEventListener('click', () => {
    audio.muted = !audio.muted;
    try { localStorage.setItem(MUTED_KEY, String(audio.muted)); } catch { /* Session preference only. */ }
    updateControl();
    // Never seek or restart a playing song when changing mute.
    tryPlay();
  });
  audio.addEventListener('volumechange', updateControl);
  audio.addEventListener('playing', () => { if (!canPlay()) audio.pause(); });
  window.addEventListener('bachelor:started', () => {
    if (blocked || initializationStarted) return;
    initializationStarted = true;
    started = true;
    audio.currentTime = 0;
    try { localStorage.setItem(STARTED_KEY, 'true'); } catch { /* Session-only start. */ }
    tryPlay(); // Runs within the original start-button gesture.
  });
  window.addEventListener('bachelor:reset', () => {
    started = false;
    initializationStarted = false;
    blocked = preview;
    preparing = false;
    cancelFade();
    pause();
    audio.currentTime = 0;
    audio.volume = 1;
    if (!preview) {
      try { localStorage.removeItem(STARTED_KEY); } catch { /* Reset in memory. */ }
    }
    updateControl();
  });

  // Retries also cover returning to a suspended tab and back/forward navigation.
  // Bubble-phase click handling lets reset/finale handlers block playback first.
  document.addEventListener('click', tryPlay);
  document.addEventListener('keydown', tryPlay);
  document.addEventListener('touchend', tryPlay, { passive: true });
  window.addEventListener('pageshow', tryPlay);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) tryPlay(); });
  updateControl();
  tryPlay();
  return { prepareFinale, cancelFinale, stopForFinale };
}
