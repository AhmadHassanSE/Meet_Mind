import { useEffect, useRef, useState } from 'react';

/** MeetMind mark: speech waveform bars resolving into a check ("voice to done"). */
export function Logo({ size = 28 }: { size?: number }) {
  return <svg className="logo" width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" focusable="false">
    <rect width="32" height="32" rx="9" className="logo-tile"/>
    <g strokeLinecap="round" strokeWidth="2.6" className="logo-bars">
      <path d="M7 15v2"/><path d="M10.5 12.5v7"/><path d="M14 14v4"/>
    </g>
    <path d="M17 16.5l3.2 3.5L26 11" fill="none" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" className="logo-check"/>
  </svg>;
}

export function prefersReducedMotion() {
  return typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
}

/** Counts from the previous value to the new one; jumps straight there with reduced motion. */
export function useCountUp(target: number, duration = 700) {
  const [value, setValue] = useState(target);
  const from = useRef(0);
  useEffect(() => {
    if (prefersReducedMotion() || target === from.current) { setValue(target); from.current = target; return; }
    const start = performance.now(), origin = from.current;
    let frame = 0;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      setValue(Math.round(origin + (target - origin) * eased));
      if (t < 1) frame = requestAnimationFrame(tick);
      else from.current = target;
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [target, duration]);
  return value;
}
