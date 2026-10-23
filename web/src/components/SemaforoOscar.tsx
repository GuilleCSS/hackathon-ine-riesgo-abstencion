import { useState } from "react";
import type { ExpressionSpecification, FilterSpecification } from "maplibre-gl";
import Ficha from "./Ficha";
import MapaSecciones, { ambito, type Propiedades } from "./MapaSecciones";
import { Kpi, Leyenda, Segmentado, SelectEntidad } from "./controles";
import { NIVELES, fmt, useApi, type Oscar } from "../lib/api";
import { nivelColor, token } from "../lib/tokens";

type Modo = "dif" | "oficial" | "oscar";
const MODOS: [Modo, string][] = [["dif", "Diferencias"], ["oficial", "Oficial"], ["oscar", "Oscar"]];
const COMPARACION: Record<string, [string, string]> = {
  coincide: ["dif-coincide", "Mismo nivel"],
  oscar_mas_alto: ["dif-alto", "Oscar más alto"],
  oscar_mas_bajo: ["dif-bajo", "Oscar más bajo"],
  solo_oscar: ["dif-solo", "Sólo en el de Oscar"],
};
const MOTIVOS: Record<string, string> = {
  comparable_high_ns: "NS > 10% en 2021 o 2024",
  sin_dato_comparable: "No está en 2021 y 2024 a la vez",
  insufficient_inputs: "Sin abstención calculable (100% NS)",
  valid_inputs_low_comparability: "Cambió de municipio o tipo",
};
const porNivel = (prop: string): ExpressionSpecification =>
  ["match", ["get", prop], "BAJO", token("riesgo-bajo"), "MEDIO", token("riesgo-medio"), "ALTO", token("riesgo-alto"), token("sin-estimacion")];

function capa(modo: Modo, edo: number | null) {
  const a = ambito(edo);
  if (modo === "oficial") return { filtro: ["all", ["==", ["get", "capa"], "semaforo"], ...a] as FilterSpecification, color: porNivel("nivel") };
  if (modo === "oscar") return { filtro: ["all", ["has", "nivel_oscar"], ...a] as FilterSpecification, color: porNivel("nivel_oscar") };
  return {
    filtro: ["all", ["has", "comp_oscar"], ...a] as FilterSpecification,
    color: ["match", ["get", "comp_oscar"], ...Object.entries(COMPARACION).flatMap(([k, [t]]) => [k, token(t)]),
      token("sin-estimacion")] as ExpressionSpecification,
  };
}

export default function SemaforoOscar() {
  const [edo, setEdo] = useState<number | null>(null);
  const [modo, setModo] = useState<Modo>("dif");
  const [seleccion, setSeleccion] = useState<string | null>(null);
  const { data, error } = useApi<Oscar>("/api/oscar", { edo });

  const tooltip = (p: Propiedades): [string, string][] => [
    ["Sección", p.clave],
    ["Oficial", p.nivel ? `${p.nivel} · ${fmt.pct(p.pred)}` : "fuera del universo"],
    ["Oscar", p.nivel_oscar ?? "fuera del universo"],
    ["Comparación", COMPARACION[p.comp_oscar]?.[1] ?? "—"],
  ];
  const leyenda: [string, string][] = modo === "dif"
    ? Object.values(COMPARACION).map(([t, e]) => [token(t), e])
    : NIVELES.map((n) => [nivelColor(n), n]);
  const k = data?.kpis;
  const matriz = (o: string, s: string) => data?.matriz.find((m) => m.oficial === o && m.oscar === s)?.secciones ?? 0;
  const u = data?.umbrales;

  return (
    <>
      <div className="app">
        <aside className="panel" aria-label="Filtros e indicadores">
          <section>
            <h2>Filtros</h2>
            <SelectEntidad valor={edo} onCambio={setEdo} />
            <Segmentado nombre="modo" etiqueta="Mostrar en el mapa" opciones={MODOS} valor={modo} onCambio={setModo} />
          </section>
          <section>
            <h2>Indicadores</h2>
            <div className="kpis" aria-live="polite">
              <Kpi etiqueta="Secciones en ambos" valor={k ? fmt.n(k.ambos) : "…"} />
              <Kpi etiqueta="Mismo nivel" valor={k ? fmt.share(k.mismo_nivel) : "…"} />
              <Kpi etiqueta="Oscar − oficial" valor={k ? fmt.pp(k.dif_media_pp) : "…"} />
              <Kpi etiqueta="Sólo en el de Oscar" valor={k ? fmt.n(k.solo_oscar) : "…"} />
            </div>
          </section>
          {data && (
            <div className="note">
              Nacional: si fueran independientes coincidirían {fmt.share(data.nacional.coincidencia_esperada_al_azar)};
              misma marca Top10 en {fmt.share(data.nacional.coincidencia_top10)}; correlación de Spearman entre
              estimaciones {data.nacional.spearman_estimaciones.toFixed(3)}.
            </div>
          )}
          {error && <div className="error" role="alert">No se pudo cargar la comparación: {error}</div>}
        </aside>
        <div className="map-wrap">
          <MapaSecciones datos={capa(modo, edo)} tooltip={tooltip} bbox={data?.bbox ?? null} seleccion={seleccion} onSelect={setSeleccion} />
          <Leyenda items={[...leyenda, ["var(--sin-estimacion)", "Fuera de ambos semáforos"]]} />
          {seleccion && <Ficha clave={seleccion} onClose={() => setSeleccion(null)} />}
        </div>
      </div>

      {data && u && (
        <div className="debajo">
          <section className="card">
            <h2>Qué diferencia a los dos semáforos</h2>
            <table className="tabla">
              <thead><tr><th /><th>Oficial</th><th>Oscar</th></tr></thead>
              <tbody>
                <tr><td>Estimación 2027</td><td>Regresión de dos historias (2021 y 2024)</td><td>Persistencia: abstención 2021</td></tr>
                <tr><td>Universo</td><td>NS ≤ 10%, sin cambios de municipio ni tipo</td><td>Todas las secciones con historia comparable</td></tr>
                <tr><td>BAJO hasta</td><td>{fmt.pct(u.oficial.q50)}</td><td>{fmt.pct(u.oscar.q50)}</td></tr>
                <tr><td>MEDIO hasta</td><td>{fmt.pct(u.oficial.q80)}</td><td>{fmt.pct(u.oscar.q80)}</td></tr>
                <tr><td>Top10 desde</td><td>{fmt.pct(u.oficial.q90)}</td><td>{fmt.pct(u.oscar.q90)}</td></tr>
              </tbody>
            </table>
            <p className="muted">
              Los dos usan la misma regla relativa (percentiles 50, 80 y 90 de su propio universo). Error medio en backtests,
              regresión vs. persistencia: 2021, 7.69 vs. 9.91 pp; 2024, 4.36 vs. 4.72 pp; 2018, 11.35 vs. 4.77 pp (ahí la
              regresión sólo pudo entrenarse con una intermedia). Detalle en <code>reports/semaforo_oscar/</code>.
            </p>
          </section>

          <div className="dos">
            <section className="card">
              <h2>Niveles: oficial (filas) vs. Oscar (columnas)</h2>
              <table className="tabla matriz">
                <thead><tr><th>Oficial</th>{NIVELES.map((n) => <th key={n} className="num">{n}</th>)}<th className="num">Mismo nivel</th></tr></thead>
                <tbody>
                  {NIVELES.map((o) => {
                    const total = NIVELES.reduce((a, s) => a + matriz(o, s), 0);
                    return (
                      <tr key={o}>
                        <td><span className="swatch" style={{ background: nivelColor(o) }} /> {o}</td>
                        {NIVELES.map((s) => <td key={s} className={o === s ? "num diag" : "num"}>{fmt.n(matriz(o, s))}</td>)}
                        <td className="num">{fmt.share(total ? matriz(o, o) / total : null)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </section>
            <section className="card">
              <h2>Por qué hay secciones sólo en el de Oscar</h2>
              <p className="muted">Son las que el filtro de calidad oficial excluye.</p>
              <table className="tabla">
                <thead><tr><th>Motivo</th><th className="num">Secciones</th></tr></thead>
                <tbody>
                  {data.motivos.map((m) => <tr key={m.motivo}><td>{MOTIVOS[m.motivo] ?? m.motivo}</td><td className="num">{fmt.n(m.secciones)}</td></tr>)}
                </tbody>
              </table>
            </section>
          </div>

          <section className="card">
            <h2>Coincidencia por {edo === null ? "entidad" : "municipio"}</h2>
            <p className="muted">De menor a mayor coincidencia.</p>
            <table className="tabla">
              <thead>
                <tr><th>{edo === null ? "Entidad" : "Municipio"}</th><th className="num">En ambos</th><th className="num">Mismo nivel</th>
                  <th className="num">Oscar − oficial</th><th className="num">ALTO oficial</th><th className="num">ALTO Oscar</th>
                  <th className="num">Sólo Oscar</th></tr>
              </thead>
              <tbody>
                {data.por_unidad.map((r) => (
                  <tr key={r.clave} onClick={() => edo === null && setEdo(r.clave)} title={edo === null ? "Ver en el mapa" : undefined}>
                    <td>{r.nombre}</td><td className="num">{fmt.n(r.ambos)}</td><td className="num">{fmt.share(r.mismo_nivel)}</td>
                    <td className="num">{fmt.pp(r.dif_media_pp)}</td><td className="num">{fmt.n(r.alto_oficial)}</td>
                    <td className="num">{fmt.n(r.alto_oscar)}</td><td className="num">{fmt.n(r.solo_oscar)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </div>
      )}
    </>
  );
}
