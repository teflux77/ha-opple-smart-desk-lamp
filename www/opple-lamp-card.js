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

  set hass(hass) {
    this._hass = hass;
    if (!this._built) {
      this._build();
      this._built = true;
    }
    this._render();
  }

  _build() {
    const root = document.createElement("div");
    root.innerHTML = `
      <style>
        ha-card.opple-card {
          background: #0b0b0c;
          color: #f2f2f2;
          border-radius: 18px;
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
          background: #2c2c2e;
          display: flex;
          align-items: center;
          justify-content: center;
          flex-shrink: 0;
          color: #9a9a9a;
          transition: background 0.15s, color 0.15s;
        }
        .tile-icon.on {
          background: #3a7bd533;
          color: #5b9bff;
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
          opacity: 0.6;
        }

        /* ---- Shared power-button style (tile toggle + dialog rows) ---- */
        .opple-card .power-btn {
          width: 40px;
          height: 40px;
          border-radius: 50%;
          border: none;
          background: #2c2c2e;
          color: #9a9a9a;
          display: flex;
          align-items: center;
          justify-content: center;
          cursor: pointer;
          transition: background 0.15s, color 0.15s;
          flex-shrink: 0;
        }
        .opple-card .power-btn.on {
          background: #3a7bd5;
          color: #fff;
        }
        .opple-card .power-btn ha-icon {
          --mdc-icon-size: 20px;
        }

        /* ---- Overlay / dialog (opened by tapping the tile) ---- */
        .overlay {
          position: fixed;
          inset: 0;
          background: rgba(0, 0, 0, 0.65);
          display: none;
          align-items: center;
          justify-content: center;
          z-index: 100;
          padding: 16px;
          box-sizing: border-box;
        }
        .overlay.open {
          display: flex;
        }
        .dialog {
          position: relative;
          width: 100%;
          max-width: 360px;
          max-height: 90vh;
          overflow-y: auto;
          background: #0b0b0c;
          border-radius: 18px;
          padding: 16px 16px 20px;
          box-sizing: border-box;
        }
        .dialog-close {
          position: absolute;
          top: 10px;
          right: 10px;
          width: 32px;
          height: 32px;
          border-radius: 50%;
          border: none;
          background: #2c2c2e;
          color: #e8e8e8;
          display: flex;
          align-items: center;
          justify-content: center;
          cursor: pointer;
          z-index: 1;
        }
        .opple-card .header {
          text-align: center;
          margin-bottom: 12px;
        }
        .opple-card .header-area {
          font-size: 12.5px;
          opacity: 0.6;
          margin-bottom: 2px;
        }
        .opple-card .header-name {
          font-size: 16px;
          font-weight: 600;
        }
        .opple-card .row-card {
          background: #1c1c1e;
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
          color: #b5b5b7;
          cursor: pointer;
          padding: 4px 0;
        }
        .opple-card .mode-btn .circle {
          width: 48px;
          height: 48px;
          border-radius: 50%;
          border: 1.5px solid #3a3a3c;
          display: flex;
          align-items: center;
          justify-content: center;
        }
        .opple-card .mode-btn.active .circle {
          border-color: #f2f2f2;
          background: #2c2c2e;
        }
        .opple-card .mode-btn.active {
          color: #f2f2f2;
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
          opacity: 0.75;
          margin-bottom: 8px;
        }
        .opple-card input[type="range"] {
          -webkit-appearance: none;
          width: 100%;
          height: 4px;
          border-radius: 2px;
          background: #3a3a3c;
          outline: none;
        }
        .opple-card input[type="range"]::-webkit-slider-thumb {
          -webkit-appearance: none;
          width: 20px;
          height: 20px;
          border-radius: 50%;
          background: #f2f2f2;
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
          border-top: 1px solid #2c2c2e;
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
        <div class="overlay">
          <div class="dialog">
            <button class="dialog-close" title="Close"><ha-icon icon="mdi:close"></ha-icon></button>
            <div class="header">
              <div class="header-area"></div>
              <div class="header-name"></div>
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
          </div>
        </div>
      </ha-card>
    `;
    this.innerHTML = "";
    while (root.firstChild) {
      this.appendChild(root.firstChild);
    }

    const overlay = this.querySelector(".overlay");
    this.querySelector(".tile").addEventListener("click", (e) => {
      if (e.target.closest(".tile-toggle")) return; // toggle handled separately, doesn't open the dialog
      overlay.classList.add("open");
    });
    this.querySelector(".dialog-close").addEventListener("click", () =>
      overlay.classList.remove("open")
    );
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) overlay.classList.remove("open"); // backdrop click closes it
    });

    this.querySelectorAll(".power-btn").forEach((btn) =>
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        this._togglePower();
      })
    );
    this.querySelector(".brightness-slider").addEventListener("change", (e) =>
      this._setBrightness(Number(e.target.value))
    );
    this.querySelector(".brightness-slider").addEventListener("input", (e) => {
      this.querySelector(".brightness-value").textContent = `${e.target.value}%`;
    });
    this.querySelector(".cct-slider").addEventListener("change", (e) =>
      this._setColorTemp(Number(e.target.value))
    );
    this.querySelector(".cct-slider").addEventListener("input", (e) => {
      this.querySelector(".cct-value").textContent = `${e.target.value} K`;
    });
  }

  _render() {
    const hass = this._hass;
    const cfg = this._config;
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
    this.querySelectorAll(".power-btn").forEach((btn) => btn.classList.toggle("on", isOn));

    // Dialog header: area name (small, like the default light tile's detail
    // view) above the entity/friendly name.
    this.querySelector(".header-area").textContent = this._areaName(hass, cfg.entity);
    this.querySelector(".header-name").textContent = name;
    this.querySelector(".status-text").textContent = stateLabel;

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
    const brightnessRow = this.querySelector(".brightness-row");
    if (anyLightOn) {
      brightnessRow.style.display = "";
      const known = stateObj.attributes.brightness != null;
      const pct = known ? Math.round((stateObj.attributes.brightness / 255) * 100) : 50;
      const slider = this.querySelector(".brightness-slider");
      if (document.activeElement !== slider) {
        slider.value = pct;
      }
      this.querySelector(".brightness-value").textContent = known ? `${pct}%` : "—";
    } else {
      brightnessRow.style.display = "none";
    }

    // Color temperature - see cctAllowed above.
    const cctRow = this.querySelector(".cct-row");
    if (isOn && cctAllowed) {
      cctRow.style.display = "";
      const min = stateObj.attributes.min_color_temp_kelvin || 2700;
      const max = stateObj.attributes.max_color_temp_kelvin || 5700;
      const known = stateObj.attributes.color_temp_kelvin != null;
      const value = known ? stateObj.attributes.color_temp_kelvin : Math.round((min + max) / 2);
      const slider = this.querySelector(".cct-slider");
      slider.min = min;
      slider.max = max;
      if (document.activeElement !== slider) {
        slider.value = value;
      }
      this.querySelector(".cct-value").textContent = known ? `${value} K` : "—";
    } else {
      cctRow.style.display = "none";
    }

    // Lighting mode row
    const modeRow = this.querySelector(".mode-row");
    const modeGrid = this.querySelector(".mode-grid");
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
    const extraRow = this.querySelector(".extra-row");
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

customElements.define("opple-lamp-card", OppleLampCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "opple-lamp-card",
  name: "Opple Lamp Card",
  description:
    "Compact tile for the Huawei HiLink Opple lamp integration - tap to open the full lighting-mode / brightness / color temperature / side-light controls.",
});
