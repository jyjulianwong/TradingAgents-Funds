/**
 * events.js — dispatches WebSocket events from the server to scene mutations.
 *
 * Export:
 *   EventHandler(office, charManager, uiCallbacks)
 *     .handle(event)
 */

export class EventHandler {
  /**
   * @param {object}   office       - officeState returned by buildOffice()
   * @param {object}   charManager  - CharacterManager instance
   * @param {object}   ui           - { onStart, onIdle, onComplete } callbacks
   */
  constructor(office, charManager, ui) {
    this.office           = office;
    this.chars            = charManager;
    this.ui               = ui;
    this._inHandoff       = new Set();
    // Tracks pending doc-show setTimeout IDs keyed by agent name so they can
    // be cancelled when a new handoff fires before the old timer expires.
    // Without this, the stale timer calls goHome() and aborts the new walk.
    this._handoffTimeouts = new Map();
  }

  handle(event) {
    switch (event.type) {
      case 'workflow_idle':
        this.ui.onIdle?.();
        break;

      case 'workflow_start':
        this.ui.onStart?.(event.ticker, event.date);
        break;

      case 'agent_active':
        this._onAgentActive(event.agent);
        break;

      case 'agent_idle':
        this._onAgentIdle(event.agent);
        break;

      case 'agent_message':
        this.ui.onAgentMessage?.(event.agent, event.text);
        break;

      case 'handoff':
        this._onHandoff(event.from, event.to);
        break;

      case 'workflow_complete':
        // Clear all thinking clouds before showing the final result.
        for (const char of Object.values(this.chars.chars)) {
          char.setThinking(false);
        }
        this.ui.onComplete?.(event.signal, event.ticker);
        break;

      case 'ping':
        // keepalive — no action needed
        break;

      default:
        break;
    }
  }

  // ── Handlers ──────────────────────────────────────────────────────────────

  _onAgentActive(agentName) {
    const char = this.chars.getCharacter(agentName);
    if (char) char.setThinking(true);
    this.ui.onAgentActive?.(agentName);
  }

  _onAgentIdle(agentName) {
    const char = this.chars.getCharacter(agentName);
    if (char) char.setThinking(false);
    this.ui.onAgentIdle?.(agentName);
  }

  /**
   * The sender walks to the recipient's desk, shows the document prop briefly,
   * then walks back home.  Meanwhile the recipient's thinking cloud is shown
   * after the sender arrives (via a timeout that matches the walk duration).
   */
  _onHandoff(fromName, toName) {
    const fromChar = this.chars.getCharacter(fromName);
    const toChar   = this.chars.getCharacter(toName);
    if (!fromChar || !toChar) return;

    // If a previous handoff for this character is still in the doc-show phase,
    // cancel its goHome timer before redirecting.  A stale timer firing after
    // walkTo() has already set a new target would call goHome() and abort the
    // new walk mid-stride, producing the cumulative round-robin bug.
    if (this._handoffTimeouts.has(fromName)) {
      clearTimeout(this._handoffTimeouts.get(fromName));
      this._handoffTimeouts.delete(fromName);
      fromChar.docProp.visible = false;
    }

    fromChar.setThinking(false);
    this._inHandoff.add(fromName);

    fromChar.walkTo(toChar.deskPos, () => {
      fromChar.docProp.visible = true;

      const tid = setTimeout(() => {
        this._handoffTimeouts.delete(fromName);
        fromChar.docProp.visible = false;
        fromChar.goHome(() => {
          this._inHandoff.delete(fromName);
        });
      }, 550);
      this._handoffTimeouts.set(fromName, tid);
    });
  }
}
