import { useState } from "react";
import type { FilterSpecification } from "maplibre-gl";
import Ficha from "./Ficha";
import MapaSecciones, { ambito, type Propiedades } from "./MapaSecciones";
import { Barras, Lineas } from "./graficas";
import { Kpi, Leyenda, Segmentado, SelectEntidad } from "./controles";
import { fmt, useApi, type Grupos as Datos } from "../lib/api";
import { token } from "../lib/tokens";

type Tipo = "" | "intermedia" | "presidencial";
const TIPOS: [Tipo, string][] = [["", "Todas"], ["intermedia", "Intermedias"], ["presidencial", "Presidenciales"]];
const color = (g: number) => token(`grupo-${g}`);
const signo = (v: number) => `${v > 0 ? "+" : ""}${v.toFixed(1)}`;

export default function Grupos() {
  const [edo, setEdo] = useState<number | null>(null);
  const [tipo, setTipo] = useState<Tipo>("");
  // Un grupo a la vez en el mapa: con los 5 colores juntos algunos pares no se distinguen.
  const [grupo, setGrupo] = useState(3);
  const [seleccion, setSeleccion] = useState<string | null>(null);
  const { data, error } = useApi<Datos>("/api/grupos", { edo, tipo: tipo || null });

  const nombres = data?.config.groups ?? {};
  const ids = Object.keys(nombres).map(Number);
  const datos = {
    filtro: ["all", ...ambito(edo), ["==", ["get", "grupo"], grupo]] as FilterSpecification,
    color: color(grupo),
  };
  const tooltip = (p: Propiedades): [string, string][] => [
    ["Sección", p.clave],
    ["Grupo", p.grupo ? nombres[p.grupo] : "sin grupo (no tiene las 6 elecciones o NS alto)"],
    ["Abstención 2021 / 2024", `${fmt.pct(p.abst_2021)} / ${fmt.pct(p.abst_2024)}`],
  ];
  const unidad = edo === null ? "entidad" : "municipio";
  // Filas de la composición ordenadas por la proporción del grupo elegido en el mapa.
  const comp = data ? Object.values(Object.groupBy(data.composicion, (c) => String(c.clave))) : [];
  const filas = comp
    .map((cs) => ({ etiqueta: cs![0].nombre ?? String(cs![0].clave), total: cs![0].total,
      valores: Object.fromEntries(cs!.map((c) => [String(c.grupo), c.pct])) }))
    .sort((a, b) => (b.valores[grupo] ?? 0) - (a.valores[grupo] ?? 0));

  return (
    <>
      <div className="app">
        <aside className="panel" aria-label="Filtros e indicadores">
          <section>
            <h2>Filtros</h2>
            <SelectEntidad valor={edo} onCambio={setEdo} />
            <Segmentado nombre="tipo" etiqueta="Tipo de elección (gráfica)" opciones={TIPOS} valor={tipo} onCambio={setTipo} />
            <fieldset>
              <legend>Grupo en el mapa</legend>
              <div className="opciones">
                {ids.map((g) => (
                  <label key={g}>
                    <input type="radio" name="grupo" checked={g === grupo} onChange={() => setGrupo(g)} />
                    <span className="swatch" style={{ background: color(g) }} />{nombres[g]}
                  </label>
                ))}
              </div>
            </fieldset>
          </section>
          <section>
            <h2>Indicadores</h2>
            <div className="kpis" aria-live="polite">
              <Kpi etiqueta="Secciones agrupadas" valor={data ? fmt.n(data.kpis.agrupadas) : "…"} />
              <Kpi etiqueta="Del total de secciones" valor={data ? fmt.share(data.kpis.agrupadas_en_cartografia / data.kpis.cartografia) : "…"} />
              <Kpi etiqueta="Separación entre grupos (silhouette)" valor={data ? data.config.silhouette_k.toFixed(2) : "…"} ancho
                nota="De −1 a 1. Cerca de 0.25: estructura moderada, grupos con fronteras difusas." />
            </div>
          </section>
          <div className="note">
            Tipología descriptiva con 2009–2024. Para usarla en el modelo hay que reconstruirla sólo con elecciones
            anteriores a la que se predice.
          </div>
          {error && <div className="error" role="alert">No se pudieron cargar los grupos: {error}</div>}
        </aside>
        <div className="map-wrap">
          <MapaSecciones datos={datos} tooltip={tooltip} bbox={data?.bbox ?? null} seleccion={seleccion} onSelect={setSeleccion} />
          <Leyenda items={[[color(grupo), nombres[grupo] ?? "Grupo"], ["var(--sin-estimacion)", "Otros grupos o sin grupo"]]} />
          {seleccion && <Ficha clave={seleccion} onClose={() => setSeleccion(null)} />}
        </div>
      </div>

      {data && (
        <div className="debajo">
          <section className="card">
            <h2>Perfil de los grupos</h2>
            <p className="muted">
              Nivel, tendencia y volatilidad en puntos porcentuales frente a la abstención nacional de cada elección
              (negativo = votan más que el promedio). Tendencia = promedio 2021–2024 menos promedio 2009–2012.
            </p>
            <table className="tabla">
              <thead>
                <tr><th>Grupo</th><th className="num">Secciones</th><th className="num">%</th><th className="num">Intermedias (pp)</th>
                  <th className="num">Presidenciales (pp)</th><th className="num">Tendencia (pp)</th><th className="num">Volatilidad (pp)</th>
                  <th className="num">% urbana</th><th className="num">% rural</th><th className="num">Lista nominal mediana</th><th className="num">% 18–24</th></tr>
              </thead>
              <tbody>
                {data.perfil.map((p) => (
                  <tr key={p.grupo} onClick={() => setGrupo(p.grupo)} title="Ver en el mapa">
                    <td><span className="swatch" style={{ background: color(p.grupo) }} /> {p.nombre}</td>
                    <td className="num">{fmt.n(p.secciones)}</td><td className="num">{fmt.share(p.pct)}</td>
                    <td className="num">{signo(p.intermedias)}</td><td className="num">{signo(p.presidenciales)}</td>
                    <td className="num">{signo(p.tendencia)}</td><td className="num">{p.volatilidad.toFixed(1)}</td>
                    <td className="num">{fmt.share(p.urbana)}</td><td className="num">{fmt.share(p.rural)}</td>
                    <td className="num">{fmt.n(Math.round(p.ln_mediana))}</td><td className="num">{fmt.share(p.jovenes)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section className="card">
            <h2>Abstención de cada grupo en el tiempo</h2>
            <p className="muted">
              Abstención agregada (no votaron / votaron + no votaron) de las secciones de cada grupo. La línea punteada es
              el total de las secciones agrupadas del territorio elegido.
              {tipo === "" && " Con \"Todas\" la línea alterna entre intermedias (más abstención) y presidenciales."}
            </p>
            <Lineas titulo="Abstención por grupo y elección" formato={(x) => `${(x * 100).toFixed(0)}%`} formatoValor={fmt.share}
              series={[
                ...ids.map((g) => ({ nombre: nombres[g], color: color(g),
                  puntos: data.trayectorias.filter((t) => t.grupo === g).map((t) => ({ x: t.anio, y: t.abstencion })) })),
                { nombre: "Todas las agrupadas", color: token("ink-2"), punteada: true,
                  puntos: data.trayectorias.filter((t) => t.grupo === null).map((t) => ({ x: t.anio, y: t.abstencion })) },
              ]} />
          </section>

          <section className="card">
            <h2>Composición por {unidad}</h2>
            <p className="muted">
              {edo !== null && "Los 30 municipios con más secciones agrupadas. "}
              Ordenado por la proporción de "{nombres[grupo]}", el grupo elegido para el mapa.
            </p>
            <Barras escala={1} formato={fmt.share} filas={filas}
              partes={ids.map((g) => ({ clave: String(g), nombre: nombres[g], color: color(g) }))} />
            <details className="tabla-oculta">
              <summary>Ver como tabla</summary>
              <table className="tabla">
                <thead><tr><th>{unidad === "entidad" ? "Entidad" : "Municipio"}</th><th className="num">Secciones</th>
                  {ids.map((g) => <th key={g} className="num">{nombres[g]}</th>)}</tr></thead>
                <tbody>
                  {filas.map((f) => (
                    <tr key={f.etiqueta}>
                      <td>{f.etiqueta}</td><td className="num">{fmt.n(f.total)}</td>
                      {ids.map((g) => <td key={g} className="num">{fmt.share(f.valores[g] ?? 0)}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          </section>

          <section className="card prose">
            <h2>Cómo se formaron los grupos y limitaciones</h2>
            <ul>
              <li><strong>Universo:</strong> {fmt.n(data.config.sections_clustered)} secciones con abstención calculable en
                las 6 elecciones y NS ≤ {fmt.share(data.config.max_ns)} en todas. Las secciones nuevas o renumeradas no tienen grupo.</li>
              <li><strong>Variables</strong> (pp frente a la abstención nacional de cada elección): nivel en intermedias,
                nivel en presidenciales, tendencia (2021–2024 vs. 2009–2012) y volatilidad. Se estandarizan y se agrupan
                con k-means (k = {data.config.k}).</li>
              <li><strong>Nombres:</strong> tendencia mayor a ±{data.config.naming_rules_pp.trend} pp → Mejorando / Empeorando;
                si no, nivel mayor a ±{data.config.naming_rules_pp.level} pp → alta / baja persistente; si no, En el promedio.</li>
              <li><strong>Separación:</strong> silhouette {data.config.silhouette_k.toFixed(2)}. Las secciones forman un
                continuo; los grupos son una tipología con fronteras difusas.</li>
              <li><strong>Uso:</strong> descriptivo. Detalle en <code>reports/clustering/CLUSTER_METHOD.md</code>.</li>
            </ul>
            <table className="tabla">
              <thead><tr><th className="num">k (grupos)</th><th className="num">Silhouette</th><th>Tamaños</th></tr></thead>
              <tbody>
                {data.k_seleccion.map((r) => (
                  <tr key={r.k}><td className="num">{r.k}</td><td className="num">{Number(r.silhouette).toFixed(3)}</td>
                    <td className="num">{r.tamanos.split("|").map((n) => fmt.n(Number(n))).join(" · ")}</td></tr>
                ))}
              </tbody>
            </table>
          </section>
        </div>
      )}
    </>
  );
}
