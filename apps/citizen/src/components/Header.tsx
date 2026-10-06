import React from "react";
import { Language, Theme } from "../types";

interface HeaderProps {
  theme: Theme;
  onThemeChange: (t: Theme) => void;
  lang: Language;
  onLangChange: (l: Language) => void;
  onOpenReport: () => void;
  isOnline: boolean;
}

export const Header: React.FC<HeaderProps> = ({
  theme,
  onThemeChange,
  lang,
  onLangChange,
  onOpenReport,
  isOnline,
}) => {
  return (
    <header className="top-bar">
      <div className="brand">
        <span
          className={`health-dot ${isOnline ? "" : "offline"}`}
          title={isOnline ? "Connected to FloodRoute API" : "Offline"}
        />
        <h1>FloodRoute</h1>
      </div>

      <div className="top-controls">
        <button
          type="button"
          className="select-btn"
          onClick={onOpenReport}
          title="Report waterlogged road"
        >
          📷 Report
        </button>

        <select
          className="select-btn"
          value={lang}
          onChange={(e) => onLangChange(e.target.value as Language)}
          aria-label="Language"
        >
          <option value="en">EN</option>
          <option value="hi">हिन्दी</option>
          <option value="kn">ಕನ್ನಡ</option>
          <option value="ta">தமிழ்</option>
          <option value="te">తెలుగు</option>
        </select>

        <select
          className="select-btn"
          value={theme}
          onChange={(e) => onThemeChange(e.target.value as Theme)}
          aria-label="Theme"
        >
          <option value="light">Light</option>
          <option value="dark">Dark</option>
          <option value="sunlight">Sunlight</option>
          <option value="hc">High Contrast</option>
        </select>
      </div>
    </header>
  );
};
