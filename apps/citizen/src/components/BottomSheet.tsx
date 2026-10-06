import React, { useCallback, useRef, useState } from "react";

export type SnapPoint = "collapsed" | "half" | "expanded";

export interface BottomSheetProps {
  initialSnap?: SnapPoint;
  snap?: SnapPoint;
  onSnapChange?: (snap: SnapPoint) => void;
  children: React.ReactNode;
  title?: React.ReactNode;
  headerExtra?: React.ReactNode;
  role?: "dialog" | "region";
  ariaLabel?: string;
  className?: string;
  style?: React.CSSProperties;
}

export const SNAP_HEIGHT_CSS: Record<SnapPoint, string> = {
  collapsed: "6rem",
  half: "50dvh",
  expanded: "90dvh",
};

const getViewportHeight = (): number => {
  if (typeof window !== "undefined" && window.innerHeight) {
    return window.innerHeight;
  }
  return 800;
};

const getSnapHeightsPx = (vh: number): Record<SnapPoint, number> => {
  return {
    collapsed: 96,
    half: Math.round(vh * 0.5),
    expanded: Math.round(vh * 0.9),
  };
};

export function calculateTargetSnap(
  fromSnap: SnapPoint,
  currentHeight: number,
  totalDeltaY: number,
  velocity: number,
  snaps: Record<SnapPoint, number>
): SnapPoint {
  const VELOCITY_THRESHOLD = 0.3;

  if (velocity <= -VELOCITY_THRESHOLD) {
    if (fromSnap === "collapsed") {
      return velocity <= -0.8 || currentHeight > snaps.half ? "expanded" : "half";
    }
    return "expanded";
  }

  if (velocity >= VELOCITY_THRESHOLD) {
    if (fromSnap === "expanded") {
      return velocity >= 0.8 || currentHeight < snaps.half ? "collapsed" : "half";
    }
    return "collapsed";
  }

  const DISTANCE_THRESHOLD = 50;
  if (totalDeltaY >= DISTANCE_THRESHOLD) {
    if (fromSnap === "collapsed") {
      const midpointHalfExpanded = (snaps.half + snaps.expanded) / 2;
      return currentHeight > midpointHalfExpanded ? "expanded" : "half";
    }
    return "expanded";
  }

  if (totalDeltaY <= -DISTANCE_THRESHOLD) {
    if (fromSnap === "expanded") {
      const midpointCollapsedHalf = (snaps.collapsed + snaps.half) / 2;
      return currentHeight < midpointCollapsedHalf ? "collapsed" : "half";
    }
    return "collapsed";
  }

  const distCollapsed = Math.abs(currentHeight - snaps.collapsed);
  const distHalf = Math.abs(currentHeight - snaps.half);
  const distExpanded = Math.abs(currentHeight - snaps.expanded);

  if (distCollapsed <= distHalf && distCollapsed <= distExpanded) {
    return "collapsed";
  }
  if (distHalf <= distCollapsed && distHalf <= distExpanded) {
    return "half";
  }
  return "expanded";
}

export const BottomSheet: React.FC<BottomSheetProps> = ({
  initialSnap = "half",
  snap: controlledSnap,
  onSnapChange,
  children,
  title,
  headerExtra,
  role = "dialog",
  ariaLabel = "Route details and actions",
  className = "",
  style,
}) => {
  const [uncontrolledSnap, setUncontrolledSnap] = useState<SnapPoint>(initialSnap);
  const currentSnap = controlledSnap !== undefined ? controlledSnap : uncontrolledSnap;

  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [dragHeight, setDragHeight] = useState<number | null>(null);

  const sheetRef = useRef<HTMLElement | null>(null);
  const pointerIdRef = useRef<number | null>(null);
  const startYRef = useRef<number>(0);
  const startHeightRef = useRef<number>(0);
  const lastYRef = useRef<number>(0);
  const lastTimeRef = useRef<number>(0);
  const velocityRef = useRef<number>(0);
  const rafIdRef = useRef<number | null>(null);
  const pendingHeightRef = useRef<number | null>(null);

  const setTargetSnap = useCallback(
    (nextSnap: SnapPoint) => {
      if (controlledSnap === undefined) {
        setUncontrolledSnap(nextSnap);
      }
      onSnapChange?.(nextSnap);
    },
    [controlledSnap, onSnapChange]
  );

  const handlePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0 && e.pointerType === "mouse") {
      return;
    }

    const target = e.target as HTMLElement;
    if (target.closest("button, a, input, select, textarea")) {
      return;
    }

    const vh = getViewportHeight();
    const snaps = getSnapHeightsPx(vh);
    const rect = sheetRef.current?.getBoundingClientRect();
    const initialHeight = rect && rect.height > 0 ? rect.height : snaps[currentSnap];

    pointerIdRef.current = e.pointerId;
    startYRef.current = e.clientY;
    startHeightRef.current = initialHeight;
    lastYRef.current = e.clientY;
    lastTimeRef.current = performance.now();
    velocityRef.current = 0;

    try {
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch {
      // In testing environments pointer capture may be unavailable
    }

    setIsDragging(true);
    setDragHeight(initialHeight);
  };

  const handlePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!isDragging || e.pointerId !== pointerIdRef.current) {
      return;
    }

    const now = performance.now();
    const dt = now - lastTimeRef.current;
    const dy = e.clientY - lastYRef.current;

    if (dt > 8) {
      velocityRef.current = dy / dt;
      lastYRef.current = e.clientY;
      lastTimeRef.current = now;
    }

    const deltaY = startYRef.current - e.clientY;
    const rawHeight = startHeightRef.current + deltaY;

    const vh = getViewportHeight();
    const minHeight = 64;
    const maxHeight = Math.round(vh * 0.95);
    const clampedHeight = Math.min(Math.max(rawHeight, minHeight), maxHeight);

    pendingHeightRef.current = clampedHeight;
    if (rafIdRef.current === null) {
      rafIdRef.current = requestAnimationFrame(() => {
        rafIdRef.current = null;
        if (pendingHeightRef.current !== null) {
          setDragHeight(pendingHeightRef.current);
        }
      });
    }
  };

  const handlePointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!isDragging || e.pointerId !== pointerIdRef.current) {
      return;
    }

    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch {
      // Non-fatal if unsupported
    }

    if (rafIdRef.current !== null) {
      cancelAnimationFrame(rafIdRef.current);
      rafIdRef.current = null;
    }

    const vh = getViewportHeight();
    const snaps = getSnapHeightsPx(vh);
    const resolvedHeight = pendingHeightRef.current ?? (dragHeight ?? startHeightRef.current);
    const totalDeltaY = startYRef.current - e.clientY;
    const velocity = velocityRef.current;

    const nextSnap = calculateTargetSnap(
      currentSnap,
      resolvedHeight,
      totalDeltaY,
      velocity,
      snaps
    );

    setIsDragging(false);
    setDragHeight(null);
    pendingHeightRef.current = null;
    pointerIdRef.current = null;

    setTargetSnap(nextSnap);
  };

  const handlePointerCancel = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!isDragging || e.pointerId !== pointerIdRef.current) {
      return;
    }

    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch {
      // Non-fatal if unsupported
    }

    if (rafIdRef.current !== null) {
      cancelAnimationFrame(rafIdRef.current);
      rafIdRef.current = null;
    }

    setIsDragging(false);
    setDragHeight(null);
    pendingHeightRef.current = null;
    pointerIdRef.current = null;
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "ArrowUp") {
      e.preventDefault();
      if (currentSnap === "collapsed") setTargetSnap("half");
      else if (currentSnap === "half") setTargetSnap("expanded");
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      if (currentSnap === "expanded") setTargetSnap("half");
      else if (currentSnap === "half") setTargetSnap("collapsed");
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      if (currentSnap === "collapsed") setTargetSnap("half");
      else if (currentSnap === "half") setTargetSnap("expanded");
      else setTargetSnap("collapsed");
    }
  };

  const currentHeightStyle =
    isDragging && dragHeight !== null
      ? `${dragHeight}px`
      : SNAP_HEIGHT_CSS[currentSnap];

  const transitionStyle = isDragging
    ? "none"
    : "height 0.35s cubic-bezier(0.16, 1, 0.3, 1)";

  return (
    <section
      ref={sheetRef}
      className={`bottom-sheet ${className}`.trim()}
      role={role}
      aria-label={ariaLabel}
      aria-modal={role === "dialog" ? false : undefined}
      data-snap={currentSnap}
      data-dragging={isDragging ? "true" : "false"}
      style={{
        height: currentHeightStyle,
        transition: transitionStyle,
        willChange: isDragging ? "height" : "auto",
        ...style,
      }}
    >
      <div
        className="sheet-drag-zone"
        role="button"
        tabIndex={0}
        aria-label="Drag or toggle sheet height"
        aria-expanded={currentSnap !== "collapsed"}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerCancel}
        onKeyDown={handleKeyDown}
        style={{
          touchAction: "none",
          cursor: isDragging ? "grabbing" : "grab",
          userSelect: "none",
          minHeight: "2.5rem",
        }}
      >
        <div className="sheet-handle" aria-hidden="true" />
        {(title !== undefined || headerExtra !== undefined) && (
          <div className="sheet-header">
            {typeof title === "string" ? (
              <h2 style={{ margin: 0, fontSize: "var(--fr-text-lg)", fontWeight: 700 }}>
                {title}
              </h2>
            ) : (
              title
            )}
            {headerExtra && <div className="sheet-header-extra">{headerExtra}</div>}
          </div>
        )}
      </div>

      <div className="sheet-content">{children}</div>
    </section>
  );
};

export default BottomSheet;
