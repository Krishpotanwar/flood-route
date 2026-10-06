import React from "react";
import { Language, Theme } from "../types";

interface HeaderProps {
  theme: Theme;
  onThemeChange: (t: Theme) => void;
  lang: Language;
  onLangChange: (l: Language) => void;
  city: string;
  onCityChange: (c: string) => void;
  onOpenReport: () => void;
  isOnline: boolean;
}

export const Header: React.FC<HeaderProps> = ({
  theme,
  onThemeChange,
  city,
  onCityChange,
  onOpenReport,
  isOnline,
}) => {
  return (
    <header className="top-bar">
      <a className="brand brand-wordmark" href="#top" aria-label="FloodRoute home">
        <span
          className={`health-dot ${isOnline ? "" : "offline"}`}
          role="img"
          aria-label={isOnline ? "Routing service connected" : "Routing service unavailable"}
        />
        <span>FloodRoute<span aria-hidden="true">.</span></span>
      </a>

      <nav className="top-nav" aria-label="Main navigation">
        <a href="#planner">Route planner</a>
        <a href="#conditions">Road conditions</a>
        <a href="#how-it-works">How it works</a>
      </nav>

      <div className="top-controls">
        <select
          className="select-btn"
          value={city}
          onChange={(e) => onCityChange(e.target.value)}
          aria-label="Select City"
        >
          <option value="bengaluru">Bengaluru</option>
          <option value="mumbai">Mumbai</option>
          <option value="gurugram">Gurugram</option>
        </select>

        <button
          type="button"
          className="select-btn"
          onClick={onOpenReport}
          aria-label="Report a waterlogged road"
        >
          Report road <span aria-hidden="true">↗</span>
        </button>

        <select
          className="select-btn"
          value="en"
          disabled
          aria-label="Language"
          title="English preview"
        >
          <option value="en">EN</option>
        </select>

        <select
          className="select-btn"
          value={theme}
          onChange={(e) => onThemeChange(e.target.value as Theme)}
          aria-label="Theme"
        >
          <option value="light">White</option>
          <option value="dark">Black</option>
        </select>
      </div>
    </header>
  );
};
