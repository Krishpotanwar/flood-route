export function HeroRoutePreview({ city }: { city: string }) {
  return (
    <figure className="hero-route-preview">
      <svg viewBox="0 0 1320 310" role="img" aria-labelledby="hero-route-title" preserveAspectRatio="xMidYMid meet">
        <title id="hero-route-title">Route illustration avoiding a sample closure. This is not live road data.</title>
        <defs>
          <pattern id="preview-streets" width="62" height="54" patternUnits="userSpaceOnUse" patternTransform="rotate(-11)">
            <path d="M0 0H62V54H0ZM21 0V54M0 28H62" fill="none" stroke="var(--hairline)" strokeWidth=".7" />
            <path d="M5 5H16V20H5ZM28 7H54V22H28ZM29 34H53V47H29" fill="var(--fr-canvas)" stroke="var(--hairline)" strokeWidth=".5" />
          </pattern>
          <pattern id="preview-closure" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(35)">
            <path d="M0 0V8" stroke="var(--fr-impassable-ink)" strokeWidth="3" />
          </pattern>
          <marker id="preview-arrow" markerWidth="8" markerHeight="8" refX="4" refY="4" orient="auto" markerUnits="userSpaceOnUse">
            <path d="M1 1L5 4L1 7" fill="none" stroke="var(--fr-ink)" strokeWidth="1.5" />
          </marker>
        </defs>
        <rect width="1320" height="310" fill="var(--fr-surface-elevated)" />
        <rect width="1320" height="310" fill="url(#preview-streets)" opacity=".9" />
        <g fill="none" stroke="var(--hairline)" strokeWidth="8">
          <path d="M-30 222C204 251 286 59 514 91S866 280 1350 197" />
          <path d="M108 -30C190 95 347 88 489 254L550 350" />
          <path d="M939 -20C856 77 1033 157 953 341" />
          <path d="M-30 112C169 86 297 151 443 138L735 139L890 120L1350 131" />
        </g>
        <path d="M1064 0C1030 36 1062 68 1047 105C1033 141 1014 140 1024 170C1036 207 1080 242 1049 310" fill="none" stroke="var(--hairline)" strokeWidth="22" opacity=".55" />
        <g fill="var(--fr-ink-2)" fontSize="14" fontFamily="var(--fr-font-sans)">
          <text x="227" y="102">Start area</text>
          <text x="904" y="92">Destination area</text>
          <text x="427" y="276">Alternative corridor</text>
        </g>
        <rect x="559" y="128" width="126" height="22" fill="url(#preview-closure)" />
        <path d="M86 132C155 126 180 143 228 138L390 138Q408 138 408 158L408 185Q408 209 433 209L590 209L702 209Q724 209 725 230L725 246Q725 267 749 258L810 197Q823 183 843 183L920 183Q950 183 950 162L950 149Q950 132 971 132L1231 132" fill="none" stroke="var(--fr-canvas)" strokeWidth="9" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M86 132C155 126 180 143 228 138L390 138Q408 138 408 158L408 185Q408 209 433 209L590 209L702 209Q724 209 725 230L725 246Q725 267 749 258L810 197Q823 183 843 183L920 183Q950 183 950 162L950 149Q950 132 971 132L1231 132" fill="none" stroke="var(--fr-ink)" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" markerEnd="url(#preview-arrow)" />
        <path d="M568 209H590" stroke="var(--fr-ink)" strokeWidth="4" markerEnd="url(#preview-arrow)" />
        <g fill="var(--fr-ink)" stroke="var(--fr-canvas)" strokeWidth="3">
          <circle cx="86" cy="132" r="9" /><circle cx="1231" cy="132" r="9" />
        </g>
        <g fill="var(--fr-ink)" fontSize="18" fontWeight="500" fontFamily="var(--fr-font-sans)">
          <text x="86" y="108">Start</text><text x="1231" y="108" textAnchor="end">Destination</text>
        </g>
        <path d="M622 124V105" stroke="var(--fr-impassable-ink)" />
        <text x="622" y="92" textAnchor="middle" fill="var(--fr-impassable-ink)" fontSize="16" fontFamily="var(--fr-font-sans)">Sample closure</text>
        <circle cx="622" cy="139" r="12" fill="var(--fr-impassable-ink)" stroke="var(--fr-canvas)" strokeWidth="2" />
        <path d="M616 139H628" stroke="var(--fr-canvas)" strokeWidth="2" />
      </svg>
      <figcaption><span>{city} / Route illustration</span><span>Example only. Live journeys use the planner below.</span></figcaption>
    </figure>
  );
}
