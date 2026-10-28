import { useState } from "react";
import type { ExpressionSpecification, FilterSpecification } from "maplibre-gl";
import Ficha from "./Ficha";
import MapaSecciones, { ambito, type Propiedades } from "./MapaSecciones";
import { Lineas } from "./graficas";
import { Kpi, Leyenda, Segmentado, SelectEntidad } from "./controles";
import { fmt, useApi, type Brecha } from "../lib/api";
import { token } from "../lib/tokens";

type Par = "15_18" | "21_24";
const PARES: [Par, string][] = [["15_18", "2015 vs. 2018"], ["21_24", "2021 vs. 2024"]];
const ANIOS_PAR: Record<Par, [number, number]> = { "15_18": [2015, 2018], "21_24": [2021, 2024] };
const NOMBRE_PAR: Record<Par, string> = { "15_18": "2015–2018", "21_24": "2021–2024" };
const COLORES = ["brecha-neg", "brecha-1", "brecha-2", "brecha-3", "brecha-4"];
const ETIQUETAS = ["< 0 pp (más abstención en la presidencial)", "0–5 pp", "5–10 pp", "10–15 pp", "≥ 15 pp"];
const VARIABLES: Record<string, string> = {
  gob_intermedia: "Gubernatura el mismo día que la intermedia",
  gob_presidencial: "Gubernatura el mismo día que la presidencial",
  local_intermedia: "Elecciones locales el mismo día que la intermedia",
  local_presidencial: "Elecciones locales el mismo día que la presidencial",
};
const PARES_TABLA = ["2009–2012", "2015–2012", "2015–2018", "2021–2018", "2021–2024"];
const si = (v: number | boolean | undefined) => (v ? "sí" : "no");

export default function BrechaTipo() {
  const [edo, setEdo] = useState<number | null>(null);
  const [par, setPar] = useState<Par>("21_24");
  const [seleccion, setSeleccion] = useState<string | null>(null);
  const { data, error } = useApi<Brecha>("/api/brecha", { edo });

  const colores = COLORES.map(token);
  const prop = `brecha_${par}`;
  const [ai, ap] = ANIOS_PAR[par];
  const datos = {
    filtro: ["all", ...ambito(edo), ["has", prop]] as FilterSpecification,
    color: ["step", ["get", prop], colores[0], 0, colores[1], 5, colores[2], 10, colores[3], 15, colores[4]] as ExpressionSpecification,
  };
  const tooltip = (p: Propiedades): [string, string][] => p[prop] === undefined
    ? [["Sección", p.clave], ["Sin brecha", "no existe en ambas elecciones o NS > 10%"]]
    : [["Sección", p.clave], [`Abstención ${ai} (intermedia)`, fmt.pct(p[`abst_${ai}`])],
       [`Abstención ${ap} (presidencial)`, fmt.pct(p[`abst_${ap}`])], ["Brecha", fmt.pp(p[prop])]];

  const r = data?.resumen;
  const est = data?.entidad?.find((e) => e.par === NOMBRE_PAR[par]);
  const gob = edo === null ? undefined : data?.gubernaturas.find((g) => g.EDOCVE === edo);
  const total = data?.nacional.filter((n) => n.variable === "Total") ?? [];
  const efecto = (v: string) => data?.efecto.find((e) => e.variable === v);

  return (
    <>
      <div className="app">
        <aside className="panel" aria-label="Filtros e indicadores">
          <section>
            <h2>Filtros</h2>
            <SelectEntidad valor={edo} onCambio={setEdo} />
            <Segmentado nombre="par" etiqueta="Elecciones que se comparan" opciones={PARES} valor={par} onCambio={setPar} />
          </section>
          <section>
            <h2>{est ? `${est.entidad} · ${NOMBRE_PAR[par]}` : `Nacional · ${NOMBRE_PAR[par]}`}</h2>
            <div className="kpis" aria-live="polite">
              {est ? (
                <>
                  <Kpi etiqueta="Brecha de la entidad" valor={fmt.pp(est.brecha_pp)} />
                  <Kpi etiqueta="Nacional" valor={r ? fmt.pp(r.brecha_nacional_pp[NOMBRE_PAR[par]]) : "…"} />
                  <Kpi etiqueta={`Gubernatura ${ai} / ${ap}`} valor={`${si(est.gob_intermedia)} / ${si(est.gob_presidencial)}`} />
                  <Kpi etiqueta="Gubernatura en 2027" valor={si(gob?.gob_2027)} nota={gob?.cambia_vs_2021 ? "Cambia frente a 2021" : undefined} />
                </>
              ) : (
                <>
                  <Kpi etiqueta="Brecha nacional" valor={r ? fmt.pp(r.brecha_nacional_pp[NOMBRE_PAR[par]]) : "…"} />
                  <Kpi etiqueta="Mediana por sección" valor={r ? fmt.pp(r.mediana_secciones_pp[NOMBRE_PAR[par]]) : "…"} />
                  <Kpi etiqueta="Secciones con brecha negativa" ancho valor={r ? fmt.share(r.pct_negativa[NOMBRE_PAR[par]]) : "…"}
                    nota="Se abstienen más en la presidencial que en la intermedia." />
                </>
              )}
            </div>
          </section>
          <div className="note">
            Brecha = abstención en la intermedia − en la presidencial. Rojo: la sección vota sobre todo cuando hay elección
            presidencial; 2027 es intermedia.
          </div>
          {error && <div className="error" role="alert">No se pudo cargar la brecha: {error}</div>}
        </aside>
        <div className="map-wrap">
          <MapaSecciones datos={datos} tooltip={tooltip} bbox={data?.bbox ?? null} seleccion={seleccion} onSelect={setSeleccion} />
          <Leyenda items={[...ETIQUETAS.map((e, i) => [colores[i], e] as [string, string]),
            ["var(--sin-estimacion)", "Sin brecha (no está en ambas o NS > 10%)"]]} />
          {seleccion && <Ficha clave={seleccion} onClose={() => setSeleccion(null)} />}
        </div>
      </div>

      {data && r && (
        <div className="debajo">
          <section className="card prose">
            <h2>Conclusiones</h2>
            <ol>
              <li><strong>La brecha se cerró a menos de la mitad:</strong> de {fmt.pp(r.brecha_nacional_pp["2009–2012"])} (2009–2012)
                a {fmt.pp(r.brecha_nacional_pp["2021–2024"])} (2021–2024).</li>
              <li><strong>Ya no es universal:</strong> {fmt.share(r.pct_negativa["2021–2024"])} de las secciones se abstuvieron más en la
                presidencial de 2024 que en la intermedia de 2021. Es grande en secciones urbanas y casi nula en las rurales.</li>
              <li><strong>Es poco persistente</strong> (Spearman {r.persistencia_15_18_vs_21_24.toFixed(2)}): depende más del contexto de
                cada elección que de la sección.</li>
              <li><strong>El calendario local está asociado con una brecha menor:</strong> en el modelo descriptivo, la concurrencia
                con elecciones locales se asocia con {fmt.pp(r.efecto_local_intermedia_pp)} y la concurrencia con gubernatura con
                {fmt.pp(r.efecto_gob_intermedia_pp)} adicionales. Es una asociación observacional, no un efecto causal.</li>
              <li><strong>Para 2027:</strong> las secciones ALTO del semáforo son las de mayor brecha, lo que refuerza su riesgo en una
                intermedia. Aguascalientes y Quintana Roo tendrán gubernatura el mismo día y en 2021 no; el modelo no usa concurrencia.</li>
            </ol>
            <p className="muted">El resumen 2027 se contrasta con la información oficial del INE; las asociaciones históricas no se interpretan como causalidad.</p>
          </section>

          <section className="card">
            <h2>Evolución</h2>
            <div className="dos">
              <Lineas titulo="Abstención nacional por tipo de elección" formato={(x) => `${(x * 100).toFixed(0)}%`} formatoValor={fmt.share}
                series={[
                  { nombre: "Intermedias", color: token("grupo-1"), puntos: [2009, 2015, 2021].map((y) => ({ x: y, y: total.find((t) => t.par.startsWith(String(y)))?.abst_intermedia ?? null })) },
                  { nombre: "Presidenciales", color: token("grupo-2"), puntos: [2012, 2018, 2024].map((y) => ({ x: y, y: total.find((t) => t.par.endsWith(String(y)))?.abst_presidencial ?? null })) },
                ]} />
              <table className="tabla">
                <thead><tr><th>Brecha (pp)</th>{PARES_TABLA.map((p) => <th key={p} className="num">{p}</th>)}</tr></thead>
                <tbody>
                  {[...new Set(data.nacional.map((n) => n.categoria))].map((c) => (
                    <tr key={c}><td>{c}</td>
                      {PARES_TABLA.map((p) => {
                        const n = data.nacional.find((x) => x.par === p && x.categoria === c);
                        return <td key={p} className="num">{n ? fmt.pp(n.brecha_pp) : "—"}</td>;
                      })}</tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <div className="dos">
            <section className="card">
              <h2>Entre secciones</h2>
              <table className="tabla">
                <thead><tr><th>Par</th><th className="num">Secciones</th><th className="num">Mediana</th><th className="num">P10</th>
                  <th className="num">P90</th><th className="num">Negativa</th></tr></thead>
                <tbody>
                  {data.distribucion.map((d) => (
                    <tr key={d.par}><td>{d.par}</td><td className="num">{fmt.n(d.secciones)}</td><td className="num">{fmt.pp(d.mediana)}</td>
                      <td className="num">{fmt.pp(d.p10)}</td><td className="num">{fmt.pp(d.p90)}</td><td className="num">{fmt.share(d.pct_negativa)}</td></tr>
                  ))}
                </tbody>
              </table>
              <h3>¿Dónde es mayor? (2021–2024, mediana)</h3>
              <table className="tabla">
                <tbody>
                  {data.por_grupo.filter((g) => g.variable !== "Entidad").map((g) => (
                    <tr key={g.variable + g.categoria}><td className="muted">{g.variable}</td><td>{g.categoria}</td>
                      <td className="num">{fmt.pp(g.mediana_pp)}</td></tr>
                  ))}
                </tbody>
              </table>
            </section>
            <section className="card">
              <h2>¿Cómo se asocia con la concurrencia local?</h2>
              <p className="muted">
                MCO de la brecha por entidad y par (32 × 5) con efectos fijos de par; intervalo al 90% por bootstrap de entidades.
              </p>
              <table className="tabla">
                <thead><tr><th>Variable</th><th className="num">Coef. asociado</th><th className="num">IC 90%</th></tr></thead>
                <tbody>
                  {Object.entries(VARIABLES).map(([k, texto]) => {
                    const e = efecto(k);
                    return e && (
                      <tr key={k}><td>{texto}</td><td className="num">{fmt.pp(e.coef_pp)}</td>
                        <td className="num">[{e.ic90_bajo.toFixed(1)}, {e.ic90_alto.toFixed(1)}]</td></tr>
                    );
                  })}
                </tbody>
              </table>
              <h3>Entidades con elecciones el mismo día que la federal</h3>
              <table className="tabla">
                <thead><tr><th>Año</th>{data.calendario.map((c) => <th key={c.ANIO} className="num">{c.ANIO}</th>)}</tr></thead>
                <tbody>
                  <tr><td>Locales</td>{data.calendario.map((c) => <td key={c.ANIO} className="num">{c.locales}</td>)}</tr>
                  <tr><td>Gubernaturas</td>{data.calendario.map((c) => <td key={c.ANIO} className="num">{c.gubernaturas}</td>)}</tr>
                </tbody>
              </table>
              <p className="muted">
                Entre 2009–2012 y 2021–2024 la brecha promedio de las entidades cambió {fmt.pp(r.cierre_por_calendario.cambio_observado_pp)};
                bajo este modelo descriptivo, el cambio asociado al calendario equivale a {fmt.pp(r.cierre_por_calendario.cambio_por_calendario_pp)}.
              </p>
            </section>
          </div>

          <div className="dos">
            <section className="card">
              <h2>Implicaciones para 2027</h2>
              <table className="tabla">
                <thead><tr><th>Nivel 2027</th><th className="num">Secciones</th><th className="num">Brecha mediana 2021–2024</th></tr></thead>
                <tbody>
                  {data.niveles.map((n) => (
                    <tr key={n.nivel}><td>{n.nivel}</td><td className="num">{fmt.n(n.secciones)}</td><td className="num">{fmt.pp(n.mediana_pp)}</td></tr>
                  ))}
                </tbody>
              </table>
              <h3>Gubernaturas concurrentes que cambian en 2027</h3>
              <table className="tabla">
                <thead><tr><th>Entidad</th><th>2021</th><th>2024</th><th>2027</th></tr></thead>
                <tbody>
                  {data.gubernaturas.filter((g) => g.cambia_vs_2021).map((g) => (
                    <tr key={g.EDOCVE}><td>{g.entidad}</td><td>{si(g.gob_2021)}</td><td>{si(g.gob_2024)}</td><td>{si(g.gob_2027)}</td></tr>
                  ))}
                </tbody>
              </table>
            </section>
            <section className="card">
              <h2>Entidades (2021–2024)</h2>
              <table className="tabla">
                <thead><tr><th>Entidad</th><th className="num">Brecha</th><th>Gob. 2021</th><th>Gob. 2024</th></tr></thead>
                <tbody>
                  {data.entidades.map((e) => (
                    <tr key={e.EDOCVE} onClick={() => setEdo(e.EDOCVE)} title="Ver en el mapa">
                      <td>{e.entidad}</td><td className="num">{fmt.pp(e.brecha_pp)}</td><td>{si(e.gob_intermedia)}</td><td>{si(e.gob_presidencial)}</td></tr>
                  ))}
                </tbody>
              </table>
            </section>
          </div>
        </div>
      )}
    </>
  );
}
