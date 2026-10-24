/**
 * Opple Lamp Card - a custom Lovelace card for the Huawei HiLink Opple
 * integration, styled after the lamp's own control layout (status bar,
 * lighting-mode row, brightness slider) - an original line-art illustration
 * and CSS, not a copy of the Huawei AI Life app's actual assets.
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

const LAMP_SVG = `
<svg viewBox="0 0 220 160" class="lamp-art" aria-hidden="true">
  <g fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">
    <line x1="40" y1="20" x2="170" y2="20" />
    <line x1="60" y1="20" x2="60" y2="120" />
    <ellipse cx="60" cy="130" rx="46" ry="10" />
  </g>
</svg>`;

class OppleLampCard extends HTMLElement {
  setConfig(config) {
    if (!config.entity) {
      throw new Error("opple-lamp-card: 'entity' (the light) is required");
    }
    this._config = config;
    this._built = false;
  }

  getCardSize() {
    return 5;
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
          padding: 16px 16px 20px;
          border-radius: 18px;
          font-family: var(--paper-font-body1_-_font-family, inherit);
        }
        .opple-card .header {
          text-align: center;
          font-size: 15px;
          opacity: 0.7;
          margin-bottom: 4px;
        }
        .opple-card .lamp-art {
          display: block;
          width: 100%;
          max-width: 220px;
          height: 90px;
          margin: 4px auto 10px;
          color: #e8e8e8;
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
        .opple-card .power-btn {
          width: 44px;
          height: 44px;
          border-radius: 50%;
          border: none;
          background: #2c2c2e;
          color: #9a9a9a;
          display: flex;
          align-items: center;
          justify-content: center;
          cursor: pointer;
          transition: background 0.15s, color 0.15s;
        }
        .opple-card .power-btn.on {
          background: #3a7bd5;
          color: #fff;
        }
        .opple-card .power-btn ha-icon {
          --mdc-icon-size: 22px;
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
        <div class="header"></div>
        ${LAMP_SVG}
        <div class="row-card status-row">
          <div class="status-text"></div>
          <button class="power-btn" title="Power">
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
      </ha-card>
    `;
    this.innerHTML = "";
    this.appendChild(root.firstElementChild ? root : root);
    // move children up (we wrapped in a plain div for innerHTML parsing)
    while (root.firstChild) {
      this.appendChild(root.firstChild);
    }
    this.querySelector(".power-btn").addEventListener("click", () => this._togglePower());
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
      this.querySelector(".status-text").textContent = "Entity not found";
      return;
    }
    const isOn = stateObj.state === "on";
    const isUnknown = stateObj.state === "unknown" || stateObj.state === "unavailable";

    this.querySelector(".header").textContent = cfg.name || stateObj.attributes.friendly_name || "";
    this.querySelector(".status-text").textContent = isUnknown ? "—" : isOn ? "On" : "Off";
    const powerBtn = this.querySelector(".power-btn");
    powerBtn.classList.toggle("on", isOn);

    // Brightness - shown whenever the light is on, even before its current
    // value is known (state is only ever learned from a push after a
    // command; see the GET-on-startup fix in __init__.py). Falls back to a
    // sensible default so the slider is still usable meanwhile, and shows
    // "—" instead of a possibly-wrong percentage until the real value lands.
    const brightnessRow = this.querySelector(".brightness-row");
    if (isOn) {
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

    // Color temperature - same reasoning as brightness above.
    const cctRow = this.querySelector(".cct-row");
    if (isOn) {
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
        row.querySelector("button").addEventListener("click", () => {
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

  _prettyLabel(hass, entityId, option) {
    // Use HA's own translated state label when available, else humanize the raw option.
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
    "Lighting-mode / brightness / side-light control card for the Huawei HiLink Opple lamp integration.",
});
