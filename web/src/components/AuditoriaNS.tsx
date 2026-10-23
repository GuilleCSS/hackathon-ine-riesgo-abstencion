import { useState } from "react";
import type { ExpressionSpecification, FilterSpecification } from "maplibre-gl";
import Ficha from "./Ficha";
import MapaSecciones, { ambito, type Propiedades } from "./MapaSecciones";
import { Barras, Lineas } from "./graficas";
import { Kpi, Leyenda, Segmentado, SelectEntidad } from "./controles";
import { NIVELES, fmt, useApi, type AuditoriaNS as Datos } from "../lib/api";
import { nivelColor, token } from "../lib/tokens";

type Modo = "umbral" | "ns_2021" | "ns_2024";
const MODOS: [Modo, string][] = [["umbral", "Otro umbral"], ["ns_2021", "NS 2021"], ["ns_2024", "NS 2024"]];
const UMBRALES = [10, 15, 20, 25, 50, 100];
const RAMPA = ["rampa-1", "rampa-2", "rampa-3", "rampa-4", "rampa-5"];
const RANGOS_NS = ["0–5%", "5–10%", "10–25%", "25–50%", "> 50%"];
const TIPOS: Record<string, string> = { U: "Urbana", M: "Mixta", R: "Rural" };

/** Nivel con los umbrales congelados del semáforo (sólo indicativo fuera del universo oficial). */
const nivelDe = (pred: number, u: { q50: number; q80: number }) => (pred <= u.q50 ? "BAJO" : pred <= u.q80 ? "MEDIO" : "ALTO");

function capas(modo: Modo, umbral: number, edo: number | null, u: { q50: number; q80: number }) {
  const a = ambito(edo);
  if (modo !== "umbral") {
    const colores = RAMPA.map(token);
    return {
      datos: {
        filtro: ["all", ...a, [">", ["coalesce", ["get", modo], 0], 0]] as FilterSpecification,
        color: ["step", ["get", modo], colores[0], 5.05, colores[1], 10.05, colores[2], 25.05, colores[3], 50.05, colores[4]] as ExpressionSpecification,
      },
    };
  }
  // Las teselas guardan el NS con un decimal: "< umbral" evita contar 10.04% como dentro de 10%.
  const entra: ExpressionSpecification[] = [["<", ["get", "ns_2021"], umbral], ["<", ["get", "ns_2024"], umbral]];
  const excluida: ExpressionSpecification = ["==", ["get", "capa"], "ns_alto"];
  return {
    datos: {
      filtro: ["all", excluida, ...a, ...entra] as FilterSpecification,
      color: ["step", ["get", "pred"], token("riesgo-bajo"), u.q50, token("riesgo-medio"), u.q80, token("riesgo-alto")] as ExpressionSpecification,
    },
    extra: { filtro: ["all", excluida, ...a, ["!", ["all", ...entra]]] as FilterSpecification, color: token("ns-alto"), visible: true },
  };
}

export default function AuditoriaNS() {
  const [edo, setEdo] = useState<number | null>(null);
  const [modo, setModo] = useState<Modo>("umbral");
  const [umbral, setUmbral] = useState(25);
  const [seleccion, setSeleccion] = useState<string | null>(null);
  const { data, error } = useApi<Datos>("/api/auditoria-ns", { edo, umbral: umbral / 100 });
  const u = data?.umbrales ?? { q50: 42.82, q80: 51.07, q90: 55.44 };
  const k = data?.kpis;

  const tooltip = (p: Propiedades): [string, string][] => {
    const filas: [string, string][] = [["Sección", p.clave],
      ["NS 2021 / 2024", `${fmt.pct(p.ns_2021)} / ${fmt.pct(p.ns_2024)}`]];
    if (p.capa === "semaforo") filas.push(["Semáforo", `${p.nivel} · ${fmt.pct(p.pred)}`]);
    else if (p.capa === "ns_alto") filas.push(["Excluida por NS", `nivel indicativo ${nivelDe(p.pred, u)} · ${fmt.pct(p.pred)}`]);
    else filas.push(["Sin estimación", "fuera del universo comparable"]);
    return filas;
  };
  const leyenda: [string, string][] = modo === "umbral"
    ? [...NIVELES.map((n) => [nivelColor(n), `Entraría con ${umbral}%: ${n}`] as [string, string]),
       ["var(--ns-alto)", `Seguiría excluida con ${umbral}%`], ["var(--sin-estimacion)", "En el semáforo o sin estimación"]]
    : [...RANGOS_NS.map((r, i) => [token(RAMPA[i]), r] as [string, string]), ["var(--sin-estimacion)", "Sin NS o sin registro"]];
  const sel = (v: string) => data?.seleccion.filter((r) => r.variable.startsWith(v)) ?? [];

  return (
    <>
      <div className="app">
        <aside className="panel" aria-label="Filtros e indicadores">
          <section>
            <h2>Filtros</h2>
            <SelectEntidad valor={edo} onCambio={setEdo} />
            <Segmentado nombre="modo" etiqueta="Mostrar en el mapa" opciones={MODOS} valor={modo} onCambio={setModo} />
            {modo === "umbral" && (
              <Segmentado nombre="umbral" etiqueta="Umbral de NS para entrar al semáforo" valor={umbral} onCambio={setUmbral}
                opciones={UMBRALES.map((x) => [x, `${x}%`])} />
            )}
          </section>
          <section>
            <h2>Indicadores</h2>
            <div className="kpis" aria-live="polite">
              <Kpi etiqueta="Excluidas por NS" valor={k ? fmt.n(k.excluidas) : "…"}
                nota={k ? `${fmt.share(k.excluidas / (k.excluidas + k.en_semaforo))} de las comparables` : undefined} />
              <Kpi etiqueta="De ellas, serían ALTO" valor={k ? fmt.share(k.excluidas ? k.excluidas_alto / k.excluidas : null) : "…"}
                nota="En el semáforo: 20%" />
              <Kpi etiqueta={`Entrarían con ${umbral}%`} valor={k ? fmt.n(k.entrarian) : "…"} ancho
                nota={k ? `${fmt.n(k.entrarian_alto)} de ellas en ALTO (umbrales congelados)` : undefined} />
            </div>
          </section>
          <div className="note">
            El NS viene de casillas completas y no sesga la abstención medida, pero el filtro de NS ≤ 10% deja fuera
            secciones con más riesgo que el promedio. Ver las conclusiones abajo.
          </div>
          {error && <div className="error" role="alert">No se pudo cargar la auditoría: {error}</div>}
        </aside>
        <div className="map-wrap">
          <MapaSecciones {...capas(modo, umbral, edo, u)} tooltip={tooltip} bbox={data?.bbox ?? null}
            seleccion={seleccion} onSelect={setSeleccion} />
          <Leyenda items={leyenda} />
          {seleccion && <Ficha clave={seleccion} onClose={() => setSeleccion(null)} />}
        </div>
      </div>

      {data && (
        <div className="debajo">
          <section className="card prose">
            <h2>Conclusiones</h2>
            <ol>
              <li><strong>El NS viene de casillas completas, no de personas.</strong> En secciones con NS parcial, la
                proporción se amontona en 1/2 ({fmt.share(data.resumen.concentracion_fracciones["1/2"])} de las secciones),
                1/3 ({fmt.share(data.resumen.concentracion_fracciones["1/3"])}) y 1/4; si fuera uniforme, cada fracción tendría 4.2%.</li>
              <li><strong>Afecta igual a todas las edades y sexos dentro de cada sección</strong> (razón de{" "}
                {data.resumen.uniformidad_razon_min_max[0].toFixed(2)} a {data.resumen.uniformidad_razon_min_max[1].toFixed(2)}).</li>
              <li><strong>No es aleatorio entre secciones:</strong> pesa más en secciones grandes, mixtas y de más abstención,
                y en ciertas entidades. La repetición en la misma sección es moderada.</li>
              <li><strong>No esconde abstención:</strong> donde hay NS se mide {fmt.pp(data.resumen.sesgo_residuo_ns_alto_pp)} de
                abstención sobre lo esperado, décimas de punto y en dirección contraria a la temida.</li>
              <li><strong>El filtro sí sesga el semáforo:</strong> {fmt.share(data.resumen.excluidas_alto_indicativo)} de las
                excluidas serían ALTO, contra 20% en el semáforo.</li>
            </ol>
            <p>
              Propuesta para el equipo (no aplicada): incluir las secciones con NS parcial marcadas como estimación con menos
              registros, o subir el umbral a 25%. Detalle en <code>reports/auditoria_ns/AUDITORIA_NS.md</code>.
            </p>
          </section>

          <section className="card">
            <h2>Cuánto NS hay</h2>
            <div className="dos">
              <Lineas titulo="NS como % de la lista nominal" formato={(x) => `${(x * 100).toFixed(0)}%`} formatoValor={fmt.share}
                series={[{ nombre: "NS", color: token("accent"), puntos: data.magnitud.map((m) => ({ x: m.anio, y: m.pct_lista_nominal_ns })) }]} />
              <table className="tabla">
                <thead><tr><th>Año</th><th className="num">Con NS</th><th className="num">NS &gt; 10%</th><th className="num">100% NS</th>
                  <th className="num">% de la lista</th></tr></thead>
                <tbody>
                  {data.magnitud.map((m) => (
                    <tr key={m.anio}><td className="num">{m.anio}</td><td className="num">{fmt.n(m.con_ns)}</td>
                      <td className="num">{fmt.n(m.ns_mayor_10)}</td><td className="num">{fmt.n(m.ns_100)}</td>
                      <td className="num">{fmt.share(m.pct_lista_nominal_ns)}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="muted">Entre 94% y 99% del NS de cada año está en secciones con más de 10%: es un problema concentrado.</p>
          </section>

          <div className="dos">
            <section className="card">
              <h2>De dónde viene</h2>
              <p className="muted">Secciones con NS parcial cuya proporción de NS está a ±2 pp de cada fracción (uniforme ≈ 4.2%).</p>
              <Barras formato={fmt.share} partes={[{ clave: "v", nombre: "Secciones cerca de la fracción", color: token("accent") }]}
                filas={Object.entries(data.resumen.concentracion_fracciones).map(([f, v]) => ({ etiqueta: f, valores: { v } }))} />
              <h3>NS del grupo entre NS de su sección</h3>
              <table className="tabla">
                <thead><tr><th>Año</th>{["18–24", "25–34", "35–44", "45–59", "60+", "Hombres", "Mujeres"].map((g) => <th key={g} className="num">{g}</th>)}</tr></thead>
                <tbody>
                  {data.edad_sexo.map((r) => (
                    <tr key={r.anio}><td className="num">{r.anio}</td>
                      {["18–24", "25–34", "35–44", "45–59", "60+", "Hombres", "Mujeres"].map((g) => <td key={g} className="num">{r[g].toFixed(2)}</td>)}</tr>
                  ))}
                </tbody>
              </table>
            </section>
            <section className="card">
              <h2>¿Es aleatorio entre secciones?</h2>
              <p className="muted">Proporción de sección-elección 2015–2024 con NS &gt; 10%.</p>
              {[["Lista nominal", "Tamaño de la sección"], ["Tipo", "Tipo de sección"], ["Abstención", "Abstención en la elección anterior"]].map(([v, titulo]) => (
                <div key={v}>
                  <h3>{titulo}</h3>
                  <Barras formato={fmt.share} partes={[{ clave: "v", nombre: "NS > 10%", color: token("rampa-3") }]} escala={0.2}
                    filas={sel(v).map((r) => ({ etiqueta: TIPOS[r.categoria] ?? r.categoria, valores: { v: r.tasa_ns_alto } }))} />
                </div>
              ))}
              <p className="muted">
                Repetición: tener NS &gt; 10% hace {Math.min(...data.persistencia.slice(1).map((p) => p.veces_mas_probable)).toFixed(1)}–
                {Math.max(...data.persistencia.slice(1).map((p) => p.veces_mas_probable)).toFixed(1)} veces más probable volver a tenerlo
                en la siguiente elección; la mayoría no repite.
              </p>
            </section>
          </div>

          <section className="card">
            <h2>¿Sesga la abstención medida?</h2>
            <p className="muted">
              Abstención observada menos la esperada (elección anterior del mismo tipo + cambio de su entidad), en secciones
              que estaban limpias la vez anterior. Negativo = el NS escondería a quienes no votaron.
            </p>
            <table className="tabla">
              <thead><tr><th>NS este año</th>{[2015, 2018, 2021, 2024].map((y) => <th key={y} className="num">{y}</th>)}</tr></thead>
              <tbody>
                {["0%", "0–5%", "5–10%", "10–25%", "25–50%", "50–99.9%"].map((b) => (
                  <tr key={b}><td>{b}</td>
                    {[2015, 2018, 2021, 2024].map((y) => {
                      const r = data.sesgo.find((s) => s.anio === y && s.NS_BUCKET === b);
                      return <td key={y} className="num">{r ? `${fmt.pp(r.residuo_medio_pp)} ± ${r.error_estandar_pp.toFixed(1)}` : "—"}</td>;
                    })}</tr>
                ))}
              </tbody>
            </table>
          </section>

          <div className="dos">
            <section className="card">
              <h2>Qué le hace el filtro al semáforo</h2>
              <p className="muted">Nivel con los umbrales congelados: semáforo oficial vs. secciones excluidas por NS.</p>
              <Barras escala={1} formato={fmt.share}
                partes={NIVELES.map((n) => ({ clave: n, nombre: n, color: token(`riesgo-${n.toLowerCase()}`) }))}
                filas={[
                  { etiqueta: "Semáforo oficial", valores: Object.fromEntries(data.niveles.map((n) => [n.nivel, n.semaforo_oficial])) },
                  { etiqueta: "Excluidas por NS", valores: Object.fromEntries(data.niveles.map((n) => [n.nivel, n.excluidas_por_ns])) },
                ]} />
              <h3>Entidades que más pierden</h3>
              <table className="tabla">
                <thead><tr><th>Entidad</th><th className="num">Comparables</th><th className="num">Excluidas</th><th className="num">%</th></tr></thead>
                <tbody>
                  {data.por_entidad.slice(0, 10).map((r) => (
                    <tr key={r.entidad}><td>{r.entidad}</td><td className="num">{fmt.n(r.comparables)}</td>
                      <td className="num">{fmt.n(r.excluidas_por_ns)}</td><td className="num">{fmt.share(r.pct_excluidas)}</td></tr>
                  ))}
                </tbody>
              </table>
            </section>
            <section className="card">
              <h2>Sensibilidad al umbral</h2>
              <p className="muted">Nacional; los percentiles se recalculan sobre cada universo. Clic en una fila para verla en el mapa.</p>
              <table className="tabla">
                <thead><tr><th className="num">Umbral</th><th className="num">Secciones</th><th className="num">q80</th><th className="num">ALTO</th>
                  <th className="num">ALTO oficial que sigue</th><th className="num">ALTO nuevas</th></tr></thead>
                <tbody>
                  {data.sensibilidad.map((r) => {
                    const t = Math.round(r.umbral_ns * 100);
                    return (
                      <tr key={t} onClick={() => UMBRALES.includes(t) && (setModo("umbral"), setUmbral(t))}
                        className={t === umbral && modo === "umbral" ? "activa" : undefined}>
                        <td className="num">{t}%</td><td className="num">{fmt.n(r.secciones)}</td><td className="num">{fmt.share(r.q80)}</td>
                        <td className="num">{fmt.n(r.alto)}</td><td className="num">{fmt.share(r.alto_oficial_que_sigue_alto)}</td>
                        <td className="num">{fmt.n(r.alto_nuevas)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </section>
          </div>
        </div>
      )}
    </>
  );
}
