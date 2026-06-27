/**
 * main.js — Three.js application entry point.
 *
 * Sets up the renderer, scene, camera, controls, and animation loop.
 * Connects to the FastAPI WebSocket and delegates events to EventHandler.
 */

import * as THREE from 'three';
import { OrbitControls }   from 'three/addons/controls/OrbitControls.js';
import { CSS2DRenderer }   from 'three/addons/renderers/CSS2DRenderer.js';
import { AGENT_CONFIGS, CharacterManager } from './characters.js';
import { buildOffice, setOfficeActive, drawTickerScrolling, drawTickerSignal } from './office.js';
import { EventHandler } from './events.js';
import { DialogBox }    from './dialog.js';

// ─── Renderer ────────────────────────────────────────────────────────────────

const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.shadowMap.enabled = false;
document.body.insertBefore(renderer.domElement, document.getElementById('label-layer'));

// CSS2D label renderer (overlays the WebGL canvas)
const labelRenderer = new CSS2DRenderer();
labelRenderer.setSize(window.innerWidth, window.innerHeight);
const labelLayer = labelRenderer.domElement;
labelLayer.id = 'label-layer';
labelLayer.style.position = 'fixed';
labelLayer.style.top      = '0';
labelLayer.style.left     = '0';
labelLayer.style.pointerEvents = 'none';
document.getElementById('label-layer').replaceWith(labelLayer);

// ─── Scene ───────────────────────────────────────────────────────────────────

const scene = new THREE.Scene();
scene.background = new THREE.Color(0xf0f0ee);
scene.fog = new THREE.Fog(0xf0f0ee, 45, 95);

// ─── Camera ──────────────────────────────────────────────────────────────────

const camera = new THREE.PerspectiveCamera(48, window.innerWidth / window.innerHeight, 0.1, 100);
camera.position.set(0, 16, 24);
camera.lookAt(0, 1, 0);

// ─── Orbit Controls ──────────────────────────────────────────────────────────

const controls = new OrbitControls(camera, renderer.domElement);
controls.target.set(0, 1, 0);
controls.enableDamping   = true;
controls.dampingFactor   = 0.06;
controls.maxPolarAngle   = Math.PI / 2.05;
controls.minDistance     = 4;
controls.maxDistance     = 45;
controls.mouseButtons    = {
  LEFT: THREE.MOUSE.ROTATE,
  MIDDLE: THREE.MOUSE.DOLLY,
  RIGHT: THREE.MOUSE.PAN,
};

// ─── Build Office & Characters ────────────────────────────────────────────────

const officeState  = buildOffice(scene, AGENT_CONFIGS);
const charManager  = new CharacterManager(scene);

// Start in the lit/active state so the office is always visible on load.
// (The dark "out-of-hours" idle look was designed for the old dark background.)
setOfficeActive(officeState, true);
charManager.showAll();

// ─── Application State ────────────────────────────────────────────────────────

let isActive    = false;
let isComplete  = false;
let tickerSymbol = '';
let tickerOffset = 0;

// ─── Dialog box ───────────────────────────────────────────────────────────────

const dialogBox = new DialogBox(document.getElementById('dialog-box'));

// ─── UI helpers ───────────────────────────────────────────────────────────────

const statusText  = document.getElementById('status-text');
const tickerBadge = document.getElementById('ticker-badge');

function setStatus(text)  { statusText.textContent  = text; }
function setTicker(text, color = '#4fc3f7') {
  tickerBadge.textContent = text;
  tickerBadge.style.color = color;
}

// ─── Event handler callbacks ──────────────────────────────────────────────────

const eventHandler = new EventHandler(officeState, charManager, {
  onIdle() {
    isActive   = false;
    isComplete = false;
    setOfficeActive(officeState, false);
    setStatus('Out of hours — waiting for analysis to start');
    setTicker('');
    dialogBox.reset();
  },
  onStart(ticker) {
    tickerSymbol = ticker;
    isActive     = true;
    isComplete   = false;
    tickerOffset = 0;
    setOfficeActive(officeState, true);
    charManager.showAll();
    setStatus(`Analysing ${ticker}…`);
    setTicker(ticker);
    dialogBox.reset();
  },
  onComplete(signal, ticker) {
    isComplete = true;
    drawTickerSignal(officeState, signal);

    const sig = (signal || '').toUpperCase();
    const display =
      ['BUY',  'OVERWEIGHT' ].includes(sig) ? 'BUY'  :
      ['SELL', 'UNDERWEIGHT'].includes(sig) ? 'SELL' : 'HOLD';

    const colorMap = { BUY: '#00ff41', SELL: '#ff2525', HOLD: '#ffcc00' };
    const colour   = colorMap[display] || '#aaa';

    setStatus(`Analysis complete — ${ticker}`);
    setTicker(`${display}  ·  ${ticker}`, colour);
  },
  onAgentActive(agentName)          { dialogBox.onAgentActive(agentName); },
  onAgentIdle(agentName)            { dialogBox.onAgentIdle(agentName); },
  onAgentMessage(agentName, text)   { dialogBox.onAgentMessage(agentName, text); },
});

// ─── WebSocket ────────────────────────────────────────────────────────────────

function connectWS() {
  const ws = new WebSocket(`ws://${window.location.host}/ws`);

  ws.onopen = () => {
    document.getElementById('loading').classList.add('hidden');
  };

  ws.onmessage = (e) => {
    try {
      eventHandler.handle(JSON.parse(e.data));
    } catch (_) { /* ignore malformed messages */ }
  };

  ws.onclose = () => {
    setStatus('Disconnected — reload to reconnect');
    // Auto-reconnect after 3 s
    setTimeout(connectWS, 3000);
  };
}

connectWS();

// ─── Animation Loop ───────────────────────────────────────────────────────────

const clock = new THREE.Clock();

function animate() {
  requestAnimationFrame(animate);
  const delta = clock.getDelta();

  controls.update();
  charManager.update(delta);

  // Scroll the ticker display while analysis is running
  if (isActive && !isComplete && tickerSymbol) {
    tickerOffset += delta * 85;
    drawTickerScrolling(officeState, tickerSymbol, tickerOffset);
  }

  renderer.render(scene, camera);
  labelRenderer.render(scene, camera);
}

// ─── Window resize ────────────────────────────────────────────────────────────

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
  labelRenderer.setSize(window.innerWidth, window.innerHeight);
});

animate();
