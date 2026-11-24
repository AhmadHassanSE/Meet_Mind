import React, { createContext, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';

/** Whether model scores, pipeline names and diagnostics are shown. Off by default so the everyday
 *  view stays plain; evaluators switch it on from the top bar. */
export const DetailsContext = createContext(false);
export const useDetails = () => useContext(DetailsContext);
export function useDetailsSetting(): [boolean, () => void] {
  const [on, setOn] = useState(() => { try { return localStorage.getItem('meetmind-details') === 'on'; } catch { return false; } });
  useEffect(() => { try { localStorage.setItem('meetmind-details', on ? 'on' : 'off'); } catch { /* storage unavailable */ } }, [on]);
  return [on, () => setOn(v => !v)];
}

/** Only renders its children when technical details are switched on. */
export function TechOnly({ children }: { children: React.ReactNode }) {
  return useDetails() ? <>{children}</> : null;
}

/** MeetMind mark from the project poster: a speech bubble holding an "M" drawn as a connected
 *  graph, whose last stroke ends in the gold "execution" node. */
export function Logo({ size = 32 }: { size?: number }) {
  return <svg className="logo" width={size} height={size} viewBox="0 0 48 48" aria-hidden="true" focusable="false">
    <rect width="48" height="48" rx="12" className="logo-tile"/>
    <path className="logo-line" fill="none" strokeWidth="3" strokeLinejoin="round"
      d="M15 10.5h18a6.5 6.5 0 0 1 6.5 6.5v11a6.5 6.5 0 0 1-6.5 6.5H21l-7 5.5v-5.6A6.5 6.5 0 0 1 8.5 28V17a6.5 6.5 0 0 1 6.5-6.5z"/>
    <path className="logo-line" fill="none" strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round" d="M16.5 27.5V17.5l7.5 7 7.5-7v9"/>
    <circle className="logo-node" cx="16.5" cy="27.5" r="2.3"/>
    <circle className="logo-node" cx="16.5" cy="17.5" r="2.3"/>
    <circle className="logo-node" cx="24" cy="24.5" r="2.3"/>
    <circle className="logo-node" cx="31.5" cy="17.5" r="2.3"/>
    <circle className="logo-dot" cx="32" cy="28.5" r="3.9"/>
  </svg>;
}

export function prefersReducedMotion() {
  return typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
}

/** Counts from the previous value to the new one; jumps straight there with reduced motion. */
export function useCountUp(target: number, duration = 800) {
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

/** A figure that counts up when its data arrives. */
export function Ticker({ value, ready = true }: { value: number; ready?: boolean }) {
  return <>{useCountUp(ready ? value : 0)}</>;
}

/** Topographic contour lines, the texture of the poster. Drawn in on mount, then drifts slowly. */
export function Contours({ className = '', rings = 10, seed = 1 }: { className?: string; rings?: number; seed?: number }) {
  const paths = useMemo(() => {
    const out: string[] = [];
    for (let k = 0; k < rings; k++) {
      const r = 46 + k * 36;
      let d = '';
      for (let i = 0; i <= 120; i++) {
        const t = (i / 120) * Math.PI * 2;
        const wobble = 1 + 0.1 * Math.sin(3 * t + k * 0.55 + seed) + 0.05 * Math.sin(5 * t - k * 0.35 + seed * 2) + 0.025 * Math.sin(9 * t + k);
        d += `${i ? 'L' : 'M'}${(400 + Math.cos(t) * r * wobble * 1.3).toFixed(1)} ${(300 + Math.sin(t) * r * wobble * 0.82).toFixed(1)}`;
      }
      out.push(d + 'Z');
    }
    return out;
  }, [rings, seed]);
  return <svg className={`contours ${className}`} viewBox="0 0 800 600" preserveAspectRatio="xMidYMid slice" aria-hidden="true" focusable="false">
    <g>{paths.map((d, i) => <path key={i} d={d} pathLength={1} style={{ '--k': i } as React.CSSProperties}/>)}</g>
  </svg>;
}

export type BridgeStage = { label: string; detail: string; value?: number | null; caption?: string; onSelect?: () => void; gold?: boolean };

/** The five-stage bridge from the poster. A light travels along the track; each figure counts up. */
export function Bridge({ stages, ready = true, vertical = false, label }: { stages: BridgeStage[]; ready?: boolean; vertical?: boolean; label: string }) {
  return <div className={`bridge${vertical ? ' vertical' : ''}`}>
    <span className="bridge-beam" aria-hidden="true"><span/></span>
    <ol aria-label={label}>{stages.map((stage, index) => <BridgeItem key={stage.label} stage={stage} index={index} ready={ready}/>)}</ol>
  </div>;
}

function BridgeItem({ stage, index, ready }: { stage: BridgeStage; index: number; ready: boolean }) {
  const value = useCountUp(ready && typeof stage.value === 'number' ? stage.value : 0);
  const body = <>
    <span className="bridge-disc" aria-hidden="true">{index + 1}</span>
    <span className="bridge-text">
      <strong className="bridge-label">{stage.label}</strong>
      {stage.value !== undefined && <span className="bridge-value">{stage.value === null ? 'none yet' : value}</span>}
      {stage.caption && <span className="bridge-caption">{stage.caption}</span>}
      <span className="bridge-detail">{stage.detail}</span>
    </span></>;
  return <li className={stage.gold ? 'gold' : undefined} style={{ '--i': index } as React.CSSProperties}>
    {stage.onSelect ? <button type="button" className="bridge-node" onClick={stage.onSelect}>{body}</button> : <div className="bridge-node">{body}</div>}
  </li>;
}

/** Approved-of-total as a ring. */
export function Ring({ value, total, size = 40 }: { value: number; total: number; size?: number }) {
  const share = total ? value / total : 0;
  const c = 2 * Math.PI * 16;
  return <svg className="ring" width={size} height={size} viewBox="0 0 40 40" aria-hidden="true" focusable="false">
    <circle cx="20" cy="20" r="16" className="ring-track"/>
    <circle cx="20" cy="20" r="16" className="ring-fill" strokeDasharray={c} style={{ strokeDashoffset: c * (1 - share) }}/>
  </svg>;
}

/** Fades sections in as they enter the viewport (once). Content stays visible without the observer. */
export function useReveal(root: React.RefObject<HTMLElement>) {
  useEffect(() => {
    const host = root.current;
    if (!host || typeof IntersectionObserver === 'undefined' || prefersReducedMotion()) return;
    document.documentElement.classList.add('motion');
    const io = new IntersectionObserver(entries => entries.forEach(entry => {
      if (entry.isIntersecting) { entry.target.classList.add('in'); io.unobserve(entry.target); }
    }), { rootMargin: '0px 0px -6% 0px', threshold: 0.04 });
    const scan = () => host.querySelectorAll('.reveal:not(.in)').forEach(el => io.observe(el));
    scan();
    const watch = new MutationObserver(scan);
    watch.observe(host, { childList: true, subtree: true });
    return () => { io.disconnect(); watch.disconnect(); };
  }, [root]);
}

/** Cursor-following highlight on any `.spot` surface. */
export function useSpotlight() {
  useEffect(() => {
    const move = (e: PointerEvent) => {
      const el = (e.target as Element | null)?.closest?.('.spot') as HTMLElement | null;
      if (!el) return;
      const box = el.getBoundingClientRect();
      el.style.setProperty('--mx', `${e.clientX - box.left}px`);
      el.style.setProperty('--my', `${e.clientY - box.top}px`);
    };
    document.addEventListener('pointermove', move, { passive: true });
    return () => document.removeEventListener('pointermove', move);
  }, []);
}

/** Position of the active item inside a container, for an indicator that slides between items. */
export function useIndicator<T extends HTMLElement>(selector: string, deps: unknown[]) {
  const ref = useRef<T>(null);
  const [style, setStyle] = useState<React.CSSProperties>({ opacity: 0 });
  useLayoutEffect(() => {
    const measure = () => {
      const el = ref.current?.querySelector<HTMLElement>(selector);
      setStyle(el ? { opacity: 1, '--x': `${el.offsetLeft}px`, '--y': `${el.offsetTop}px`, '--w': String(el.offsetWidth), '--h': `${el.offsetHeight}px` } as React.CSSProperties : { opacity: 0 });
    };
    measure();
    void document.fonts?.ready.then(measure);
    window.addEventListener('resize', measure);
    return () => window.removeEventListener('resize', measure);
  }, deps);
  return [ref, style] as const;
}

const speakerTones = 5;
/** A stable colour slot per speaker name. */
export function speakerTone(name: string | null | undefined) {
  if (!name) return 0;
  let hash = 0;
  for (const char of name) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return 1 + (hash % speakerTones);
}
