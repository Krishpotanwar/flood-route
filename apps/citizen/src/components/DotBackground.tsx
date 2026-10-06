import { useEffect, useRef } from "react";
import type { Theme } from "../types";
import { advanceDot, type Dot } from "../utils/dots";

export function DotBackground({ theme = "light" }: { theme?: Theme }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context) return;
    const staticMotion = window.matchMedia("(prefers-reduced-motion: reduce), (pointer: coarse)");
    const dark = theme === "dark" || theme === "hc-dark";
    let dots: Dot[] = [];
    let pointer: { x: number; y: number } | null = null;
    let frame = 0;
    let previousTime = 0;
    let width = 0;
    let height = 0;

    const draw = () => {
      context.clearRect(0, 0, width, height);
      context.fillStyle = dark ? "rgba(255,255,255,0.14)" : "rgba(0,0,0,0.18)";
      context.beginPath();
      for (const dot of dots) {
        const x = dot.x + dot.offsetX;
        const y = dot.y + dot.offsetY;
        context.moveTo(x + 1, y);
        context.arc(x, y, 1, 0, Math.PI * 2);
      }
      context.fill();
    };
    const stop = () => {
      cancelAnimationFrame(frame);
      frame = 0;
      previousTime = 0;
    };
    const animate = (time: number) => {
      frame = 0;
      const elapsed = previousTime ? Math.min(time - previousTime, 48) : 16.67;
      previousTime = time;
      const blend = 1 - Math.exp(-elapsed / 96);
      let moving = false;
      for (const dot of dots) moving = advanceDot(dot, pointer, blend) || moving;
      draw();
      if (moving) frame = requestAnimationFrame(animate);
      else previousTime = 0;
    };
    const wake = () => {
      if (!frame && !document.hidden && !staticMotion.matches) frame = requestAnimationFrame(animate);
    };
    const reset = () => {
      stop();
      pointer = null;
      for (const dot of dots) { dot.offsetX = 0; dot.offsetY = 0; }
      if (!document.hidden) draw();
    };
    const resize = () => {
      stop();
      width = window.innerWidth;
      height = window.innerHeight;
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
      dots = [];
      // ponytail: viewport grid; switch to tiled rendering if wall-size displays need it.
      for (let y = 15; y < height; y += 30) {
        for (let x = 15; x < width; x += 30) dots.push({ x, y, offsetX: 0, offsetY: 0 });
      }
      if (!document.hidden) draw();
      if (pointer) wake();
    };
    const onPointerMove = (event: PointerEvent) => {
      if (staticMotion.matches || document.hidden || event.pointerType === "touch") return;
      pointer = { x: event.clientX, y: event.clientY };
      wake();
    };
    const clearPointer = () => { pointer = null; wake(); };

    resize();
    window.addEventListener("pointermove", onPointerMove, { passive: true });
    window.addEventListener("resize", resize, { passive: true });
    window.addEventListener("blur", clearPointer);
    document.addEventListener("mouseleave", clearPointer);
    document.addEventListener("visibilitychange", reset);
    staticMotion.addEventListener("change", reset);
    return () => {
      stop();
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("resize", resize);
      window.removeEventListener("blur", clearPointer);
      document.removeEventListener("mouseleave", clearPointer);
      document.removeEventListener("visibilitychange", reset);
      staticMotion.removeEventListener("change", reset);
    };
  }, [theme]);

  return <canvas ref={canvasRef} className="dot-background" aria-hidden="true" />;
}
