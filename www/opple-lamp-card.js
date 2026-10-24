/**
 * Opple Lamp Card - a custom Lovelace card for the Huawei HiLink Opple
 * integration. Renders as a compact tile (icon, name, on/off state, power
 * toggle) like the default dashboard light tiles - tapping it opens a
 * dialog with the full controls (lighting mode, brightness, color
 * temperature, backlight/night light), styled after the lamp's own layout.
 * Original line-art illustration and CSS - not a copy of the Huawei AI Life
 * app's actual assets.
 *
 * Install:
 *   1. Copy this file to <config>/www/opple-lamp-card.js
 *   2. Settings -> Dashboards -> top-right ⋮ -> Resources -> Add resource
 *        URL: /local/opple-lamp-card.js
 *        Resource type: JavaScript module
 *   3. Add a card with type: custom:opple-lamp-card, e.g.:
 *
 *   type: custom:opple-lamp-card
 *   entity: light.opple_lamp_left
 *   mode_entity: select.opple_lamp_left_lighting_mode
 *   backlight_entity: switch.opple_lamp_left_backlight
 *   night_entity: switch.opple_lamp_left_night_light
 *   name: Opple Lamp Left
 *
 * Only `entity` is required - the others are optional and simply hide their
 * row if not configured.
 */

const MODE_ICONS = {
  reading: "mdi:book-open-page-variant-outline",
  writing: "mdi:pencil-outline",
  computer: "mdi:monitor",
  custom: "mdi:tune-variant",
};

const MODE_ORDER = ["reading", "writing", "computer", "custom"];

class OppleLampCard extends HTMLElement {
  setConfig(config) {
    if (!config.entity) {
      throw new Error("opple-lamp-card: 'entity' (the light) is required");
    }
    this._config = config;
    this._built = false;
  }

  getCardSize() {
    return 2;
  }

  connectedCallback() {
    // Some Lovelace views re-add the card element without rebuilding it
    // (e.g. after a brief removal during a dashboard re-render). Make sure
    // the dialog - which lives outside this element, see _build() - comes
    // back with it.
    if (this._built && this._dialog && !this._dialog.isConnected) {
      document.body.appendChild(this._dialog);
    }
  }

  disconnectedCallback() {
    // The dialog was moved to <body> (see _build()), so it isn't cleaned up
    // automatically when this card is removed - do it ourselves to avoid
    // leaving an orphaned dialog behind.
    if (this._dialog && this._dialog.parentNode) {
      this._dialog.parentNode.removeChild(this._dialog);
    }
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._built) {
      try {
        this._build();
        this._built = true;
      } catch (err) {
        // Fail loud: a silent exception here would otherwise just leave the
        // card half-wired (e.g. the tile's click listener never attached),
        // which looks like "nothing happens when I tap it" with no clue why.
        console.error("opple-lamp-card: failed to build card", err);
        return;
      }
    }
    try {
      this._render();
    } catch (err) {
      console.error("opple-lamp-card: failed to render card", err);
    }
  }

  _build() {
    const root = document.createElement("div");
    root.innerHTML = `
      <style>
        /* Every color below comes from Home Assistant's own theme custom
           properties (with a sane fallback for themes that don't set a
           given one), instead of hardcoded hex values - so the card
           follows whatever theme/skin is active, light or dark, instead of
           always rendering as a fixed near-black panel. */
        ha-card.opple-card {
          background: var(--ha-card-background, var(--card-background-color, #1c1c1e));
          color: var(--primary-text-color, #e1e1e1);
          border-radius: var(--ha-card-border-radius, 12px);
          box-shadow: var(--ha-card-box-shadow, none);
          border: var(--ha-card-border-width, 1px) solid var(--ha-card-border-color, var(--divider-color, transparent));
          font-family: var(--paper-font-body1_-_font-family, inherit);
          overflow: visible;
        }

        /* ---- Compact tile (default card view) ---- */
        .tile {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 12px 14px;
          cursor: pointer;
        }
        .tile-icon {
          width: 40px;
          height: 40px;
          border-radius: 50%;
          background: var(--secondary-background-color, #2c2c2e);
          display: flex;
          align-items: center;
          justify-content: center;
          flex-shrink: 0;
          color: var(--secondary-text-color, #9a9a9a);
          transition: background 0.15s, color 0.15s;
        }
        .tile-icon.on {
          background: rgba(var(--rgb-primary-color, 58, 123, 213), 0.2);
          color: var(--state-icon-active-color, var(--primary-color, #3a7bd5));
        }
        .tile-info {
          flex: 1;
          min-width: 0;
        }
        .tile-name {
          font-size: 14px;
          font-weight: 500;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .tile-state {
          font-size: 12.5px;
          color: var(--secondary-text-color, #9a9a9a);
        }

        /* ---- Shared power-button style (tile toggle + dialog rows) ---- */
        .opple-card .power-btn {
          width: 40px;
          height: 40px;
          border-radius: 50%;
          border: none;
          background: var(--secondary-background-color, #2c2c2e);
          color: var(--secondary-text-color, #9a9a9a);
          display: flex;
          align-items: center;
          justify-content: center;
          cursor: pointer;
          transition: background 0.15s, color 0.15s, transform 0.1s;
          flex-shrink: 0;
        }
        .opple-card .power-btn:active {
          transform: scale(0.92);
        }
        .opple-card .power-btn.on {
          background: var(--primary-color, #3a7bd5);
          color: var(--text-primary-color, #fff);
        }
        .opple-card .power-btn ha-icon {
          --mdc-icon-size: 20px;
        }

        /* ---- Dialog (opened by tapping the tile) ---- */
        /* A native <dialog> shown via showModal() is promoted to the
           browser's "top layer" - a stacking level that sits above the
           entire regular document, by specification, regardless of any
           ancestor's position/transform/z-index/overflow. That sidesteps
           custom themes (page-transition transforms on <body>/<html>,
           blur/filter tricks, etc.) that broke a hand-rolled
           position:fixed overlay. The backdrop itself is the browser's
           native ::backdrop pseudo-element - also unaffected by theme CSS. */
        dialog.dialog {
          margin: auto;
          width: 100%;
          max-width: 360px;
          max-height: 90vh;
          overflow-y: auto;
          background: var(--ha-dialog-surface-background, var(--mdc-theme-surface, var(--card-background-color, #1c1c1e)));
          color: var(--primary-text-color, #e1e1e1);
          border: none;
          border-radius: var(--ha-dialog-border-radius, 28px);
          box-shadow: var(--ha-dialog-box-shadow, 0 11px 15px -7px rgba(0, 0, 0, 0.2), 0 24px 38px 3px rgba(0, 0, 0, 0.14), 0 9px 46px 8px rgba(0, 0, 0, 0.12));
          padding: 16px 16px 20px;
          box-sizing: border-box;
        }
        dialog.dialog::backdrop {
          background: rgba(0, 0, 0, 0.32);
          backdrop-filter: blur(2px);
          -webkit-backdrop-filter: blur(2px);
        }
        .opple-card .dialog-topbar {
          display: flex;
          align-items: center;
          gap: 10px;
          margin-bottom: 14px;
        }
        .dialog-close {
          width: 32px;
          height: 32px;
          border-radius: 50%;
          border: none;
          background: var(--secondary-background-color, #2c2c2e);
          color: var(--primary-text-color, #e8e8e8);
          display: flex;
          align-items: center;
          justify-content: center;
          cursor: pointer;
          flex-shrink: 0;
        }
        .opple-card .header {
          text-align: left;
          min-width: 0;
        }
        .opple-card .header-area {
          font-size: 12.5px;
          color: var(--secondary-text-color, #9a9a9a);
          margin-bottom: 2px;
        }
        .opple-card .header-name {
          font-size: 16px;
          font-weight: 600;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .opple-card .row-card {
          background: var(--secondary-background-color, #2c2c2e);
          border-radius: 14px;
          padding: 14px 16px;
          margin-bottom: 10px;
        }
        .opple-card .status-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
        }
        .opple-card .status-text {
          font-size: 20px;
          font-weight: 600;
        }
        .opple-card .mode-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(56px, 1fr));
          gap: 10px;
        }
        .opple-card .mode-btn {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 6px;
          background: none;
          border: none;
          color: var(--secondary-text-color, #b5b5b7);
          cursor: pointer;
          padding: 4px 0;
        }
        .opple-card .mode-btn .circle {
          width: 48px;
          height: 48px;
          border-radius: 50%;
          border: 1.5px solid var(--divider-color, #3a3a3c);
          display: flex;
          align-items: center;
          justify-content: center;
        }
        .opple-card .mode-btn.active .circle {
          border-color: var(--primary-color, #3a7bd5);
          background: rgba(var(--rgb-primary-color, 58, 123, 213), 0.15);
        }
        .opple-card .mode-btn.active {
          color: var(--primary-text-color, #f2f2f2);
        }
        .opple-card .mode-btn span.label {
          font-size: 11.5px;
        }
        .opple-card .brightness-row {
          margin-top: 4px;
        }
        .opple-card .brightness-label {
          display: flex;
          justify-content: space-between;
          font-size: 13px;
          color: var(--secondary-text-color, #b5b5b7);
          margin-bottom: 8px;
        }
        .opple-card input[type="range"] {
          -webkit-appearance: none;
          width: 100%;
          height: 4px;
          border-radius: 2px;
          background: var(--divider-color, #3a3a3c);
          outline: none;
        }
        .opple-card input[type="range"]::-webkit-slider-thumb {
          -webkit-appearance: none;
          width: 20px;
          height: 20px;
          border-radius: 50%;
          background: var(--primary-color, #f2f2f2);
          cursor: pointer;
        }
        .opple-card input[type="range"].warm-cool {
          background: linear-gradient(to right, #ffb454, #fff4e0, #cfe8ff);
        }
        .opple-card .toggle-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 6px 0;
        }
        .opple-card .toggle-row + .toggle-row {
          border-top: 1px solid var(--divider-color, #2c2c2e);
        }
        .opple-card .toggle-row .label {
          font-size: 14px;
        }
      </style>
      <ha-card class="opple-card">
        <div class="tile">
          <div class="tile-icon"><ha-icon icon="mdi:desk-lamp"></ha-icon></div>
          <div class="tile-info">
            <div class="tile-name"></div>
            <div class="tile-state"></div>
          </div>
          <button class="power-btn tile-toggle" title="Power">
            <ha-icon icon="mdi:power"></ha-icon>
          </button>
        </div>
        <dialog class="dialog">
          <div class="dialog-topbar">
            <button class="dialog-close" title="Close"><ha-icon icon="mdi:close"></ha-icon></button>
            <div class="header">
              <div class="header-area"></div>
              <div class="header-name"></div>
            </div>
          </div>
          <div class="row-card status-row">
            <div class="status-text"></div>
            <button class="power-btn dialog-toggle" title="Power">
              <ha-icon icon="mdi:power"></ha-icon>
            </button>
          </div>
          <div class="row-card mode-row" style="display:none">
            <div class="mode-grid"></div>
          </div>
          <div class="row-card brightness-row" style="display:none">
            <div class="brightness-label">
              <span>Brightness</span>
              <span class="brightness-value"></span>
            </div>
            <input type="range" min="1" max="100" step="1" class="brightness-slider" />
          </div>
          <div class="row-card cct-row" style="display:none">
            <div class="brightness-label">
              <span>Color temperature</span>
              <span class="cct-value"></span>
            </div>
            <input type="range" step="50" class="cct-slider warm-cool" />
          </div>
          <div class="row-card extra-row" style="display:none"></div>
        </dialog>
      </ha-card>
    `;
    this.innerHTML = "";
    while (root.firstChild) {
      this.appendChild(root.firstChild);
    }

    const dialogEl = this.querySelector("dialog.dialog");
    // Move the dialog to <body>. showModal() alone already promotes it to
    // the top layer (see the big CSS comment above) regardless of where in
    // the DOM it lives, but keeping it under <body> avoids any lingering
    // layout/clipping quirks from its original parent and keeps behavior
    // consistent across browsers.
    document.body.appendChild(dialogEl);
    this._dialog = dialogEl;

    this.querySelector(".tile").addEventListener("click", (e) => {
      if (e.target.closest(".tile-toggle")) return; // toggle handled separately, doesn't open the dialog
      console.debug("opple-lamp-card: tile tapped, opening dialog for", this._config.entity);
      dialogEl.showModal();
    });
    dialogEl.querySelector(".dialog-close").addEventListener("click", () => dialogEl.close());
    // Click-outside-to-close: a click that lands on the <dialog> element
    // itself (rather than bubbling up from one of its children) means it
    // hit the backdrop area, since the dialog's own box only covers its
    // rendered content.
    dialogEl.addEventListener("click", (e) => {
      if (e.target === dialogEl) dialogEl.close();
    });

    [this.querySelector(".tile-toggle"), dialogEl.querySelector(".dialog-toggle")].forEach((btn) =>
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        this._togglePower();
      })
    );
    dialogEl.querySelector(".brightness-slider").addEventListener("change", (e) =>
      this._setBrightness(Number(e.target.value))
    );
    dialogEl.querySelector(".brightness-slider").addEventListener("input", (e) => {
      dialogEl.querySelector(".brightness-value").textContent = `${e.target.value}%`;
    });
    dialogEl.querySelector(".cct-slider").addEventListener("change", (e) =>
      this._setColorTemp(Number(e.target.value))
    );
    dialogEl.querySelector(".cct-slider").addEventListener("input", (e) => {
      dialogEl.querySelector(".cct-value").textContent = `${e.target.value} K`;
    });

    console.debug("opple-lamp-card: build complete for", this._config.entity);
  }

  _render() {
    const hass = this._hass;
    const cfg = this._config;
    const dialogEl = this._dialog;
    const stateObj = hass.states[cfg.entity];
    if (!stateObj) {
      this.querySelector(".tile-name").textContent = "Entity not found";
      return;
    }
    const isOn = stateObj.state === "on";
    const isUnknown = stateObj.state === "unknown" || stateObj.state === "unavailable";
    const name = cfg.name || stateObj.attributes.friendly_name || "";
    const stateLabel = isUnknown ? "—" : isOn ? "On" : "Off";

    // Compact tile
    this.querySelector(".tile-name").textContent = name;
    this.querySelector(".tile-state").textContent = stateLabel;
    this.querySelector(".tile-icon").classList.toggle("on", isOn);
    [...this.querySelectorAll(".power-btn"), ...dialogEl.querySelectorAll(".power-btn")].forEach(
      (btn) => btn.classList.toggle("on", isOn)
    );

    // Dialog header: area name (small, like the default light tile's detail
    // view) above the entity/friendly name. The dialog itself lives in
    // <body>, not under this element - see _build() - so it's queried from
    // `dialogEl`, not `this`.
    dialogEl.querySelector(".header-area").textContent = this._areaName(hass, cfg.entity);
    dialogEl.querySelector(".header-name").textContent = name;
    dialogEl.querySelector(".status-text").textContent = stateLabel;

    // In "Computer" lighting mode only the side light (backlight) is on and
    // the main light entity itself reports "off" - but brightness still
    // applies to whichever point is actually lit (see the project doc's
    // "Observation importante" note). So brightness stays visible whenever
    // EITHER the main light or the backlight is on, not just the main light.
    const backlightOn =
      cfg.backlight_entity &&
      hass.states[cfg.backlight_entity] &&
      hass.states[cfg.backlight_entity].state === "on";
    const anyLightOn = isOn || backlightOn;
    // Color temperature is tied to the *lighting mode*, not on/off state: in
    // "Computer" mode the lamp runs off the side light only, which has no
    // tunable color temperature - so cct is hidden specifically in that mode,
    // shown in every other mode (as long as the main light is on).
    const currentMode =
      cfg.mode_entity && hass.states[cfg.mode_entity] && hass.states[cfg.mode_entity].state;
    const cctAllowed = currentMode !== "computer";

    // Brightness - shown whenever the main light or the backlight is on,
    // even before its current value is known (state is only ever learned
    // from a push after a command; see the GET-on-startup fix in
    // __init__.py). Falls back to a sensible default so the slider is still
    // usable meanwhile, and shows "—" instead of a possibly-wrong percentage
    // until the real value lands.
    const brightnessRow = dialogEl.querySelector(".brightness-row");
    if (anyLightOn) {
      brightnessRow.style.display = "";
      const known = stateObj.attributes.brightness != null;
      const pct = known ? Math.round((stateObj.attributes.brightness / 255) * 100) : 50;
      const slider = dialogEl.querySelector(".brightness-slider");
      if (document.activeElement !== slider) {
        slider.value = pct;
      }
      dialogEl.querySelector(".brightness-value").textContent = known ? `${pct}%` : "—";
    } else {
      brightnessRow.style.display = "none";
    }

    // Color temperature - see cctAllowed above.
    const cctRow = dialogEl.querySelector(".cct-row");
    if (isOn && cctAllowed) {
      cctRow.style.display = "";
      const min = stateObj.attributes.min_color_temp_kelvin || 2700;
      const max = stateObj.attributes.max_color_temp_kelvin || 5700;
      const known = stateObj.attributes.color_temp_kelvin != null;
      const value = known ? stateObj.attributes.color_temp_kelvin : Math.round((min + max) / 2);
      const slider = dialogEl.querySelector(".cct-slider");
      slider.min = min;
      slider.max = max;
      if (document.activeElement !== slider) {
        slider.value = value;
      }
      dialogEl.querySelector(".cct-value").textContent = known ? `${value} K` : "—";
    } else {
      cctRow.style.display = "none";
    }

    // Lighting mode row
    const modeRow = dialogEl.querySelector(".mode-row");
    const modeGrid = dialogEl.querySelector(".mode-grid");
    if (cfg.mode_entity && hass.states[cfg.mode_entity]) {
      const modeState = hass.states[cfg.mode_entity];
      modeRow.style.display = "";
      const options = modeState.attributes.options || MODE_ORDER;
      modeGrid.innerHTML = "";
      options
        .slice()
        .sort((a, b) => MODE_ORDER.indexOf(a) - MODE_ORDER.indexOf(b))
        .forEach((option) => {
          const btn = document.createElement("button");
          btn.className = "mode-btn" + (modeState.state === option ? " active" : "");
          const label = this._prettyLabel(hass, cfg.mode_entity, option);
          btn.innerHTML = `
            <span class="circle"><ha-icon icon="${MODE_ICONS[option] || "mdi:lightbulb-outline"}"></ha-icon></span>
            <span class="label">${label}</span>
          `;
          btn.addEventListener("click", () => this._setMode(option));
          modeGrid.appendChild(btn);
        });
    } else {
      modeRow.style.display = "none";
    }

    // Backlight / night light toggles
    const extraRow = dialogEl.querySelector(".extra-row");
    const extras = [
      { key: "backlight_entity", label: "Side lamp" },
      { key: "night_entity", label: "Night light" },
    ].filter((e) => cfg[e.key] && hass.states[cfg[e.key]]);
    if (extras.length) {
      extraRow.style.display = "";
      extraRow.innerHTML = "";
      extras.forEach(({ key, label }) => {
        const entityId = cfg[key];
        const st = hass.states[entityId];
        const row = document.createElement("div");
        row.className = "toggle-row";
        row.innerHTML = `
          <span class="label">${label}</span>
          <button class="power-btn ${st.state === "on" ? "on" : ""}" style="width:36px;height:36px">
            <ha-icon icon="mdi:power" style="--mdc-icon-size:18px"></ha-icon>
          </button>
        `;
        row.querySelector("button").addEventListener("click", (e) => {
          e.stopPropagation();
          hass.callService("switch", st.state === "on" ? "turn_off" : "turn_on", {
            entity_id: entityId,
          });
        });
        extraRow.appendChild(row);
      });
    } else {
      extraRow.style.display = "none";
    }
  }

  _areaName(hass, entityId) {
    // Mirrors what the default light tile's detail (more-info) view shows
    // above the entity name: the area it's assigned to, via entity -> device
    // -> area, falling back to a direct entity -> area assignment.
    try {
      const entity = hass.entities && hass.entities[entityId];
      if (!entity) return "";
      let areaId = entity.area_id;
      if (!areaId && entity.device_id && hass.devices) {
        const device = hass.devices[entity.device_id];
        areaId = device && device.area_id;
      }
      if (!areaId || !hass.areas) return "";
      const area = hass.areas[areaId];
      return (area && area.name) || "";
    } catch (e) {
      return "";
    }
  }

  _prettyLabel(hass, entityId, option) {
    // Use HA's own translated state label (follows the account's language,
    // e.g. "Ordinateur" for French) when available, else humanize the raw option.
    const stateObj = hass.states[entityId];
    const translated =
      stateObj &&
      hass.formatEntityState &&
      (() => {
        try {
          return hass.formatEntityState({ ...stateObj, state: option });
        } catch (e) {
          return null;
        }
      })();
    if (translated) return translated;
    return option
      .replace(/_/g, " ")
      .replace(/\b\w/g, (c) => c.toUpperCase());
  }

  _togglePower() {
    const cfg = this._config;
    const isOn = this._hass.states[cfg.entity].state === "on";
    this._hass.callService("light", isOn ? "turn_off" : "turn_on", {
      entity_id: cfg.entity,
    });
  }

  _setBrightness(pct) {
    this._hass.callService("light", "turn_on", {
      entity_id: this._config.entity,
      brightness_pct: pct,
    });
  }

  _setColorTemp(kelvin) {
    this._hass.callService("light", "turn_on", {
      entity_id: this._config.entity,
      color_temp_kelvin: kelvin,
    });
  }

  _setMode(option) {
    this._hass.callService("select", "select_option", {
      entity_id: this._config.mode_entity,
      option,
    });
  }
}

// Guard against double-registration: if the resource somehow gets loaded
// twice (e.g. a leftover duplicate entry under Settings -> Dashboards ->
// Resources pointing at an older ?v=N of this same file), a second
// `customElements.define` call for the same tag throws and silently aborts
// the rest of that script - which can leave the dashboard running a stale,
// half-broken copy of this card with no visible error. Skip re-defining
// instead of crashing.
if (!customElements.get("opple-lamp-card")) {
  customElements.define("opple-lamp-card", OppleLampCard);
} else {
  console.warn(
    "opple-lamp-card: already registered - check Settings > Dashboards > Resources " +
      "for more than one entry pointing at opple-lamp-card.js (different ?v=N values " +
      "count as different entries) and remove the stale one(s)."
  );
}

window.customCards = window.customCards || [];
window.customCards.push({
  type: "opple-lamp-card",
  name: "Opple Lamp Card",
  description:
    "Compact tile for the Huawei HiLink Opple lamp integration - tap to open the full lighting-mode / brightness / color temperature / side-light controls.",
});
