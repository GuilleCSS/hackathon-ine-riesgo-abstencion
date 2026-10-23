// Gráficas propias (SVG/HTML): sin dependencias y sin estilos en línea que bloquearía la CSP.
import { Fragment, useEffect, useRef, useState } from "react";
import { rem } from "../lib/tokens";

export interface Serie {
  nombre: string;
  color: string;
  punteada?: boolean;
  puntos: { x: number; y: number | null }[];
}

function useAncho() {
  const ref = useRef<HTMLDivElement>(null);
  const [ancho, setAncho] = useState(0);
  useEffect(() => {
    const ro = new ResizeObserver(([e]) => setAncho(e.contentRect.width));
    ro.observe(ref.current!);
    return () => ro.disconnect();
  }, []);
  return [ref, ancho] as const;
}

function pasoBonito(max: number, n = 4) {
  const crudo = max / n;
  const mag = 10 ** Math.floor(Math.log10(crudo));
  const f = crudo / mag;
  return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * mag;
}

/** Líneas por año con eje en cero, rejilla tenue y tooltip con todas las series del año bajo el cursor. */
export function Lineas({ series, formato, formatoValor = formato, titulo }: {
  series: Serie[];
  formato: (v: number) => string;
  /** Para el tooltip (más precisión que el eje). */
  formatoValor?: (v: number) => string;
  titulo: string;
}) {
  const [ref, ancho] = useAncho();
  const [hover, setHover] = useState<number | null>(null);
  const xs = [...new Set(series.flatMap((s) => s.puntos.map((p) => p.x)))].sort((a, b) => a - b);
  const max = Math.max(0, ...series.flatMap((s) => s.puntos.map((p) => p.y ?? 0)));
  const paso = pasoBonito(max || 1);
  const tope = Math.ceil(max / paso) * paso || paso;
  const ticks = Array.from({ length: Math.round(tope / paso) + 1 }, (_, i) => i * paso);
  const m = { top: rem(0.75), right: rem(1.25), bottom: rem(2), left: rem(3.75) };
  const alto = rem(17);
  const w = Math.max(ancho - m.left - m.right, 0);
  const h = alto - m.top - m.bottom;
  const tramos = Math.max(xs.length - 1, 1);
  const x = (v: number) => m.left + (xs.length < 2 ? w / 2 : (xs.indexOf(v) / tramos) * w);
  const y = (v: number) => m.top + h - (v / tope) * h;
  const enHover = hover === null ? [] : series
    .map((s) => ({ s, y: s.puntos.find((p) => p.x === hover)?.y ?? null }))
    .filter((d) => d.y !== null)
    .sort((a, b) => b.y! - a.y!);

  return (
    <div className="grafica" ref={ref}>
      {series.length > 1 && (
        <div className="leyenda">
          {series.map((s) => (
            <span key={s.nombre}>
              <span className={`trazo${s.punteada ? " punteada" : ""}`} style={s.punteada ? undefined : { background: s.color }} />
              {s.nombre}
            </span>
          ))}
        </div>
      )}
      <div className="lienzo">
      {ancho > 0 && (
        <svg width={ancho} height={alto} role="img" aria-label={titulo}>
          {ticks.map((t) => (
            <g key={t}>
              <line className="rejilla" x1={m.left} x2={m.left + w} y1={y(t)} y2={y(t)} />
              <text className="eje" x={m.left - rem(0.5)} y={y(t)} textAnchor="end" dominantBaseline="middle">{formato(t)}</text>
            </g>
          ))}
          {xs.map((v) => <text key={v} className="eje" x={x(v)} y={alto - rem(0.35)} textAnchor="middle">{v}</text>)}
          {hover !== null && <line className="guia" x1={x(hover)} x2={x(hover)} y1={m.top} y2={m.top + h} />}
          {series.map((s) => {
            const pts = s.puntos.filter((p) => p.y !== null);
            return (
              <g key={s.nombre}>
                <path className={`linea${s.punteada ? " punteada" : ""}`} stroke={s.punteada ? "var(--ink-2)" : s.color}
                  d={pts.map((p, i) => `${i ? "L" : "M"}${x(p.x)},${y(p.y!)}`).join("")} />
                {!s.punteada && pts.map((p) => <circle key={p.x} className="marca" cx={x(p.x)} cy={y(p.y!)} r={rem(0.3)} fill={s.color} />)}
              </g>
            );
          })}
          {xs.map((v) => (
            <rect key={v} x={x(v) - w / tramos / 2} y={m.top} width={w / tramos} height={h} fill="transparent"
              onMouseEnter={() => setHover(v)} onMouseLeave={() => setHover(null)} />
          ))}
        </svg>
      )}
      {hover !== null && enHover.length > 0 && (
        <div className="tip" style={x(hover) > ancho * 0.6
          ? { right: ancho - x(hover) + rem(0.75), top: m.top } : { left: x(hover) + rem(0.75), top: m.top }}>
          <b>{hover}</b>
          {enHover.map(({ s, y: v }) => (
            <div key={s.nombre}>
              <span className="swatch" style={{ background: s.punteada ? "var(--ink-2)" : s.color }} />
              {s.nombre}: <b className="num">{formatoValor(v!)}</b>
            </div>
          ))}
        </div>
      )}
      </div>
    </div>
  );
}

export interface Parte { clave: string; nombre: string; color: string }

/** Barras horizontales apiladas. Con escala = 1 son proporciones que suman 100%. */
export function Barras({ filas, partes, formato, escala }: {
  filas: { etiqueta: string; valores: Record<string, number> }[];
  partes: Parte[];
  formato: (v: number) => string;
  escala?: number;
}) {
  const tope = escala ?? Math.max(1e-9, ...filas.map((f) => partes.reduce((a, p) => a + (f.valores[p.clave] ?? 0), 0)));
  return (
    <>
      <div className="leyenda">
        {partes.map((p) => <span key={p.clave}><span className="swatch" style={{ background: p.color }} />{p.nombre}</span>)}
      </div>
      <div className="barras">
        {filas.map((f) => (
          <Fragment key={f.etiqueta}>
            <span>{f.etiqueta}</span>
            <div className="pista">
              {partes.map((p) => {
                const v = f.valores[p.clave] ?? 0;
                return v > 0 && (
                  <div key={p.clave} title={`${f.etiqueta} · ${p.nombre}: ${formato(v)}`}
                    style={{ width: `${(v / tope) * 100}%`, background: p.color }} />
                );
              })}
            </div>
          </Fragment>
        ))}
      </div>
    </>
  );
}
