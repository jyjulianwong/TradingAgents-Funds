/**
 * characters.js — blocky Minecraft-style employee characters.
 *
 * Exports:
 *   AGENT_CONFIGS   — array of { name, color, desk: THREE.Vector3, homeRotation?, seated? }
 *   CharacterManager — manages all 12 characters
 *
 * homeRotation (optional):
 *   Default Math.PI (face -Z, toward the ticker wall).  Override for characters
 *   whose natural facing direction differs — e.g. meeting-room occupants who
 *   face the conference table rather than the display wall.
 *
 * seated (optional):
 *   When true, homePos == desk position (no 1.3-unit forward offset).  Used for
 *   characters who sit around the conference table rather than stand at a desk.
 */

import * as THREE from 'three';
import { CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';

// ─── Agent configuration ─────────────────────────────────────────────────────

export const AGENT_CONFIGS = [
  // ── Analyst row (back, near ticker wall, z = -9) ──────────────────────────
  { name: 'Market Analyst',       color: 0x2196F3, desk: new THREE.Vector3(-7.5, 0, -9) },
  { name: 'Sentiment Analyst',    color: 0x9C27B0, desk: new THREE.Vector3(-2.5, 0, -9) },
  { name: 'News Analyst',         color: 0xFF9800, desk: new THREE.Vector3( 2.5, 0, -9) },
  { name: 'Fundamentals Analyst', color: 0x4CAF50, desk: new THREE.Vector3( 7.5, 0, -9) },

  // ── Meeting room — seated around conference table (z = -6 to -0.5) ───────
  //   homeRotation drives the direction each character faces:
  //     Bull  (left side)  faces +X (across the table toward Bear)
  //     Bear  (right side) faces -X (across the table toward Bull)
  //     RM    (head)       faces +Z (down the length of the table toward Bull/Bear)
  { name: 'Bull Researcher',   color: 0x8BC34A, desk: new THREE.Vector3(-3,   0, -3.75), homeRotation:  Math.PI / 2, seated: true },
  { name: 'Bear Researcher',   color: 0xF44336, desk: new THREE.Vector3( 3,   0, -3.75), homeRotation: -Math.PI / 2, seated: true },
  { name: 'Research Manager',  color: 0x795548, desk: new THREE.Vector3( 0,   0, -5),    homeRotation:  0,           seated: true },

  // ── Trading desk (Trader at centre; NPC desks added by office.js) ─────────
  { name: 'Trader',            color: 0xFFD700, desk: new THREE.Vector3( 0,   0,  3) },

  // ── Risk management row (z = 7) ───────────────────────────────────────────
  { name: 'Aggressive Analyst',   color: 0xFF5722, desk: new THREE.Vector3(-5,   0,  7) },
  { name: 'Neutral Analyst',      color: 0x607D8B, desk: new THREE.Vector3( 0,   0,  7) },
  { name: 'Conservative Analyst', color: 0x009688, desk: new THREE.Vector3( 5,   0,  7) },

  // ── Portfolio Manager — inside glass corner office (z = 10–15) ────────────
  { name: 'Portfolio Manager', color: 0xE91E63, desk: new THREE.Vector3( 0,   0,  12) },
];

// ─── CharacterManager ────────────────────────────────────────────────────────

export class CharacterManager {
  constructor(scene) {
    this.scene = scene;
    this.chars = {};

    for (const cfg of AGENT_CONFIGS) {
      const c = new Character(cfg, scene);
      c.hide();
      this.chars[cfg.name] = c;
    }
  }

  showAll() {
    for (const c of Object.values(this.chars)) c.show();
  }

  getCharacter(name) {
    return this.chars[name] || null;
  }

  update(delta) {
    for (const c of Object.values(this.chars)) {
      if (!c.group.visible) continue;
      c.update(delta);
    }
  }
}

// ─── Character ───────────────────────────────────────────────────────────────

class Character {
  constructor(cfg, scene) {
    this.name    = cfg.name;
    this.color   = cfg.color;
    this.deskPos = cfg.desk.clone();

    // homeRotation: direction the character faces when at rest.
    // Default Math.PI = face -Z (toward ticker/display wall).
    this.homeRotation = cfg.homeRotation !== undefined ? cfg.homeRotation : Math.PI;

    // Seated characters sit at their desk position; others stand 1.3 u in front.
    this.homePos = cfg.seated
      ? cfg.desk.clone()
      : cfg.desk.clone().add(new THREE.Vector3(0, 0, 1.3));

    this.group = new THREE.Group();
    this.group.position.copy(this.homePos);
    this.group.rotation.y = this.homeRotation;

    this._buildBody();
    this._buildLabel();
    this._buildThinkCloud();

    scene.add(this.group);

    // Animation state
    this.time      = Math.random() * Math.PI * 2; // phase offset
    this.state     = 'idle';   // idle | thinking | walking
    this._walkTarget   = null;
    this._walkCallback = null;
    this._walkSpeed    = 3.5;  // units/second
    this._dir          = new THREE.Vector3(); // reused each frame to avoid GC pressure
  }

  // ── Geometry builders ──────────────────────────────────────────────────────

  _buildBody() {
    const col  = this.color;
    const skin = 0xf5c2a2;
    const dark = 0x1a1a2e;

    const box = (w, h, d, color) => {
      const m = new THREE.Mesh(
        new THREE.BoxGeometry(w, h, d),
        new THREE.MeshLambertMaterial({ color })
      );
      return m;
    };

    // ── Head ──
    this.head = box(0.38, 0.38, 0.38, skin);
    this.head.position.set(0, 1.47, 0);
    this.group.add(this.head);

    // Hair band (thin strip on top of head, colored per role)
    const hair = box(0.38, 0.06, 0.38, col);
    hair.position.set(0, 0.22, 0);
    this.head.add(hair);

    // ── Torso ──
    this.body = box(0.46, 0.56, 0.22, col);
    this.body.position.set(0, 0.93, 0);
    this.group.add(this.body);

    // ── Arms (pivoted at shoulder so we can rotate them for typing/walking) ──
    this.rightArmPivot = new THREE.Group();
    this.rightArmPivot.position.set(0.305, 1.18, 0);
    const rArm = box(0.15, 0.48, 0.15, col);
    rArm.position.set(0, -0.24, 0);
    this.rightArmPivot.add(rArm);
    this.group.add(this.rightArmPivot);

    this.leftArmPivot = new THREE.Group();
    this.leftArmPivot.position.set(-0.305, 1.18, 0);
    const lArm = box(0.15, 0.48, 0.15, col);
    lArm.position.set(0, -0.24, 0);
    this.leftArmPivot.add(lArm);
    this.group.add(this.leftArmPivot);

    // ── Legs (pivoted at hip) ──
    this.rightLegPivot = new THREE.Group();
    this.rightLegPivot.position.set(0.12, 0.65, 0);
    const rLeg = box(0.18, 0.56, 0.18, dark);
    rLeg.position.set(0, -0.28, 0);
    this.rightLegPivot.add(rLeg);
    this.group.add(this.rightLegPivot);

    this.leftLegPivot = new THREE.Group();
    this.leftLegPivot.position.set(-0.12, 0.65, 0);
    const lLeg = rLeg.clone();
    this.leftLegPivot.add(lLeg);
    this.group.add(this.leftLegPivot);

    // ── Shoes ──
    const rShoe = box(0.22, 0.1, 0.26, 0x111111);
    rShoe.position.set(0.12, 0.05, 0.04);
    this.group.add(rShoe);
    const lShoe = rShoe.clone();
    lShoe.position.set(-0.12, 0.05, 0.04);
    this.group.add(lShoe);

    // ── Document prop (appears in hand during handoff animation) ──
    this.docProp = box(0.28, 0.36, 0.03, 0xf8f8f0);
    this.docProp.position.set(0.42, 1.05, 0.18);
    this.docProp.visible = false;
    this.group.add(this.docProp);
  }

  _buildLabel() {
    const div = document.createElement('div');
    div.className = 'agent-label';
    div.textContent = this.name;
    const hex = '#' + this.color.toString(16).padStart(6, '0');
    div.style.borderColor = hex + '88';
    div.style.boxShadow   = `0 0 4px ${hex}44`;

    this.label = new CSS2DObject(div);
    this.label.position.set(0, 2.3, 0);
    this.group.add(this.label);
  }

  _buildThinkCloud() {
    this.thinkCloud = new THREE.Group();

    // MeshBasicMaterial is unaffected by scene lighting — always bright white
    // regardless of whether the office lights are on or off.
    const cloudMat = new THREE.MeshBasicMaterial({ color: 0xffffff });
    const dotMat   = new THREE.MeshBasicMaterial({ color: 0xcccccc });
    const glowMat  = new THREE.MeshBasicMaterial({
      color: 0xffffff,
      transparent: true,
      opacity: 0.18,
      depthWrite: false,
    });

    const sphereData = [
      [  0,     0.16,  0,    0.26 ],
      [ -0.20,  0.06,  0,    0.20 ],
      [  0.20,  0.08,  0,    0.20 ],
      [ -0.10,  0.30,  0,    0.17 ],
      [  0.11,  0.28,  0,    0.17 ],
    ];
    for (const [x, y, z, r] of sphereData) {
      const s = new THREE.Mesh(new THREE.SphereGeometry(r, 10, 7), cloudMat);
      s.position.set(x, y, z);
      this.thinkCloud.add(s);

      const halo = new THREE.Mesh(new THREE.SphereGeometry(r * 1.9, 10, 7), glowMat);
      halo.position.set(x, y, z);
      this.thinkCloud.add(halo);
    }

    for (let i = 0; i < 3; i++) {
      const r   = 0.07 - i * 0.015;
      const dot = new THREE.Mesh(new THREE.SphereGeometry(r, 7, 5), dotMat);
      dot.position.set(-0.10 + i * 0.10, -0.14 - i * 0.07, 0);
      this.thinkCloud.add(dot);
    }

    this.thinkCloud.position.set(0, 3.0, 0);
    this.thinkCloud.visible = false;
    this.group.add(this.thinkCloud);
  }

  // ── Public API ─────────────────────────────────────────────────────────────

  hide() { this.group.visible = false; }
  show() { this.group.visible = true;  }

  setThinking(on) {
    this.thinkCloud.visible = on;
    if (on && this.state === 'idle') {
      this.state = 'thinking';
    } else if (!on && this.state === 'thinking') {
      this.state = 'idle';
    }
  }

  walkTo(worldPos, callback) {
    this._walkTarget   = new THREE.Vector3(worldPos.x, 0, worldPos.z);
    this._walkCallback = callback || null;
    this.state = 'walking';
    this.thinkCloud.visible = false;
    this.docProp.visible    = false;
  }

  /** Walk back to home position, then restore the character's home facing. */
  goHome(callback) {
    this.walkTo(this.homePos, () => {
      this.group.rotation.y = this.homeRotation;
      if (callback) callback();
    });
  }

  // ── Per-frame update ───────────────────────────────────────────────────────

  update(delta) {
    this.time += delta;
    const t = this.time;

    if (this.state === 'walking') {
      this._stepWalk(delta, t);
    } else {
      this._animateIdle(t);
    }
  }

  _stepWalk(delta, t) {
    const target = this._walkTarget;
    if (!target) { this.state = 'idle'; return; }

    const dir = this._dir.set(
      target.x - this.group.position.x,
      0,
      target.z - this.group.position.z,
    );
    const dist = dir.length();

    if (dist < 0.1) {
      this.group.position.set(target.x, 0, target.z);
      this.state = 'idle';
      const cb = this._walkCallback;
      this._walkCallback = null;
      this._walkTarget   = null;
      if (cb) cb();
      return;
    }

    dir.normalize();
    const step = Math.min(this._walkSpeed * delta, dist);
    this.group.position.addScaledVector(dir, step);
    this.group.position.y = 0;

    this.group.rotation.y = Math.atan2(dir.x, dir.z);

    const swing = Math.sin(t * 9) * 0.45;
    this.rightLegPivot.rotation.x =  swing;
    this.leftLegPivot.rotation.x  = -swing;
    this.rightArmPivot.rotation.x = -swing * 0.6;
    this.leftArmPivot.rotation.x  =  swing * 0.6;
  }

  _animateIdle(t) {
    const typ = t * 2.8;
    this.rightArmPivot.rotation.x = -0.55 + Math.sin(typ)                  * 0.22;
    this.leftArmPivot.rotation.x  = -0.55 + Math.sin(typ + Math.PI * 0.6)  * 0.22;

    this.rightLegPivot.rotation.x = 0;
    this.leftLegPivot.rotation.x  = 0;

    this.head.position.y = 1.47 + Math.sin(t * 1.4) * 0.008;

    if (this.thinkCloud.visible) {
      const p = 1 + Math.sin(t * 3.2) * 0.07;
      this.thinkCloud.scale.setScalar(p);
    }
  }
}
