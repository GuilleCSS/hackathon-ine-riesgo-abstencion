import { useState } from "react";
import type { ExpressionSpecification, FilterSpecification } from "maplibre-gl";
import Ficha from "./Ficha";
import MapaSecciones, { ambito, type Propiedades } from "./MapaSecciones";
import { Barras, Lineas } from "./graficas";
import { Kpi, Leyenda, Segmentado, SelectEntidad } from "./controles";
import { ANIOS, TIPO_ANIO, fmt, useApi, type Historico as Datos } from "../lib/api";
import { token } from "../lib/tokens";

type Tipo = "" | "intermedia" | "presidencial";
type Variable = "abst" | "ns" | "cambio";
const TIPOS: [Tipo, string][] = [["", "Todas"], ["intermedia", "Intermedias"], ["presidencial", "Presidenciales"]];
const RAMPA = ["rampa-1", "rampa-2", "rampa-3", "rampa-4", "rampa-5"];
// Rangos fijos para comparar entre años (los mismos de dashboard/datos_anuales.py).
const VARIABLES: Record<Variable, { nombre: string; corto: string; cortes: number[]; etiquetas: string[]; colores: string[] }> = {
  abst: { nombre: "Abstención", corto: "Abstención", cortes: [35, 45, 55, 65],
    etiquetas: ["< 35%", "35–45%", "45–55%", "55–65%", "≥ 65%"], colores: RAMPA },
  // Rangos cerrados a la derecha (≤ 5%): con valores de un decimal, "≤ 5" equivale a "< 5.05".
  ns: { nombre: "Registros sin información (NS)", corto: "NS", cortes: [5.05, 10.05, 25.05, 50.05],
    etiquetas: ["≤ 5%", "5–10%", "10–25%", "25–50%", "> 50%"], colores: RAMPA },
  cambio: { nombre: "Cambio vs. elección anterior del mismo tipo", corto: "Cambio", cortes: [-5, 0, 5],
    etiquetas: ["bajó más de 5 pp", "bajó hasta 5 pp", "subió hasta 5 pp", "subió más de 5 pp"],
    colores: ["cambio-1", "cambio-2", "cambio-3", "cambio-4"] },
};
const RANGOS_NS = ["5–10%", "10–25%", "25–50%", "50–99%", "100%"];

function aniosDe(tipo: Tipo, variable: Variable) {
  // El cambio necesita la elección anterior del mismo tipo: no existe para 2009 ni 2012.
  return ANIOS.filter((a) => (!tipo || TIPO_ANIO[a] === tipo) && (variable !== "cambio" || a >= 2015));
}

function valor(variable: Variable, anio: number): ExpressionSpecification {
  if (variable === "abst") return ["get", `abst_${anio}`];
  if (variable === "ns") return ["get", `ns_${anio}`];
  return ["-", ["get", `abst_${anio}`], ["get", `abst_${anio - 6}`]];
}

export default function Historico() {
  const [edo, setEdo] = useState<number | null>(null);
  const [tipo, setTipo] = useState<Tipo>("");
  const [variable, setVariable] = useState<Variable>("abst");
  const [anioElegido, setAnio] = useState(2024);
  const [seleccion, setSeleccion] = useState<string | null>(null);
  const { data, error } = useApi<Datos>("/api/historico", { edo, tipo: tipo || null });

  const anios = aniosDe(tipo, variable);
  const anio = anios.includes(anioElegido) ? anioElegido : anios[anios.length - 1];
  const v = VARIABLES[variable];
  const colores = v.colores.map(token);
  const requeridos = variable === "cambio" ? [`abst_${anio}`, `abst_${anio - 6}`] : [`${variable}_${anio}`];
  const datos = {
    filtro: ["all", ...ambito(edo), ...requeridos.map((a) => ["has", a])] as FilterSpecification,
    color: ["step", valor(variable, anio), colores[0], ...v.cortes.flatMap((c, i) => [c, colores[i + 1]])] as ExpressionSpecification,
  };
  const tooltip = (p: Propiedades): [string, string][] => {
    const filas: [string, string][] = [["Sección", p.clave]];
    if (p[`abst_${anio}`] === undefined) return [...filas, [String(anio), "sin registro con esta clave"]];
    filas.push([`Abstención ${anio}`, fmt.pct(p[`abst_${anio}`])], [`NS ${anio}`, fmt.pct(p[`ns_${anio}`])]);
    if (variable === "cambio" && p[`abst_${anio - 6}`] !== undefined)
      filas.push([`Cambio vs. ${anio - 6}`, fmt.pp(p[`abst_${anio}`] - p[`abst_${anio - 6}`])]);
    return filas;
  };
  const fila = data?.anios.find((a) => a.anio === anio);

  return (
    <>
      <div className="app">
        <aside className="panel" aria-label="Filtros e indicadores">
          <section>
            <h2>Filtros</h2>
            <SelectEntidad valor={edo} onCambio={setEdo} />
            <Segmentado nombre="tipo" etiqueta="Tipo de elección" opciones={TIPOS} valor={tipo} onCambio={setTipo} />
            <Segmentado nombre="variable" etiqueta="Variable del mapa" valor={variable} onCambio={setVariable}
              opciones={Object.entries(VARIABLES).map(([k, x]) => [k as Variable, x.corto])} />
            <Segmentado nombre="anio" etiqueta="Elección" valor={anio} onCambio={setAnio}
              opciones={anios.map((a) => [a, String(a)])} />
          </section>
          <section>
            <h2>Elección {anio}</h2>
            <div className="kpis" aria-live="polite">
              <Kpi etiqueta="Secciones con registro" valor={fila ? fmt.n(fila.secciones) : "…"} />
              <Kpi etiqueta="Abstención" valor={fila ? fmt.share(fila.abstencion) : "…"} />
              <Kpi etiqueta="Sin información (NS)" valor={fila ? fmt.share(fila.pct_ns) : "…"} />
              <Kpi etiqueta="En la cartografía" valor={fila ? fmt.share(fila.en_cartografia / fila.secciones) : "…"}
                nota={fila ? `${fmt.n(fila.en_cartografia)} de ${fmt.n(fila.secciones)}` : undefined} />
            </div>
          </section>
          <div className="note">
            Restricciones actuales del modelo 2027: la sección debe existir en 2021 y 2024, no cambiar de municipio ni
            de tipo entre ambas, y tener NS ≤ 10% de su lista nominal en los dos años.
          </div>
          {error && <div className="error" role="alert">No se pudieron cargar los datos: {error}</div>}
        </aside>
        <div className="map-wrap">
          <MapaSecciones datos={datos} tooltip={tooltip} bbox={data?.bbox ?? null} seleccion={seleccion} onSelect={setSeleccion} />
          <Leyenda items={[...v.etiquetas.map((e, i) => [colores[i], e] as [string, string]),
            ["var(--sin-estimacion)", `Sin registro en ${anio} o sin dato`]]} />
          {seleccion && <Ficha clave={seleccion} onClose={() => setSeleccion(null)} />}
        </div>
      </div>

      {data && (
        <div className="debajo">
          <section className="card">
            <h2>Abstención y registros sin información</h2>
            <p className="muted">
              Intermedias: 2009, 2015 y 2021 · Presidenciales: 2012, 2018 y 2024. Abstención = NV / (SV + NV);
              NS = registros sin información, como % de la lista nominal.
            </p>
            <div className="dos">
              <div>
                <h3>Abstención</h3>
                <Lineas titulo="Abstención por elección" formato={(x) => `${(x * 100).toFixed(0)}%`} formatoValor={fmt.share}
                  series={[{ nombre: "Abstención", color: token("accent"), puntos: data.anios.map((a) => ({ x: a.anio, y: a.abstencion })) }]} />
              </div>
              <div>
                <h3>Registros sin información (NS)</h3>
                <Lineas titulo="NS por elección" formato={(x) => `${(x * 100).toFixed(1)}%`} formatoValor={(x) => `${(x * 100).toFixed(2)}%`}
                  series={[{ nombre: "NS", color: token("accent"), puntos: data.anios.map((a) => ({ x: a.anio, y: a.pct_ns })) }]} />
              </div>
            </div>
            <table className="tabla">
              <thead>
                <tr><th>Año</th><th>Elección</th><th className="num">Secciones</th><th className="num">Lista nominal</th>
                  <th className="num">Votaron</th><th className="num">No votaron</th><th className="num">Sin información</th>
                  <th className="num">Abstención</th><th className="num">% NS</th></tr>
              </thead>
              <tbody>
                {data.anios.map((a) => (
                  <tr key={a.anio} onClick={() => setAnio(a.anio)} title="Ver en el mapa">
                    <td className="num">{a.anio}</td><td>{a.tipo}</td><td className="num">{fmt.n(a.secciones)}</td>
                    <td className="num">{fmt.n(a.ln)}</td><td className="num">{fmt.n(a.sv)}</td><td className="num">{fmt.n(a.nv)}</td>
                    <td className="num">{fmt.n(a.ns)}</td><td className="num">{fmt.share(a.abstencion)}</td><td className="num">{fmt.share(a.pct_ns)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <div className="dos">
            <section className="card">
              <h2>Secciones según su proporción de NS</h2>
              <p className="muted">Proporción de las secciones de cada elección; las de NS ≤ 5% no se grafican.</p>
              <Barras formato={fmt.share}
                partes={RANGOS_NS.map((r, i) => ({ clave: r, nombre: r === "100%" ? "100% (sin información)" : r, color: token(RAMPA[i]) }))}
                filas={data.anios.map((a) => ({
                  etiqueta: String(a.anio),
                  valores: Object.fromEntries(data.ns_rangos.filter((r) => r.anio === a.anio).map((r) => [r.rango, r.secciones / a.secciones])),
                }))} />
              <details className="tabla-oculta">
                <summary>Ver como tabla</summary>
                <table className="tabla">
                  <thead><tr><th>Año</th><th className="num">≤5%</th>{RANGOS_NS.map((r) => <th key={r} className="num">{r}</th>)}</tr></thead>
                  <tbody>
                    {data.anios.map((a) => (
                      <tr key={a.anio}>
                        <td className="num">{a.anio}</td>
                        {["≤5%", ...RANGOS_NS].map((r) => (
                          <td key={r} className="num">{fmt.n(data.ns_rangos.find((x) => x.anio === a.anio && x.rango === r)?.secciones ?? 0)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </details>
            </section>

            <section className="card">
              <h2>Cambios de secciones entre elecciones</h2>
              <p className="muted">Comparando cada elección con la anterior del filtro elegido.</p>
              <table className="tabla">
                <thead>
                  <tr><th>Elección</th><th>Vs.</th><th className="num">Secciones</th><th className="num">Nuevas</th>
                    <th className="num">Ya no están</th><th className="num">Otro municipio</th><th className="num">Otro tipo</th></tr>
                </thead>
                <tbody>
                  {data.cambios.map((c) => (
                    <tr key={c.anio}>
                      <td className="num">{c.anio}</td><td className="num">{c.comparada_con}</td><td className="num">{fmt.n(c.secciones)}</td>
                      <td className="num">{fmt.n(c.nuevas)}</td><td className="num">{fmt.n(c.desaparecidas)}</td>
                      <td className="num">{fmt.n(c.cambio_municipio)}</td><td className="num">{fmt.n(c.cambio_tipo)}</td>
                    </tr>
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
