/**
 * dialog.js — RPG-style agent output dialog boxes.
 *
 * Shows the latest streaming output from active (and recently completed) agents
 * in a row of semi-opaque cards fixed at the bottom of the viewport.
 *
 * Export:
 *   DialogBox(containerEl)
 *     .onAgentActive(agentName)
 *     .onAgentIdle(agentName)
 *     .onAgentMessage(agentName, text)
 *     .reset()
 */

const AGENT_COLORS = {
  'Market Analyst':       '#2196F3',
  'Sentiment Analyst':    '#9C27B0',
  'News Analyst':         '#FF9800',
  'Fundamentals Analyst': '#4CAF50',
  'Bull Researcher':      '#8BC34A',
  'Bear Researcher':      '#F44336',
  'Research Manager':     '#795548',
  'Trader':               '#FFD700',
  'Aggressive Analyst':   '#FF5722',
  'Neutral Analyst':      '#607D8B',
  'Conservative Analyst': '#009688',
  'Portfolio Manager':    '#E91E63',
};

// Completed cards linger this long before fading out
const COMPLETED_LINGER_MS = 9000;

export class DialogBox {
  constructor(containerEl) {
    this._el       = containerEl;
    // Map: agentName → { el, headerEl, textEl, status, fadeTimer }
    this._entries  = new Map();
  }

  /** Called when an agent transitions to active (thinking cloud on). */
  onAgentActive(agentName) {
    const entry = this._getOrCreate(agentName);
    if (entry.fadeTimer) {
      clearTimeout(entry.fadeTimer);
      entry.fadeTimer = null;
    }
    entry.el.style.opacity = '1';
    if (entry.status !== 'active') {
      entry.status = 'active';
      this._renderHeader(agentName);
    }
    this._syncVisibility();
  }

  /** Called when an agent finishes (thinking cloud off). */
  onAgentIdle(agentName) {
    const entry = this._entries.get(agentName);
    if (!entry) return;
    entry.status = 'completed';
    this._renderHeader(agentName);
    // Fade out and remove after linger period
    entry.fadeTimer = setTimeout(() => this._removeEntry(agentName), COMPLETED_LINGER_MS);
  }

  /** Called with new text output for an agent.  Replaces the displayed text. */
  onAgentMessage(agentName, text) {
    const entry = this._getOrCreate(agentName);
    entry.textEl.textContent = text;
    // Auto-scroll to bottom so latest content is visible
    entry.textEl.scrollTop = entry.textEl.scrollHeight;
    this._syncVisibility();
  }

  /** Remove all cards immediately (e.g. on workflow_start). */
  reset() {
    for (const [, entry] of this._entries) {
      if (entry.fadeTimer) clearTimeout(entry.fadeTimer);
      entry.el.remove();
    }
    this._entries.clear();
    this._syncVisibility();
  }

  // ── Internal ────────────────────────────────────────────────────────────────

  _getOrCreate(agentName) {
    if (this._entries.has(agentName)) return this._entries.get(agentName);

    const color = AGENT_COLORS[agentName] || '#8888aa';

    const card = document.createElement('div');
    card.className = 'dialog-card';
    card.style.setProperty('--agent-color', color);

    const headerEl = document.createElement('div');
    headerEl.className = 'dialog-card-header';
    card.appendChild(headerEl);

    const textEl = document.createElement('div');
    textEl.className = 'dialog-card-body';
    card.appendChild(textEl);

    this._el.appendChild(card);

    const entry = { el: card, headerEl, textEl, status: 'active', fadeTimer: null, color };
    this._entries.set(agentName, entry);
    this._renderHeader(agentName);
    return entry;
  }

  _renderHeader(agentName) {
    const entry = this._entries.get(agentName);
    if (!entry) return;
    const isActive = entry.status === 'active';
    const dot      = isActive ? '▶' : '◼';
    const badge    = isActive ? 'ACTIVE' : 'DONE';
    entry.headerEl.innerHTML =
      `<span class="dialog-dot">${dot}</span>` +
      `<span class="dialog-name">${agentName}</span>` +
      `<span class="dialog-badge">${badge}</span>`;
  }

  _removeEntry(agentName) {
    const entry = this._entries.get(agentName);
    if (!entry) return;
    entry.el.style.transition = 'opacity 0.6s';
    entry.el.style.opacity    = '0';
    setTimeout(() => {
      entry.el.remove();
      this._entries.delete(agentName);
      this._syncVisibility();
    }, 650);
  }

  _syncVisibility() {
    this._el.style.display = this._entries.size > 0 ? 'flex' : 'none';
  }
}
