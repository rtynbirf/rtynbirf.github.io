/* Волна ×3 · W3-E · Киоск-контур: карта клавиш + Media Session + гистерезис автопаузы.
 * Переносимый кусок: любой плеер роя копирует файл и подключает
 * `<script src="wave3/keyboard-map.js"></script>`. Чужие файлы сайта не затрагиваются.
 * Экспортирует window.KioskKeyboard = { KEY_MAP, MEDIA_ACTIONS, HYST, on, has,
 * dispatchKey, attachMediaSession, autopause }. */
(function (global) {
  'use strict';

  // Таблица key→action (критерий 1: каждая клавиша — ровно один обработчик).
  var KEY_MAP = {
    'Space':      { action: 'toggle' },
    'KeyK':       { action: 'toggle' },
    'KeyJ':       { action: 'seekBy', arg: -10 },
    'KeyL':       { action: 'seekBy', arg: 10 },
    'ArrowLeft':  { action: 'seekBy', arg: -5 },
    'ArrowRight': { action: 'seekBy', arg: 5 },
    'ArrowUp':    { action: 'volumeBy', arg: 0.05 },
    'ArrowDown':  { action: 'volumeBy', arg: -0.05 },
    'KeyM':       { action: 'mute' },
    'KeyF':       { action: 'fullscreen' }
  };
  // Цифры 0-9 — переход к соответствующему проценту длительности.
  (function () {
    for (var i = 0; i <= 9; i++) KEY_MAP['Digit' + i] = { action: 'seekPercent', arg: i * 10 };
  })();

  // 7 обязательных действий Media Session (критерий 1).
  var MEDIA_ACTIONS = ['play', 'pause', 'stop', 'previoustrack', 'nexttrack', 'seekforward', 'seekbackward'];

  var HANDLERS = {}; // action → функция; ровно одна на действие.
  function on(action, fn) { HANDLERS[action] = fn; }
  function has(action) { return typeof HANDLERS[action] === 'function'; }

  // Диспетчер: находит ровно одну привязку по event.code и вызывает её.
  // Возвращает true, если клавиша обработана. Модификаторы и поля ввода не перехватываются.
  function dispatchKey(event, player) {
    if (event.ctrlKey || event.altKey || event.metaKey) return false;
    var tag = ((event.target && event.target.tagName) || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select') return false;
    var bind = KEY_MAP[event.code];
    if (!bind) return false;
    var fn = HANDLERS[bind.action];
    if (!fn) return false;
    fn(player, bind.arg);
    return true;
  }

  // Слой 1: navigator.mediaSession — метаданные плейлиста и хендлеры аппаратных клавиш.
  function attachMediaSession(player, item) {
    if (typeof navigator === 'undefined' || !('mediaSession' in navigator)) return false;
    try {
      if (typeof window.MediaMetadata === 'function') {
        navigator.mediaSession.metadata = new window.MediaMetadata({
          title: (item && item.title) || '',
          artist: (item && item.artist) || '',
          album: (item && item.album) || '',
          artwork: (item && item.artwork) || []
        });
      }
      var actions = {
        play: function () { player.play(); },
        pause: function () { player.pause(); },
        stop: function () { player.pause(); player.currentTime = 0; },
        previoustrack: function () { player.currentTime = 0; },
        nexttrack: function () { player.currentTime = player.duration || 0; },
        seekforward: function (d) { player.currentTime = Math.min(player.duration || 0, player.currentTime + ((d && d.seekOffset) || 10)); },
        seekbackward: function (d) { player.currentTime = Math.max(0, player.currentTime - ((d && d.seekOffset) || 10)); }
      };
      MEDIA_ACTIONS.forEach(function (name) {
        try { navigator.mediaSession.setActionHandler(name, actions[name]); }
        catch (e) { /* действие не поддержано браузером — не ошибка прибора */ }
      });
      return true;
    } catch (e) { return false; }
  }

  // Слой автопаузы: два порога + окно 800 мс; явный скачок — мгновенно (≤400 мс).
  var HYST = { quietEnter: 0.10, quietExit: 0.18, windowMs: 800, jumpBand: 0.08, maxLatencyMs: 400 };
  // state = { playing: bool, candidateSince: number|null }; level — уровень сигнала 0..1; nowMs — мс.
  // Возвращает 'pause' | 'play' | 'none'. «Дребезг» у порога исключён: переключение
  // происходит только если сигнал непрерывно за порогом ≥ windowMs либо ушёл за jumpBand.
  function autopause(state, level, nowMs) {
    var playing = state.playing;
    var beyond = playing ? (level < HYST.quietEnter) : (level > HYST.quietExit);
    var hard = playing ? (level < HYST.quietEnter - HYST.jumpBand) : (level > HYST.quietExit + HYST.jumpBand);
    if (!beyond) { state.candidateSince = null; return 'none'; }
    if (state.candidateSince === null) state.candidateSince = nowMs;
    if (hard || (nowMs - state.candidateSince) >= HYST.windowMs) {
      state.playing = !playing;
      state.candidateSince = null;
      return state.playing ? 'play' : 'pause';
    }
    return 'none';
  }

  global.KioskKeyboard = {
    KEY_MAP: KEY_MAP, MEDIA_ACTIONS: MEDIA_ACTIONS, HYST: HYST,
    on: on, has: has, dispatchKey: dispatchKey,
    attachMediaSession: attachMediaSession, autopause: autopause
  };
})(typeof window !== 'undefined' ? window : globalThis);
