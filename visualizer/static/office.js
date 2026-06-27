/**
 * office.js — builds the static trading-floor environment.
 *
 * Floor plan (z axis, ticker wall at z=-15, open camera side at z=+15):
 *
 *   z ≈ -15        Ticker / LED display wall  (front of office)
 *   z ≈ -13 to -11 Lounge: water cooler, coffee station, plants
 *   z ≈  -9        Analyst desks (4 agents)
 *   z ≈ -6 to -0.5 Meeting room: 4-wall glass enclosure, oval table, researchers
 *   z ≈   3        Trading desk row: Trader + 4 NPC desks
 *   z ≈   7        Risk management desks (3 agents)
 *   z ≈ 10–15      Portfolio Manager glass corner office (all 4 walls)
 *
 * Exports:
 *   buildOffice(scene, agentConfigs) -> officeState
 *   setOfficeActive(officeState, active)
 *   drawTickerScrolling(officeState, ticker, offset)
 *   drawTickerSignal(officeState, signal)
 */

import * as THREE from 'three';

const FLOOR_W = 32;
const FLOOR_D = 30;
const WALL_H  = 10;

// ─── Public API ─────────────────────────────────────────────────────────────

export function buildOffice(scene, agentConfigs) {
  const state = {
    ambientLight:  null,
    sunLight:      null,
    pointLights:   [],
    lightPanels:   [],
    monitorScreens:[],
    tickerCtx:     null,
    tickerCanvas:  null,
    tickerTexture: null,
  };

  _buildFloor(scene);
  _buildWalls(scene);
  _buildCeiling(scene, state);
  _buildTickerDisplay(scene, state);
  try { _buildCompanySign(scene); } catch (e) { console.warn('Company sign skipped:', e); }
  _buildLounge(scene);
  _buildMeetingRoom(scene);
  _buildDesks(scene, agentConfigs, state);
  _buildNPCTradingDesks(scene, state);
  _buildPMOffice(scene, state);
  _buildLighting(scene, agentConfigs, state);

  return state;
}

export function setOfficeActive(state, active) {
  if (active) {
    state.ambientLight.color.set(0x8899cc);
    state.ambientLight.intensity = 0.65;
    state.sunLight.intensity     = 0.55;
    state.lightPanels.forEach(p => {
      p.material.emissive.set(0xfff8e8);
      p.material.emissiveIntensity = 1.0;
    });
    state.pointLights.forEach(pl => { pl.intensity = 1.4; });
    state.monitorScreens.forEach(m => {
      m.material.emissive.set(0x002800);
      m.material.emissiveIntensity = 1.0;
    });
  } else {
    state.ambientLight.color.set(0x7788aa);
    state.ambientLight.intensity = 0.45;
    state.sunLight.intensity     = 0;
    state.lightPanels.forEach(p => {
      p.material.emissiveIntensity = 0;
    });
    state.pointLights.forEach(pl => { pl.intensity = 0; });
    state.monitorScreens.forEach(m => {
      m.material.emissiveIntensity = 0;
    });
  }
}

export function drawTickerScrolling(state, ticker, offset) {
  const { tickerCtx: ctx, tickerCanvas: cv } = state;
  ctx.fillStyle = '#010d01';
  ctx.fillRect(0, 0, cv.width, cv.height);
  ctx.fillStyle = '#00ff41';
  ctx.font = 'bold 54px "Courier New", monospace';
  ctx.textBaseline = 'middle';

  const unit = `   ${ticker}  ◆  ANALYSING...`;
  const unitWidth = ctx.measureText(unit).width;

  const startX = -(offset % unitWidth);
  for (let x = startX; x < cv.width + unitWidth; x += unitWidth) {
    ctx.fillText(unit, x, cv.height / 2);
  }
  state.tickerTexture.needsUpdate = true;
}

export function drawTickerSignal(state, rawSignal) {
  const { tickerCtx: ctx, tickerCanvas: cv } = state;

  const sig = (rawSignal || '').toUpperCase().trim();
  const display =
    ['BUY',  'OVERWEIGHT' ].includes(sig) ? 'BUY'  :
    ['SELL', 'UNDERWEIGHT'].includes(sig) ? 'SELL' :
    sig === 'HOLD'                         ? 'HOLD' : sig || '?';

  const palette = {
    BUY:  { bg: '#001800', text: '#00ff41', glow: '#00cc30' },
    SELL: { bg: '#1a0000', text: '#ff2525', glow: '#cc0000' },
    HOLD: { bg: '#130e00', text: '#ffcc00', glow: '#cc9900' },
  };
  const c = palette[display] || { bg: '#0a0a0a', text: '#aaa', glow: '#888' };

  ctx.fillStyle = c.bg;
  ctx.fillRect(0, 0, cv.width, cv.height);

  ctx.save();
  ctx.shadowColor  = c.glow;
  ctx.shadowBlur   = 28;
  ctx.fillStyle    = c.text;
  ctx.font         = 'bold 84px "Courier New", monospace';
  ctx.textAlign    = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(`★  ${display}  ★`, cv.width / 2, cv.height / 2);
  ctx.restore();

  state.tickerTexture.needsUpdate = true;
}

// ─── Core environment builders ───────────────────────────────────────────────

function _buildFloor(scene) {
  const texture = _makeWoodTexture();
  const geo = new THREE.PlaneGeometry(FLOOR_W, FLOOR_D);
  const mat = new THREE.MeshLambertMaterial({ map: texture });
  const mesh = new THREE.Mesh(geo, mat);
  mesh.rotation.x = -Math.PI / 2;
  scene.add(mesh);
}

function _makeWoodTexture() {
  const cv = document.createElement('canvas');
  cv.width = 1024; cv.height = 1024;
  const ctx = cv.getContext('2d');

  ctx.fillStyle = '#060300';
  ctx.fillRect(0, 0, 1024, 1024);

  const plankW = 72;
  const plankShades = ['#100800', '#140a01', '#0e0700', '#180c01', '#110801', '#130901'];

  for (let xi = 0; xi < 1024; xi += plankW) {
    const shade = plankShades[Math.floor(xi / plankW) % plankShades.length];
    ctx.fillStyle = shade;
    ctx.fillRect(xi + 1, 0, plankW - 2, 1024);

    for (let gi = 0; gi < 30; gi++) {
      const y0    = Math.random() * 1100 - 50;
      const curve = (Math.random() - 0.5) * 16;
      ctx.save();
      ctx.globalAlpha = 0.10 + Math.random() * 0.16;
      ctx.strokeStyle = Math.random() > 0.6 ? '#050300' : '#2a1608';
      ctx.lineWidth   = 0.4 + Math.random() * 1.0;
      ctx.beginPath();
      ctx.moveTo(xi + 1, y0);
      ctx.quadraticCurveTo(xi + plankW / 2, y0 + curve, xi + plankW - 1, y0 + curve * 0.6);
      ctx.stroke();
      ctx.restore();
    }

    ctx.fillStyle = '#020100';
    ctx.fillRect(xi, 0, 1, 1024);
  }

  const sheen = ctx.createLinearGradient(0, 0, 1024, 1024);
  sheen.addColorStop(0,   'rgba(40, 20, 5, 0.05)');
  sheen.addColorStop(0.5, 'rgba(60, 30, 8, 0.02)');
  sheen.addColorStop(1,   'rgba(20, 10, 2, 0.05)');
  ctx.fillStyle = sheen;
  ctx.fillRect(0, 0, 1024, 1024);

  const tex = new THREE.CanvasTexture(cv);
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(4, 4);
  return tex;
}

function _buildWalls(scene) {
  const wallMat = new THREE.MeshLambertMaterial({
    color: 0x1c1c2a,
    side: THREE.DoubleSide,
    transparent: true,
    opacity: 0.22,
    depthWrite: false,
  });

  // Back wall (where ticker display goes)
  const backGeo = new THREE.BoxGeometry(FLOOR_W, WALL_H, 0.25);
  const backWall = new THREE.Mesh(backGeo, wallMat.clone());
  backWall.position.set(0, WALL_H / 2, -FLOOR_D / 2);
  scene.add(backWall);
}

function _buildCeiling(scene, state) {
  const ceilMat = new THREE.MeshLambertMaterial({
    color: 0x111118,
    side: THREE.DoubleSide,
    transparent: true,
    opacity: 0.07,
    depthWrite: false,
  });
  const ceilGeo = new THREE.PlaneGeometry(FLOOR_W, FLOOR_D);
  const ceiling = new THREE.Mesh(ceilGeo, ceilMat);
  ceiling.rotation.x = Math.PI / 2;
  ceiling.position.y = WALL_H;
  scene.add(ceiling);

  // LED strip panels across the main trading floor — 5×7 grid for the larger floor
  const panelGeo = new THREE.BoxGeometry(3.6, 0.025, 0.1);
  const positions = [];
  for (let xi = -2; xi <= 2; xi++) {
    for (let zi = -3; zi <= 3; zi++) {
      positions.push([xi * 7, zi * 4]);
    }
  }
  for (const [x, z] of positions) {
    const mat = new THREE.MeshLambertMaterial({
      color: 0xfff8e0,
      emissive: new THREE.Color(0xfff8e0),
      emissiveIntensity: 0,
    });
    const panel = new THREE.Mesh(panelGeo, mat);
    panel.position.set(x, WALL_H - 0.03, z);
    scene.add(panel);
    state.lightPanels.push(panel);
  }
}

function _buildTickerDisplay(scene, state) {
  const cv  = document.createElement('canvas');
  cv.width  = 1024;
  cv.height = 128;
  const ctx = cv.getContext('2d');
  ctx.fillStyle = '#010201';
  ctx.fillRect(0, 0, cv.width, cv.height);

  state.tickerCanvas  = cv;
  state.tickerCtx     = ctx;
  state.tickerTexture = new THREE.CanvasTexture(cv);

  // Keep the ticker at the same absolute height as the original 7-unit wall so
  // the extra wall height above it is available for the company sign.
  const TICKER_Y = 5.5;

  const frameGeo = new THREE.BoxGeometry(16, 2.6, 0.22);
  const frameMat = new THREE.MeshLambertMaterial({ color: 0x0a0a0a });
  const frame    = new THREE.Mesh(frameGeo, frameMat);
  frame.position.set(0, TICKER_Y, -FLOOR_D / 2 + 0.14);
  scene.add(frame);

  const screenGeo = new THREE.PlaneGeometry(15.4, 2.1);
  const screenMat = new THREE.MeshBasicMaterial({ map: state.tickerTexture });
  const screen    = new THREE.Mesh(screenGeo, screenMat);
  screen.position.set(0, TICKER_Y, -FLOOR_D / 2 + 0.26);
  scene.add(screen);
}

// ─── Company sign (above ticker display on the back wall) ────────────────────

/**
 * Builds a dimensional "TradingAgents" nameplate on the back wall, centred
 * above the LED ticker display.  The sign uses a BoxGeometry with cream-coloured
 * sides so it reads as a solid 3-D mounted plate; the Cormorant font (loaded via
 * Google Fonts in index.html) is drawn onto a CanvasTexture once the font is
 * available and composited onto the front face.
 */
function _buildCompanySign(scene) {
  const signW = 10.0;   // width  (world units)
  const signH = 0.60;   // height
  const signD = 0.22;   // depth  — gives the raised-plate 3-D look
  const signY = WALL_H - 1.6;              // near the top of the wall
  const signZ = -FLOOR_D / 2 + 0.22;      // flush with the back wall surface

  // ── 3-D backing plate — cream ivory with slightly darker sides ──
  const faceMat  = new THREE.MeshLambertMaterial({ color: 0xf0ece3 }); // front/back
  const sideMat  = new THREE.MeshLambertMaterial({ color: 0xc8c2b6 }); // L/R sides
  const edgeMat  = new THREE.MeshLambertMaterial({ color: 0xd4cfc8 }); // top/bottom

  const box = new THREE.Mesh(
    new THREE.BoxGeometry(signW, signH, signD),
    // Material index order: +X, -X, +Y, -Y, +Z, -Z
    [sideMat, sideMat, edgeMat, edgeMat, faceMat, faceMat],
  );
  box.position.set(0, signY, signZ);
  scene.add(box);

  // ── Canvas text plane composited onto the front face ──
  // Canvas dimensions must match the plane's aspect ratio to avoid stretching.
  // Plane: (signW-0.05) × (signH-0.05) = 9.95 × 0.55 ≈ 18.1 : 1
  const planeW = signW - 0.05;
  const planeH = signH - 0.05;
  const CV_H   = 80;
  const CV_W   = Math.round((planeW / planeH) * CV_H); // ≈ 1448

  const cv  = document.createElement('canvas');
  cv.width  = CV_W;
  cv.height = CV_H;
  const ctx     = cv.getContext('2d');
  const texture = new THREE.CanvasTexture(cv);

  const textPlane = new THREE.Mesh(
    new THREE.PlaneGeometry(planeW, planeH),
    new THREE.MeshBasicMaterial({ map: texture, transparent: true }),
  );
  // Position the plane just in front of the box's front face
  textPlane.position.set(0, signY, signZ + signD / 2 + 0.003);
  scene.add(textPlane);

  const _draw = () => {
    ctx.fillStyle = '#f0ece3';
    ctx.fillRect(0, 0, CV_W, CV_H);

    ctx.fillStyle    = '#000000';
    ctx.font         = '400 48px "Cormorant", serif';
    ctx.textAlign    = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('TradingAgents', CV_W / 2, CV_H / 2);

    texture.needsUpdate = true;
  };

  // Draw once the Cormorant font is confirmed available; fall back immediately
  // if the font API is absent (older browsers will use the first serif found).
  if (typeof document !== 'undefined' && document.fonts) {
    document.fonts.load('400 48px "Cormorant"').then(_draw).catch(_draw);
  } else {
    _draw();
  }
}

// ─── Lounge area (near ticker wall, z ≈ -8 to -10) ──────────────────────────

function _buildLounge(scene) {
  // Decorative plants flanking the ticker display in the far corners
  _buildPlant(scene, -11.5, -13.5);
  _buildPlant(scene,  11.5, -13.5);

  // Water cooler — left of centre
  _buildWaterCooler(scene, -6.5, -12.0);

  // Coffee station — right of centre
  _buildCoffeeStation(scene, 6.5, -12.0);

  // High standing table between them
  _buildStandingTable(scene, 0.0, -12.2);
}

function _buildWaterCooler(scene, x, z) {
  const bodyMat   = new THREE.MeshLambertMaterial({ color: 0xe8eef4 });
  const bottleMat = new THREE.MeshLambertMaterial({ color: 0x7ab8d8, transparent: true, opacity: 0.78 });
  const trimMat   = new THREE.MeshLambertMaterial({ color: 0x2277aa });
  const chromeMat = new THREE.MeshLambertMaterial({ color: 0xaaaaaa });

  const g = new THREE.Group();

  // Cabinet body
  const body = new THREE.Mesh(new THREE.BoxGeometry(0.40, 0.90, 0.40), bodyMat);
  body.position.set(0, 0.45, 0);
  g.add(body);

  // Front panel with blue trim
  const panel = new THREE.Mesh(new THREE.BoxGeometry(0.28, 0.34, 0.04), trimMat);
  panel.position.set(0, 0.46, 0.22);
  g.add(panel);

  // Drip tray
  const tray = new THREE.Mesh(new THREE.BoxGeometry(0.36, 0.04, 0.15), chromeMat);
  tray.position.set(0, 0.22, 0.20);
  g.add(tray);

  // Inverted water jug on top
  const jug = new THREE.Mesh(new THREE.CylinderGeometry(0.17, 0.17, 0.54, 12), bottleMat);
  jug.position.set(0, 1.17, 0);
  g.add(jug);

  // Jug neck cap
  const cap = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.09, 0.06, 10),
    new THREE.MeshLambertMaterial({ color: 0x3388aa }));
  cap.position.set(0, 0.93, 0);
  g.add(cap);

  g.position.set(x, 0, z);
  scene.add(g);
}

function _buildCoffeeStation(scene, x, z) {
  const cabinetMat = new THREE.MeshLambertMaterial({ color: 0x2e1a0a });
  const topMat     = new THREE.MeshLambertMaterial({ color: 0x5c3a1e });
  const machineMat = new THREE.MeshLambertMaterial({ color: 0x111111 });
  const chromeMat  = new THREE.MeshLambertMaterial({ color: 0x999999 });
  const cupMat     = new THREE.MeshLambertMaterial({ color: 0xf0ede8 });

  const g = new THREE.Group();

  // Counter cabinet
  const cabinet = new THREE.Mesh(new THREE.BoxGeometry(1.60, 0.92, 0.65), cabinetMat);
  cabinet.position.set(0, 0.46, 0);
  g.add(cabinet);

  // Counter top surface
  const top = new THREE.Mesh(new THREE.BoxGeometry(1.66, 0.07, 0.68), topMat);
  top.position.set(0, 0.955, 0);
  g.add(top);

  // Espresso machine body
  const machine = new THREE.Mesh(new THREE.BoxGeometry(0.44, 0.50, 0.38), machineMat);
  machine.position.set(-0.46, 1.22, 0.04);
  g.add(machine);

  // Machine display (tiny glowing panel)
  const display = new THREE.Mesh(new THREE.BoxGeometry(0.28, 0.10, 0.02),
    new THREE.MeshLambertMaterial({
      color: 0x002244,
      emissive: new THREE.Color(0x001133),
      emissiveIntensity: 1.0,
    }));
  display.position.set(0, 0.09, 0.20);
  machine.add(display);

  // Chrome spout
  const spout = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.08, 0.20), chromeMat);
  spout.position.set(-0.46, 1.02, 0.27);
  g.add(spout);

  // Stacked paper cups
  for (let i = 0; i < 4; i++) {
    const cup = new THREE.Mesh(
      new THREE.CylinderGeometry(0.046, 0.038, 0.09, 8), cupMat
    );
    cup.position.set(0.08 + i * 0.13, 0.99, -0.14);
    g.add(cup);
  }

  g.position.set(x, 0, z);
  scene.add(g);
}

function _buildStandingTable(scene, x, z) {
  const topMat  = new THREE.MeshLambertMaterial({ color: 0x7a5c38 });
  const stemMat = new THREE.MeshLambertMaterial({ color: 0x555566 });

  const g = new THREE.Group();

  const top = new THREE.Mesh(new THREE.CylinderGeometry(0.40, 0.40, 0.06, 16), topMat);
  top.position.set(0, 1.06, 0);
  g.add(top);

  const stem = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.04, 1.00, 8), stemMat);
  stem.position.set(0, 0.53, 0);
  g.add(stem);

  const base = new THREE.Mesh(new THREE.CylinderGeometry(0.22, 0.22, 0.04, 12), stemMat);
  base.position.set(0, 0.02, 0);
  g.add(base);

  g.position.set(x, 0, z);
  scene.add(g);
}

function _buildPlant(scene, x, z) {
  const potMat  = new THREE.MeshLambertMaterial({ color: 0x6b4226 });
  const soilMat = new THREE.MeshLambertMaterial({ color: 0x2a1a0a });
  const leafMat = new THREE.MeshLambertMaterial({ color: 0x1a6b2a });

  const g = new THREE.Group();

  const pot = new THREE.Mesh(new THREE.CylinderGeometry(0.20, 0.15, 0.34, 10), potMat);
  pot.position.set(0, 0.17, 0);
  g.add(pot);

  const soil = new THREE.Mesh(new THREE.CylinderGeometry(0.19, 0.19, 0.04, 10), soilMat);
  soil.position.set(0, 0.36, 0);
  g.add(soil);

  // Layered foliage spheres for a full bushy appearance
  const foliage = [
    [  0.00, 0.76,  0.00, 0.28 ],
    [ -0.10, 0.62,  0.06, 0.21 ],
    [  0.10, 0.65, -0.06, 0.21 ],
    [ -0.05, 0.92,  0.03, 0.17 ],
    [  0.08, 0.90, -0.04, 0.17 ],
    [  0.00, 0.58,  0.00, 0.16 ],
  ];
  for (const [fx, fy, fz, fr] of foliage) {
    const f = new THREE.Mesh(new THREE.SphereGeometry(fr, 8, 6), leafMat);
    f.position.set(fx, fy, fz);
    g.add(f);
  }

  g.position.set(x, 0, z);
  scene.add(g);
}

// ─── Meeting room (z = -6 to -0.5, x = -6.5 to 6.5) — all 4 glass walls ─────

function _buildMeetingRoom(scene) {
  // Cool blue-tinted glass — clearly interior partitions, distinct from the
  // darker external walls.
  const glassMat = new THREE.MeshLambertMaterial({
    color: 0xaaccee,
    transparent: true,
    opacity: 0.15,
    depthWrite: false,
    side: THREE.DoubleSide,
  });
  const frameMat = new THREE.MeshLambertMaterial({ color: 0x8888a0 });

  const roomMinZ = -6.0;   // back wall (faces analyst zone)
  const roomMaxZ = -0.5;   // front wall (faces trading desk zone)
  const roomCZ   = (roomMinZ + roomMaxZ) / 2; // -3.25
  const roomW    = 13.0;   // x: -6.5 to 6.5
  const roomD    = Math.abs(roomMaxZ - roomMinZ); // 5.5

  // Front glass wall (faces trading desk area)
  const fWall = new THREE.Mesh(new THREE.BoxGeometry(roomW, WALL_H, 0.08), glassMat.clone());
  fWall.position.set(0, WALL_H / 2, roomMaxZ);
  scene.add(fWall);
  scene.add(_frameBar(roomW + 0.10, 0.12, 0.12, frameMat, 0, WALL_H, roomMaxZ));

  // Back glass wall (faces analyst desks)
  const bWall = new THREE.Mesh(new THREE.BoxGeometry(roomW, WALL_H, 0.08), glassMat.clone());
  bWall.position.set(0, WALL_H / 2, roomMinZ);
  scene.add(bWall);
  scene.add(_frameBar(roomW + 0.10, 0.12, 0.12, frameMat, 0, WALL_H, roomMinZ));

  // Left glass wall
  const lWall = new THREE.Mesh(new THREE.BoxGeometry(0.08, WALL_H, roomD), glassMat.clone());
  lWall.position.set(-6.5, WALL_H / 2, roomCZ);
  scene.add(lWall);
  scene.add(_frameBar(0.12, 0.12, roomD + 0.10, frameMat, -6.5, WALL_H, roomCZ));

  // Right glass wall
  const rWall = new THREE.Mesh(new THREE.BoxGeometry(0.08, WALL_H, roomD), glassMat.clone());
  rWall.position.set(6.5, WALL_H / 2, roomCZ);
  scene.add(rWall);
  scene.add(_frameBar(0.12, 0.12, roomD + 0.10, frameMat, 6.5, WALL_H, roomCZ));

  // Corner posts at all four corners
  for (const cx of [-6.5, 6.5]) {
    for (const cz of [roomMinZ, roomMaxZ]) {
      const post = new THREE.Mesh(new THREE.BoxGeometry(0.12, WALL_H, 0.12), frameMat);
      post.position.set(cx, WALL_H / 2, cz);
      scene.add(post);
    }
  }

  // ── Conference table — dark mahogany ─────────────────────────────────────
  const tableCZ      = -3.75;
  const tableW       = 7.0;
  const tableD       = 2.8;
  const tableTopMat  = new THREE.MeshLambertMaterial({ color: 0x3a1e0e });
  const tableEdgeMat = new THREE.MeshLambertMaterial({ color: 0x6b3c1c });
  const legMat       = new THREE.MeshLambertMaterial({ color: 0x2a2a38 });

  const tableTop = new THREE.Mesh(new THREE.BoxGeometry(tableW, 0.09, tableD), tableTopMat);
  tableTop.position.set(0, 0.79, tableCZ);
  scene.add(tableTop);

  const edgeData = [
    [tableW + 0.04, 0.03, 0.04,          0,           0.84, tableCZ - tableD / 2],
    [tableW + 0.04, 0.03, 0.04,          0,           0.84, tableCZ + tableD / 2],
    [0.04,          0.03, tableD + 0.04, -tableW / 2, 0.84, tableCZ            ],
    [0.04,          0.03, tableD + 0.04,  tableW / 2, 0.84, tableCZ            ],
  ];
  for (const [ew, eh, ed, ex, ey, ez] of edgeData) {
    const trim = new THREE.Mesh(new THREE.BoxGeometry(ew, eh, ed), tableEdgeMat);
    trim.position.set(ex, ey, ez);
    scene.add(trim);
  }

  for (const lx of [-2.2, 2.2]) {
    const ped = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.75, 0.12), legMat);
    ped.position.set(lx, 0.375, tableCZ);
    scene.add(ped);
    const foot = new THREE.Mesh(new THREE.BoxGeometry(0.55, 0.04, 0.45), legMat);
    foot.position.set(lx, 0.02, tableCZ);
    scene.add(foot);
  }

  // ── Chairs ───────────────────────────────────────────────────────────────
  // Rotation note (Three.js, Y-up):  ry=0 → +Z,  ry=π → -Z,
  //                                   ry=π/2 → +X, ry=-π/2 → -X
  const chairDefs = [
    { x: -3,   z: -3.75, ry:  Math.PI / 2  }, // Bull  (faces +X across table)
    { x:  3,   z: -3.75, ry: -Math.PI / 2  }, // Bear  (faces -X across table)
    { x:  0,   z: -5,    ry:  0            }, // Research Manager (head, faces +Z)
    { x:  0,   z: -2.2,  ry:  Math.PI      }, // empty opposite head
    { x: -2.4, z: -2.5,  ry:  Math.PI      }, // empty side
    { x:  2.4, z: -2.5,  ry:  Math.PI      }, // empty side
  ];
  for (const cd of chairDefs) _buildChair(scene, cd.x, cd.z, cd.ry);

  // "RESEARCH" badge on the front glass wall
  const badgeMat = new THREE.MeshLambertMaterial({ color: 0x152035 });
  const badge = new THREE.Mesh(new THREE.BoxGeometry(3.0, 0.32, 0.05), badgeMat);
  badge.position.set(0, WALL_H - 0.35, roomMaxZ + 0.09);
  scene.add(badge);

  // Glass door on the front wall — closed, flush with the wall
  _buildGlassDoor(scene, -0.5, roomMaxZ, 0);
}

/** Builds a single office chair at world position (x, 0, z), rotated by ry. */
function _buildChair(scene, x, z, ry) {
  const cushMat  = new THREE.MeshLambertMaterial({ color: 0x181828 });
  const frameMat = new THREE.MeshLambertMaterial({ color: 0x666676 });

  const g = new THREE.Group();

  // Seat cushion
  const seat = new THREE.Mesh(new THREE.BoxGeometry(0.52, 0.08, 0.50), cushMat);
  seat.position.set(0, 0.50, 0);
  g.add(seat);

  // Backrest
  const back = new THREE.Mesh(new THREE.BoxGeometry(0.52, 0.54, 0.07), cushMat);
  back.position.set(0, 0.84, -0.22);
  g.add(back);

  // Central pedestal
  const stem = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.44, 0.06), frameMat);
  stem.position.set(0, 0.27, 0);
  g.add(stem);

  // Star base
  const bH = new THREE.Mesh(new THREE.BoxGeometry(0.44, 0.04, 0.09), frameMat);
  bH.position.set(0, 0.05, 0);
  g.add(bH);
  const bV = new THREE.Mesh(new THREE.BoxGeometry(0.09, 0.04, 0.44), frameMat);
  bV.position.set(0, 0.05, 0);
  g.add(bV);

  g.position.set(x, 0, z);
  g.rotation.y = ry;
  scene.add(g);
}

/**
 * Decorative glass door set in a wall that runs along the world X axis.
 *
 * The hinge is at (hingeX, 0, wallZ).  The door panel extends 1.0 unit in
 * the local +X direction from the hinge, and swings around the vertical Y
 * axis by `openAngle` radians:
 *   • Positive angle → far end swings toward -Z (into a room whose interior
 *     is at smaller Z values, e.g. the meeting room).
 *   • Negative angle → far end swings toward +Z (into a room whose interior
 *     is at larger Z values, e.g. the PM office).
 *
 * For a ~20° ajar look use openAngle ≈ ±0.35.
 */
function _buildGlassDoor(scene, hingeX, wallZ, openAngle) {
  const doorW  = 1.00;  // width along local X
  const doorH  = 2.45;  // height
  const frmT   = 0.055; // aluminium frame tube size
  const glassT = 0.04;  // glass slab thickness

  const frameMat  = new THREE.MeshLambertMaterial({ color: 0x8888a0 });
  const glassMat  = new THREE.MeshLambertMaterial({
    color: 0xb8d8f0,
    transparent: true,
    opacity: 0.38,
    depthWrite: false,
    side: THREE.DoubleSide,
  });
  const handleMat = new THREE.MeshLambertMaterial({ color: 0xd0d0e0 });

  const g = new THREE.Group();

  // ── Glass panel (inset from frame) ──
  const panel = new THREE.Mesh(
    new THREE.BoxGeometry(doorW - frmT * 2, doorH - frmT * 2, glassT),
    glassMat
  );
  panel.position.set(doorW / 2, doorH / 2, 0);
  g.add(panel);

  // ── Aluminium frame — 4 bars ──
  // Top
  const topBar = new THREE.Mesh(
    new THREE.BoxGeometry(doorW + frmT, frmT, frmT * 1.8), frameMat
  );
  topBar.position.set(doorW / 2, doorH + frmT / 2, 0);
  g.add(topBar);

  // Bottom
  const botBar = new THREE.Mesh(
    new THREE.BoxGeometry(doorW + frmT, frmT, frmT * 1.8), frameMat
  );
  botBar.position.set(doorW / 2, -frmT / 2, 0);
  g.add(botBar);

  // Hinge-side vertical
  const hingeBar = new THREE.Mesh(
    new THREE.BoxGeometry(frmT, doorH + frmT * 2, frmT * 1.8), frameMat
  );
  hingeBar.position.set(0, doorH / 2, 0);
  g.add(hingeBar);

  // Latch-side vertical
  const latchBar = new THREE.Mesh(
    new THREE.BoxGeometry(frmT, doorH + frmT * 2, frmT * 1.8), frameMat
  );
  latchBar.position.set(doorW, doorH / 2, 0);
  g.add(latchBar);

  // ── Pull handle — vertical bar with two mounting stubs ──
  const hx = doorW - 0.13;   // x: near the latch edge
  const hz = frmT * 1.2;     // z: protrudes slightly from face

  const pullBar = new THREE.Mesh(
    new THREE.BoxGeometry(0.038, 0.40, 0.038), handleMat
  );
  pullBar.position.set(hx, doorH * 0.50, hz);
  g.add(pullBar);

  for (const hy of [doorH * 0.36, doorH * 0.64]) {
    const stub = new THREE.Mesh(
      new THREE.BoxGeometry(0.038, 0.038, 0.11), handleMat
    );
    stub.position.set(hx, hy, hz * 0.5);
    g.add(stub);
  }

  // ── Position hinge and rotate to ajar angle ──
  g.position.set(hingeX, 0, wallZ);
  g.rotation.y = openAngle;

  scene.add(g);
}

// ─── Desks (analysts, trader, risk, PM) ──────────────────────────────────────

/**
 * Builds individual desks for each agent config.
 * Skips configs with `seated: true` (meeting-room characters who share the
 * conference table and have no personal desk).
 */
function _buildDesks(scene, agentConfigs, state) {
  for (const cfg of agentConfigs) {
    if (cfg.seated) continue;
    const isPM = cfg.name === 'Portfolio Manager';
    _buildSingleDesk(scene, cfg.desk.x, cfg.desk.z, state, isPM);
  }
}

/**
 * Shared desk builder.  When `premium` is true an executive-spec desk is
 * produced (dark walnut, slightly wider) for the Portfolio Manager.
 */
function _buildSingleDesk(scene, x, z, state, premium = false) {
  const deskW   = premium ? 4.0 : 3.2;
  const deskD   = premium ? 1.4 : 1.2;
  const deskTop = 0.98;
  const thick   = 0.08;
  const legH    = deskTop - thick;

  const topMat    = new THREE.MeshLambertMaterial({ color: premium ? 0x1e1006 : 0xc4956a });
  const frameMat  = new THREE.MeshLambertMaterial({ color: premium ? 0x160c04 : 0xa07848 });
  const edgeMat   = new THREE.MeshLambertMaterial({ color: premium ? 0x0e0802 : 0x7a5432 });
  const monFrmMat = new THREE.MeshLambertMaterial({ color: 0x111111 });
  const standMat  = new THREE.MeshLambertMaterial({ color: 0x888888 });
  const kbdMat    = new THREE.MeshLambertMaterial({ color: 0x1a1a1a });

  const topGeo       = new THREE.BoxGeometry(deskW, thick, deskD);
  const sidePanGeo   = new THREE.BoxGeometry(0.09, legH, deskD);
  const modPanGeo    = new THREE.BoxGeometry(deskW - 0.2, legH * 0.55, 0.06);
  const crossBarGeo  = new THREE.BoxGeometry(deskW - 0.22, 0.05, 0.05);
  const frontTrimGeo = new THREE.BoxGeometry(deskW + 0.01, thick + 0.02, 0.04);

  const monW   = 0.66;
  const monH   = 0.48;
  const monGeo  = new THREE.BoxGeometry(monW, monH, 0.05);
  const baseGeo = new THREE.BoxGeometry(0.26, 0.03, 0.16);
  const kbdGeo  = new THREE.BoxGeometry(0.70, 0.03, 0.28);

  const monCols = [
    { x: -0.42, yAngle:  0.22 },
    { x:  0.42, yAngle: -0.22 },
  ];
  const monRows = [
    { dy: 0.22 + monH / 2,            xAngle: 0.06 },
    { dy: 0.22 + monH * 1.5 + 0.08,   xAngle: 0.15 },
  ];
  const monZ = -(deskD / 2) + 0.28;

  const deskGroup = new THREE.Group();
  deskGroup.position.set(x, 0, z);

  // Desktop surface
  const top = new THREE.Mesh(topGeo, topMat);
  top.position.set(0, deskTop - thick / 2, 0);
  deskGroup.add(top);

  // Side panel legs
  for (const sx of [-(deskW / 2 - 0.045), deskW / 2 - 0.045]) {
    const sp = new THREE.Mesh(sidePanGeo, frameMat);
    sp.position.set(sx, legH / 2, 0);
    deskGroup.add(sp);
  }

  // Back modesty panel
  const mod = new THREE.Mesh(modPanGeo, frameMat);
  mod.position.set(0, legH * 0.28, -(deskD / 2 - 0.03));
  deskGroup.add(mod);

  // Structural crossbar
  const bar = new THREE.Mesh(crossBarGeo, edgeMat);
  bar.position.set(0, 0.18, 0);
  deskGroup.add(bar);

  // Front edge trim
  const frontTrim = new THREE.Mesh(frontTrimGeo, edgeMat);
  frontTrim.position.set(0, deskTop - thick / 2, deskD / 2 + 0.02);
  deskGroup.add(frontTrim);

  // 2×2 monitor grid
  for (const col of monCols) {
    const topY  = deskTop + monRows[monRows.length - 1].dy;
    const poleH = topY - deskTop;
    const poleGeo = new THREE.BoxGeometry(0.05, poleH, 0.05);
    const pole    = new THREE.Mesh(poleGeo, standMat);
    pole.position.set(col.x, deskTop + poleH / 2, monZ);
    deskGroup.add(pole);

    const base = new THREE.Mesh(baseGeo, standMat);
    base.position.set(col.x, deskTop + 0.015, monZ);
    deskGroup.add(base);

    for (const row of monRows) {
      const screenMat = new THREE.MeshLambertMaterial({
        color: 0x001100,
        emissive: new THREE.Color(0x001100),
        emissiveIntensity: 0,
      });

      const mon = new THREE.Mesh(monGeo, monFrmMat);
      mon.position.set(col.x, deskTop + row.dy, monZ);
      mon.rotation.y = col.yAngle;
      mon.rotation.x = row.xAngle;
      deskGroup.add(mon);

      const screenPlane = new THREE.PlaneGeometry(monW - 0.06, monH - 0.06);
      const screen = new THREE.Mesh(screenPlane, screenMat);
      screen.position.set(0, 0, 0.027);
      mon.add(screen);
      state.monitorScreens.push(screen);
    }
  }

  // Keyboard
  const kbd = new THREE.Mesh(kbdGeo, kbdMat);
  kbd.position.set(0, deskTop + 0.02, deskD / 2 - 0.2);
  deskGroup.add(kbd);

  scene.add(deskGroup);
}

// ─── NPC trading desk row (z = 3, flanking the Trader) ──────────────────────

/**
 * Adds four NPC desks (two on each side of the Trader) to create the impression
 * of a full trading desk populated by background employees.  Each NPC position
 * gets a static blocky silhouette and a point light.
 *
 * Desk spacing equals the standard desk width (3.2 u) so desks sit flush
 * against each other in a continuous row:
 *   x = -6.4  -3.2  0 (Trader)  +3.2  +6.4
 */
function _buildNPCTradingDesks(scene, state) {
  const NPC_X      = [-6.4, -3.2, 3.2, 6.4];
  const NPC_COLORS = [0x3a4a5c, 0x2d3a48, 0x3a4a5c, 0x2d3a48];

  for (let i = 0; i < NPC_X.length; i++) {
    _buildSingleDesk(scene, NPC_X[i], 3, state);
    _buildStaticNPC(scene, NPC_X[i], 3, NPC_COLORS[i]);

    // Point light above each NPC desk, toggled with the rest
    const pl = new THREE.PointLight(0xfff0d0, 0, 13, 1.8);
    pl.position.set(NPC_X[i], WALL_H - 1.5, 3);
    scene.add(pl);
    state.pointLights.push(pl);
  }
}

/**
 * A static, non-animated blocky figure that sits at an NPC desk.
 * Identical proportions to Character but no animation state.
 */
function _buildStaticNPC(scene, x, z, color) {
  const mat     = new THREE.MeshLambertMaterial({ color });
  const skinMat = new THREE.MeshLambertMaterial({ color: 0xd4a885 });
  const darkMat = new THREE.MeshLambertMaterial({ color: 0x1a1a2e });
  const shoeMat = new THREE.MeshLambertMaterial({ color: 0x111111 });

  const addBox = (g, w, h, d, m, px, py, pz) => {
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), m);
    mesh.position.set(px, py, pz);
    g.add(mesh);
    return mesh;
  };

  const g = new THREE.Group();

  // Body
  addBox(g, 0.46, 0.56, 0.22, mat, 0, 0.93, 0);

  // Head
  addBox(g, 0.38, 0.38, 0.38, skinMat, 0, 1.47, 0);

  // Arms (static, typing posture — slightly forward)
  for (const sx of [-0.305, 0.305]) {
    const arm = new THREE.Mesh(new THREE.BoxGeometry(0.15, 0.48, 0.15), mat);
    arm.position.set(sx, 0.87, 0);
    arm.rotation.x = -0.55;
    g.add(arm);
  }

  // Legs
  for (const lx of [-0.12, 0.12]) {
    addBox(g, 0.18, 0.56, 0.18, darkMat, lx, 0.37, 0);
  }

  // Shoes
  for (const sx of [-0.12, 0.12]) {
    addBox(g, 0.22, 0.10, 0.26, shoeMat, sx, 0.05, 0.04);
  }

  // Stand in front of desk, facing the desk (toward -Z)
  g.position.set(x, 0, z + 1.3);
  g.rotation.y = Math.PI;
  scene.add(g);
}

// ─── Portfolio Manager glass corner office (z = 10–15) — all 4 glass walls ───

/**
 * Encloses the back section of the floor in four glass panels to form the
 * MD's private corner office.  The PM's desk is built by _buildDesks() with
 * the premium flag; this function adds the full enclosure, visitor area,
 * extra ceiling lights, and a brass nameplate.
 */
function _buildPMOffice(scene, state) {
  const glassMat = new THREE.MeshLambertMaterial({
    color: 0xbbddee,
    transparent: true,
    opacity: 0.19,
    depthWrite: false,
    side: THREE.DoubleSide,
  });
  const frameMat = new THREE.MeshLambertMaterial({ color: 0x777790 });
  const plateMat = new THREE.MeshLambertMaterial({ color: 0x9c8040 }); // brass

  const offMinZ = 10.0;
  const offMaxZ = FLOOR_D / 2; // = 15
  const offCZ   = (offMinZ + offMaxZ) / 2; // 12.5
  const offW    = 13.0;  // x: -6.5 to 6.5
  const offD    = offMaxZ - offMinZ; // 5.0

  // Front glass wall (office entrance, faces the risk desk zone)
  const fWall = new THREE.Mesh(new THREE.BoxGeometry(offW, WALL_H, 0.10), glassMat.clone());
  fWall.position.set(0, WALL_H / 2, offMinZ);
  scene.add(fWall);
  scene.add(_frameBar(offW + 0.20, 0.14, 0.14, frameMat, 0, WALL_H, offMinZ));
  scene.add(_frameBar(offW + 0.20, 0.08, 0.14, frameMat, 0, 0.04,   offMinZ));

  // Back glass wall (closes the office at the far edge of the floor)
  const bWall = new THREE.Mesh(new THREE.BoxGeometry(offW, WALL_H, 0.10), glassMat.clone());
  bWall.position.set(0, WALL_H / 2, offMaxZ);
  scene.add(bWall);
  scene.add(_frameBar(offW + 0.20, 0.14, 0.14, frameMat, 0, WALL_H, offMaxZ));

  // Left glass wall
  const lWall = new THREE.Mesh(new THREE.BoxGeometry(0.10, WALL_H, offD), glassMat.clone());
  lWall.position.set(-6.5, WALL_H / 2, offCZ);
  scene.add(lWall);
  scene.add(_frameBar(0.14, 0.14, offD + 0.20, frameMat, -6.5, WALL_H, offCZ));
  scene.add(_frameBar(0.14, 0.08, offD + 0.20, frameMat, -6.5, 0.04,   offCZ));

  // Right glass wall
  const rWall = new THREE.Mesh(new THREE.BoxGeometry(0.10, WALL_H, offD), glassMat.clone());
  rWall.position.set(6.5, WALL_H / 2, offCZ);
  scene.add(rWall);
  scene.add(_frameBar(0.14, 0.14, offD + 0.20, frameMat, 6.5, WALL_H, offCZ));
  scene.add(_frameBar(0.14, 0.08, offD + 0.20, frameMat, 6.5, 0.04,   offCZ));

  // Corner posts at all four corners
  for (const cx of [-6.5, 6.5]) {
    for (const cz of [offMinZ, offMaxZ]) {
      const post = new THREE.Mesh(new THREE.BoxGeometry(0.14, WALL_H, 0.14), frameMat);
      post.position.set(cx, WALL_H / 2, cz);
      scene.add(post);
    }
  }

  // Brass nameplate above the entrance
  const plate = new THREE.Mesh(new THREE.BoxGeometry(3.4, 0.36, 0.06), plateMat);
  plate.position.set(0, WALL_H - 0.38, offMinZ + 0.12);
  scene.add(plate);

  // Glass door on the front wall — hinge at x=-0.5, swings inward (toward +Z)
  _buildGlassDoor(scene, -0.5, offMinZ, 0);

  // Visitor chairs inside (ry=0 → faces +Z toward PM)
  _buildChair(scene, -1.3, 11.0, 0);
  _buildChair(scene,  1.3, 11.0, 0);

  // Low coffee table between the visitor chairs
  const cfTop = new THREE.Mesh(
    new THREE.BoxGeometry(1.1, 0.04, 0.55),
    new THREE.MeshLambertMaterial({ color: 0x2a1a0a })
  );
  cfTop.position.set(0, 0.44, 11.1);
  scene.add(cfTop);
  for (const lx of [-0.42, 0.42]) {
    const cfLeg = new THREE.Mesh(
      new THREE.BoxGeometry(0.05, 0.40, 0.05),
      new THREE.MeshLambertMaterial({ color: 0x555555 })
    );
    cfLeg.position.set(lx, 0.20, 11.1);
    scene.add(cfLeg);
  }

  // Extra ceiling light panels inside PM office
  const pmPanelGeo = new THREE.BoxGeometry(3.6, 0.025, 0.1);
  for (const [px, pz] of [[-2.5, 12.5], [0, 12.5], [2.5, 12.5]]) {
    const mat = new THREE.MeshLambertMaterial({
      color: 0xfff8e0,
      emissive: new THREE.Color(0xfff8e0),
      emissiveIntensity: 0,
    });
    const panel = new THREE.Mesh(pmPanelGeo, mat);
    panel.position.set(px, WALL_H - 0.03, pz);
    scene.add(panel);
    state.lightPanels.push(panel);
  }

  // Point lights inside PM office
  for (const [px, pz] of [[-2.5, 12.5], [0, 12.5], [2.5, 12.5]]) {
    const pl = new THREE.PointLight(0xfff0d0, 0, 13, 1.8);
    pl.position.set(px, WALL_H - 1.5, pz);
    scene.add(pl);
    state.pointLights.push(pl);
  }
}

// ─── Lighting ────────────────────────────────────────────────────────────────

function _buildLighting(scene, agentConfigs, state) {
  const ambient = new THREE.AmbientLight(0x7788aa, 0.45);
  scene.add(ambient);
  state.ambientLight = ambient;

  const sun = new THREE.DirectionalLight(0xfff5e0, 0);
  sun.position.set(4, 14, 8);
  scene.add(sun);
  state.sunLight = sun;

  // One point light above every agent position (including seated meeting-room
  // characters — their desk position sits inside the meeting room).
  for (const cfg of agentConfigs) {
    const pl = new THREE.PointLight(0xfff0d0, 0, 13, 1.8);
    pl.position.set(cfg.desk.x, WALL_H - 1.5, cfg.desk.z);
    scene.add(pl);
    state.pointLights.push(pl);
  }
}

// ─── Utility helpers ─────────────────────────────────────────────────────────

/** Creates a thin box (frame bar) and returns it positioned in world space. */
function _frameBar(w, h, d, mat, x, y, z) {
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat);
  mesh.position.set(x, y, z);
  return mesh;
}
