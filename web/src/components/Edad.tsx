import { useState } from "react";
import type { ExpressionSpecification, FilterSpecification } from "maplibre-gl";
import Ficha from "./Ficha";
import MapaSecciones, { ambito, type Propiedades } from "./MapaSecciones";
import { Lineas } from "./graficas";
import { Kpi, Leyenda, Segmentado, SelectEntidad } from "./controles";
import { ANIOS, TIPO_ANIO, fmt, useApi, type Edad as Datos } from "../lib/api";
import { token } from "../lib/tokens";

type Variable = "res" | "jov";
const VARIABLES: Record<Variable, { corto: string; cortes: number[]; etiquetas: string[]; colores: string[] }> = {
  res: { corto: "No explicada por la edad", cortes: [-10, 0, 10],
    etiquetas: ["< −10 pp (menos de lo esperado)", "−10 a 0 pp", "0 a +10 pp", "> +10 pp (más de lo esperado)"],
    colores: ["cambio-1", "cambio-2", "cambio-3", "cambio-4"] },
  jov: { corto: "Jóvenes 18–24", cortes: [10, 12, 14, 17], etiquetas: ["< 10%", "10–12%", "12–14%", "14–17%", "≥ 17%"],
    colores: ["rampa-1", "rampa-2", "rampa-3", "rampa-4", "rampa-5"] },
};
const PERIODOS: [number, number][] = [[2009, 2015], [2015, 2021], [2009, 2021], [2012, 2018], [2018, 2024], [2012, 2024]];
const GRUPOS = ["18–24", "25–34", "35–44", "45–59", "60+"];
const pct0 = (x: number) => `${(x * 100).toFixed(0)}%`;
const signo = (v: number) => `${v > 0 ? "+" : ""}${v.toFixed(2)}`;

export default function Edad() {
  const [edo, setEdo] = useState<number | null>(null);
  const [variable, setVariable] = useState<Variable>("res");
  const [anio, setAnio] = useState(2024);
  const [anioCurva, setAnioCurva] = useState(2024);
  const [seleccion, setSeleccion] = useState<string | null>(null);
  const { data, error } = useApi<Datos>("/api/edad", { edo });

  const v = VARIABLES[variable];
  const colores = v.colores.map(token);
  const prop = variable === "res" ? `edad_res_${anio}` : `jovenes_${anio}`;
  const datos = {
    filtro: ["all", ...ambito(edo), ["has", prop]] as FilterSpecification,
    color: ["step", ["get", prop], colores[0], ...v.cortes.flatMap((c, i) => [c, colores[i + 1]])] as ExpressionSpecification,
  };
  const tooltip = (p: Propiedades): [string, string][] => {
    if (p[`edad_res_${anio}`] === undefined) return [["Sección", p.clave], [String(anio), "sin registro con esta clave"]];
    const obs = p[`abst_${anio}`];
    return [["Sección", p.clave], [`Abstención ${anio}`, fmt.pct(obs)],
      ["Esperada por su edad", fmt.pct(obs - p[`edad_res_${anio}`])], ["No explicada", fmt.pp(p[`edad_res_${anio}`])],
      ["Jóvenes 18–24", fmt.pct(p[`jovenes_${anio}`])]];
  };

  const r = data?.resumen;
  const est = data?.entidad?.find((e) => e.anio === anio);
  const curva = (anioX: number, sexo: string) =>
    data?.curva.filter((c) => c.anio === anioX && c.sexo === sexo).map((c) => ({ x: c.edad, y: c.abstencion })) ?? [];
  const rampa = ["rampa-2", "rampa-3", "rampa-5"].map(token);
  const familia = (tipo: string) => ANIOS.filter((a) => TIPO_ANIO[a] === tipo)
    .map((a, i) => ({ nombre: String(a), color: rampa[i], puntos: curva(a, "Total") }));
  const total = (de: number, a: number) => data?.kitagawa.find((k) => k.de === de && k.a === a && k.grupo === "Total");

  return (
    <>
      <div className="app">
        <aside className="panel" aria-label="Filtros e indicadores">
          <section>
            <h2>Filtros</h2>
            <SelectEntidad valor={edo} onCambio={setEdo} />
            <Segmentado nombre="variable" etiqueta="Mostrar en el mapa" valor={variable} onCambio={setVariable}
              opciones={Object.entries(VARIABLES).map(([k, x]) => [k as Variable, x.corto])} />
            <Segmentado nombre="anio" etiqueta="Elección" valor={anio} onCambio={setAnio} opciones={[[2021, "2021"], [2024, "2024"]]} />
          </section>
          <section>
            <h2>{est ? `${est.entidad} · ${anio}` : `Nacional · ${anio}`}</h2>
            <div className="kpis" aria-live="polite">
              {est ? (
                <>
                  <Kpi etiqueta="Abstención" valor={fmt.share(est.observada)} />
                  <Kpi etiqueta="Esperada por su edad" valor={fmt.share(est.esperada_por_edad)} />
                  <Kpi etiqueta="No explicada por la edad" valor={fmt.pp(est.diferencia_no_explicada_pp)} />
                  <Kpi etiqueta="Brecha 18–24 vs. 60+" valor={fmt.pp(est.brecha_jovenes_mayores_pp)} />
                </>
              ) : (
                <>
                  <Kpi etiqueta="Brecha 18–24 vs. 60+" valor={r ? fmt.pp(r.brecha_18_24_menos_60_pp[anio]) : "…"} />
                  <Kpi etiqueta="Hombres − mujeres" valor={r ? fmt.pp(r.brecha_hombres_menos_mujeres_pp[anio]) : "…"} />
                  <Kpi etiqueta="Diferencias entre secciones que explica la edad" ancho
                    valor={r ? `R² ${r.r2_edad_secciones[anio].toFixed(2)}` : "…"}
                    nota="Abstención esperada si cada grupo de edad votara como el promedio nacional." />
                </>
              )}
            </div>
          </section>
          <div className="note">
            Rojo: la sección se abstiene más de lo que esperaría su pirámide de edad; azul: menos. La diferencia es
            el efecto del lugar, no de la edad.
          </div>
          {error && <div className="error" role="alert">No se pudo cargar la descomposición: {error}</div>}
        </aside>
        <div className="map-wrap">
          <MapaSecciones datos={datos} tooltip={tooltip} bbox={data?.bbox ?? null} seleccion={seleccion} onSelect={setSeleccion} />
          <Leyenda items={[...v.etiquetas.map((e, i) => [colores[i], e] as [string, string]),
            ["var(--sin-estimacion)", `Sin registro en ${anio}`]]} />
          {seleccion && <Ficha clave={seleccion} onClose={() => setSeleccion(null)} />}
        </div>
      </div>

      {data && r && (
        <div className="debajo">
          <section className="card prose">
            <h2>Conclusiones</h2>
            <ol>
              <li><strong>La curva de edad es estable.</strong> A los 18 años se vota más que de 19 a 30 (primer voto); la
                abstención es máxima cerca de los 25 y mínima entre los {Math.min(...Object.values(r.edad_con_menos_abstencion))} y{" "}
                {Math.max(...Object.values(r.edad_con_menos_abstencion))} años.</li>
              <li><strong>El envejecimiento baja la abstención, pero poco:</strong> {fmt.pp(r.largo_plazo["2009-2021"].composicion_pp)} de
                2009 a 2021 y {fmt.pp(r.largo_plazo["2012-2024"].composicion_pp)} de 2012 a 2024. Lo demás es comportamiento.</li>
              <li><strong>En presidenciales el comportamiento empeoró más de lo que se ve:</strong>{" "}
                {fmt.pp(r.largo_plazo["2012-2024"].comportamiento_pp)} de 2012 a 2024, disimulado por el envejecimiento.</li>
              <li><strong>Los hombres se abstienen más que las mujeres:</strong> {fmt.pp(r.brecha_hombres_menos_mujeres_pp["2024"])} en
                2024, hasta {fmt.pp(r.brecha_sexo_max_2024.pp)} a los {r.brecha_sexo_max_2024.edad} años.</li>
              <li><strong>La edad casi no explica el riesgo territorial:</strong> de los {r.brecha_alto_bajo_pp.toFixed(1)} pp entre
                secciones ALTO y BAJO de 2027, explica {r.brecha_explicada_por_edad_pp.toFixed(1)} pp
                ({fmt.share(r.parte_explicada_por_edad)}).</li>
              <li><strong>La abstención cae de golpe a los 65 años desde 2021</strong> ({fmt.pp(data.salto_65.find((s) => s.anio === 2024 && s.grupo === "Total")?.salto_65_pp)} en
                2024; antes, como mucho −0.9 pp). Coincide con la edad de acceso a la pensión universal para adultos
                mayores; es una asociación por verificar, no un efecto causal.</li>
            </ol>
          </section>

          <section className="card">
            <h2>Abstención por edad y sexo</h2>
            <Segmentado nombre="anio-curva" etiqueta="Elección" valor={anioCurva} onCambio={setAnioCurva}
              opciones={ANIOS.map((a) => [a, `${a} (${TIPO_ANIO[a] === "intermedia" ? "inter." : "presid."})`])} />
            <Lineas titulo={`Abstención por edad y sexo, ${anioCurva}`} formato={pct0} formatoValor={fmt.share}
              series={[
                { nombre: "Hombres", color: token("grupo-1"), puntos: curva(anioCurva, "Hombres") },
                { nombre: "Mujeres", color: token("grupo-2"), puntos: curva(anioCurva, "Mujeres") },
                { nombre: "Total", color: token("ink-2"), punteada: true, puntos: curva(anioCurva, "Total") },
              ]} />
            <p className="muted">Edad simple de 18 a 90 (90 = 90 años o más). El eje marca cada 10 años.</p>
            <h3>Salto a los 65 años</h3>
            <table className="tabla">
              <thead><tr><th>Grupo</th>{ANIOS.map((a) => <th key={a} className="num">{a}</th>)}</tr></thead>
              <tbody>
                {["Total", "Hombres", "Mujeres", "Tipo U", "Tipo M", "Tipo R"].map((g) => (
                  <tr key={g}><td>{g.replace("Tipo U", "Urbana").replace("Tipo M", "Mixta").replace("Tipo R", "Rural")}</td>
                    {ANIOS.map((a) => {
                      const s = data.salto_65.find((x) => x.anio === a && x.grupo === g);
                      return <td key={a} className="num">{s ? `${fmt.pp(s.salto_65_pp)} (${fmt.pp(s.pendiente_normal_pp)})` : "—"}</td>;
                    })}</tr>
                ))}
              </tbody>
            </table>
            <p className="muted">
              Cambio de abstención de los 64 a los 65 años; entre paréntesis, la pendiente normal entre un año de edad y el
              siguiente. Según la prensa, la pensión para adultos mayores se paga desde los 65 años a partir de julio de 2021
              (la elección de 2021 fue en junio).
            </p>
            <div className="dos">
              <div><h3>Intermedias</h3><Lineas titulo="Abstención por edad en intermedias" formato={pct0} formatoValor={fmt.share} series={familia("intermedia")} /></div>
              <div><h3>Presidenciales</h3><Lineas titulo="Abstención por edad en presidenciales" formato={pct0} formatoValor={fmt.share} series={familia("presidencial")} /></div>
            </div>
          </section>

          <section className="card">
            <h2>¿Por qué cambió la abstención? (Kitagawa)</h2>
            <p className="muted">
              Composición = efecto de que cambie el peso de cada grupo de edad (el electorado envejece). Comportamiento =
              efecto de que cada grupo se abstenga más o menos. Suman el cambio total.
            </p>
            <div className="dos">
              <table className="tabla">
                <thead><tr><th>Periodo</th><th className="num">Abstención</th><th className="num">Cambio</th>
                  <th className="num">Composición</th><th className="num">Comportamiento</th></tr></thead>
                <tbody>
                  {PERIODOS.map(([de, a]) => {
                    const t = total(de, a);
                    return t && (
                      <tr key={`${de}-${a}`}><td>{de}→{a} <span className="muted">({t.tipo.slice(0, 5)}.)</span></td>
                        <td className="num">{t.abstencion_de!.toFixed(1)}% → {t.abstencion_a!.toFixed(1)}%</td>
                        <td className="num">{signo(t.cambio_pp!)}</td><td className="num">{signo(t.composicion_pp)}</td>
                        <td className="num">{signo(t.comportamiento_pp)}</td></tr>
                    );
                  })}
                </tbody>
              </table>
              <table className="tabla">
                <thead><tr><th>Comportamiento (pp)</th>{GRUPOS.map((g) => <th key={g} className="num">{g}</th>)}</tr></thead>
                <tbody>
                  {PERIODOS.map(([de, a]) => (
                    <tr key={`${de}-${a}`}><td>{de}→{a}</td>
                      {GRUPOS.map((g) => {
                        const k = data.kitagawa.find((x) => x.de === de && x.a === a && x.grupo === g);
                        return <td key={g} className="num">{k ? signo(k.comportamiento_pp) : "—"}</td>;
                      })}</tr>
                  ))}
                </tbody>
              </table>
            </div>
            <h3>Abstención y peso de cada grupo</h3>
            <table className="tabla">
              <thead><tr><th>Año</th>{GRUPOS.map((g) => <th key={g} className="num">{g}</th>)}<th className="num">18–24 vs. 60+</th></tr></thead>
              <tbody>
                {ANIOS.map((y) => (
                  <tr key={y}><td className="num">{y}</td>
                    {GRUPOS.map((g) => {
                      const t = data.tasas.find((x) => x.anio === y && x.grupo === g);
                      return <td key={g} className="num">{t ? `${fmt.share(t.abstencion)} (${pct0(t.peso)})` : "—"}</td>;
                    })}
                    <td className="num">{fmt.pp(r.brecha_18_24_menos_60_pp[y])}</td></tr>
                ))}
              </tbody>
            </table>
            <p className="muted">Entre paréntesis, el peso del grupo entre quienes tienen participación conocida.</p>
          </section>

          <div className="dos">
            <section className="card">
              <h2>¿Cuánto explica la edad las diferencias?</h2>
              <table className="tabla">
                <thead><tr><th>Año</th><th className="num">Variación observada</th><th className="num">Esperada por edad</th><th className="num">R²</th></tr></thead>
                <tbody>
                  {data.estandarizacion.map((e) => (
                    <tr key={e.anio}><td className="num">{e.anio}</td><td className="num">{e.de_observada_pp.toFixed(1)} pp</td>
                      <td className="num">{e.de_esperada_por_edad_pp.toFixed(1)} pp</td><td className="num">{e.r2.toFixed(3)}</td></tr>
                  ))}
                </tbody>
              </table>
              <p className="muted">Desviación estándar entre secciones, ponderada por personas con participación conocida.</p>
              <h3>Semáforo 2027 por nivel</h3>
              <table className="tabla">
                <thead><tr><th>Nivel</th><th className="num">18–24</th><th className="num">60+</th>
                  <th className="num">Abstención 2021</th><th className="num">Esperada por edad</th></tr></thead>
                <tbody>
                  {data.niveles.map((n) => (
                    <tr key={n.nivel}><td>{n.nivel}</td><td className="num">{fmt.share(n.jovenes_18_24)}</td><td className="num">{fmt.share(n.mayores_60)}</td>
                      <td className="num">{fmt.share(n.observada_2021)}</td><td className="num">{fmt.share(n.esperada_por_edad_2021)}</td></tr>
                  ))}
                </tbody>
              </table>
            </section>
            <section className="card">
              <h2>Entidades: abstención no explicada por la edad (2024)</h2>
              <table className="tabla">
                <thead><tr><th>Entidad</th><th className="num">Observada</th><th className="num">Esperada</th>
                  <th className="num">No explicada</th><th className="num">18–24 vs. 60+</th></tr></thead>
                <tbody>
                  {data.entidades.map((e) => (
                    <tr key={e.entidad}><td>{e.entidad}</td><td className="num">{fmt.share(e.observada)}</td>
                      <td className="num">{fmt.share(e.esperada_por_edad)}</td><td className="num">{fmt.pp(e.diferencia_no_explicada_pp)}</td>
                      <td className="num">{fmt.pp(e.brecha_jovenes_mayores_pp)}</td></tr>
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
