import { useEffect, useState } from "react";
import Ficha from "./Ficha";
import MapaSecciones, { ambito, type Propiedades } from "./MapaSecciones";
import Tablas from "./Tablas";
import type { ExpressionSpecification, FilterSpecification } from "maplibre-gl";
import {
  CORTO, NIVELES, SENSIBILIDADES, fmt, get,
  type Config, type Entidad, type Escenario, type Filtros, type Municipio, type Nivel, type Resumen,
} from "../lib/api";
import { nivelColor, token } from "../lib/tokens";

const ESCENARIOS: Escenario[] = ["S0", "S1", "S2", "S3"];
const sufijo = (e: Escenario) => (e === "S0" ? "" : `_${e.toLowerCase()}`);

/** Los mismos filtros que /api/resumen, como expresiones de MapLibre sobre los atributos de la tesela. */
function capas(f: Filtros) {
  const nivel = `nivel${sufijo(f.escenario)}`;
  const top = `top10${sufijo(f.escenario)}`;
  const riesgo: ExpressionSpecification = [
    "all", ["==", ["get", "capa"], "semaforo"], ...ambito(f.edo, f.mun),
    ["in", ["get", nivel], ["literal", f.niveles]],
    ...(f.top10 ? [["==", ["get", top], true] as ExpressionSpecification] : []),
    ...(f.sensibilidad ? [["==", ["get", "sensibilidad"], f.sensibilidad] as ExpressionSpecification] : []),
  ];
  return {
    datos: {
      filtro: riesgo as FilterSpecification,
      color: ["match", ["get", nivel], "BAJO", token("riesgo-bajo"), "MEDIO", token("riesgo-medio"),
        "ALTO", token("riesgo-alto"), token("sin-estimacion")] as ExpressionSpecification,
    },
    extra: {
      filtro: ["all", ["==", ["get", "capa"], "ns_alto"], ...ambito(f.edo, f.mun)] as FilterSpecification,
      color: token("ns-alto"),
      visible: f.verNs,
    },
    contorno: ["all", riesgo, ["==", ["get", top], true]] as FilterSpecification,
  };
}

function tooltipRiesgo(p: Propiedades, f: Filtros): [string, string][] {
  const filas: [string, string][] = [["Sección", p.clave]];
  if (p.capa === "semaforo") {
    filas.push(["Riesgo", `${p[`nivel${sufijo(f.escenario)}`]}${p[`top10${sufijo(f.escenario)}`] ? " · Top10" : ""}`],
      ["Abstención estimada (base)", fmt.pct(p.pred)]);
  } else if (p.capa === "ns_alto") {
    filas.push(["NS alto", "fuera del semáforo"], ["Abstención indicativa", fmt.pct(p.pred)]);
  } else {
    filas.push(["Sin estimación", "fuera del universo comparable"]);
  }
  return filas;
}

// Los filtros viven en la URL para poder compartir una vista: ?escenario=S1&edo=25&nivel=ALTO
function leerUrl(): Filtros {
  const q = new URLSearchParams(location.search);
  const entero = (k: string) => (/^\d+$/.test(q.get(k) ?? "") ? Number(q.get(k)) : null);
  const niveles = q.getAll("nivel").filter((n): n is Nivel => NIVELES.includes(n as Nivel));
  const escenario = q.get("escenario") as Escenario;
  const edo = entero("edo");
  return {
    escenario: ESCENARIOS.includes(escenario) ? escenario : "S0",
    edo,
    mun: edo === null ? null : entero("mun"),
    niveles: niveles.length ? niveles : NIVELES,
    top10: q.get("top10") === "1",
    sensibilidad: q.get("sensibilidad") in SENSIBILIDADES ? q.get("sensibilidad") : null,
    verNs: q.get("ns") !== "0",
  };
}

function escribirUrl(f: Filtros) {
  const q = new URLSearchParams();
  if (f.escenario !== "S0") q.set("escenario", f.escenario);
  if (f.edo !== null) q.set("edo", String(f.edo));
  if (f.mun !== null) q.set("mun", String(f.mun));
  if (f.niveles.length < NIVELES.length) f.niveles.forEach((n) => q.append("nivel", n));
  if (f.top10) q.set("top10", "1");
  if (f.sensibilidad) q.set("sensibilidad", f.sensibilidad);
  if (!f.verNs) q.set("ns", "0");
  history.replaceState(null, "", q.size ? `?${q}` : location.pathname);
}

const ignorarAbort = (setError: (m: string) => void) => (e: Error) => e.name !== "AbortError" && setError(e.message);

export default function MapaRiesgo() {
  const [filtros, setFiltros] = useState<Filtros>(leerUrl);
  const [config, setConfig] = useState<Config | null>(null);
  const [entidades, setEntidades] = useState<Entidad[]>([]);
  const [municipios, setMunicipios] = useState<Municipio[]>([]);
  const [resumen, setResumen] = useState<Resumen | null>(null);
  const [seleccion, setSeleccion] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const cambiar = (cambio: Partial<Filtros>) => setFiltros((f) => ({ ...f, ...cambio }));

  useEffect(() => {
    Promise.all([get<Config>("/api/config"), get<Entidad[]>("/api/entidades")])
      .then(([c, e]) => { setConfig(c); setEntidades(e); })
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (filtros.edo === null) return setMunicipios([]);
    const ctl = new AbortController();
    get<Municipio[]>(`/api/entidades/${filtros.edo}/municipios`, {}, ctl.signal).then(setMunicipios).catch(ignorarAbort(setError));
    return () => ctl.abort();
  }, [filtros.edo]);

  useEffect(() => {
    escribirUrl(filtros);
    const ctl = new AbortController();
    const { escenario, edo, mun, niveles, top10, sensibilidad } = filtros;
    get<Resumen>("/api/resumen", { escenario, edo, mun, nivel: niveles, top10, sensibilidad }, ctl.signal)
      .then((r) => { setResumen(r); setError(null); })
      .catch(ignorarAbort(setError));
    return () => ctl.abort();
  }, [filtros]);

  const alternarNivel = (n: Nivel) => {
    const niveles = filtros.niveles.includes(n) ? filtros.niveles.filter((x) => x !== n) : [...filtros.niveles, n];
    // Al menos un nivel: sin ninguno el mapa quedaría vacío sin explicación.
    if (niveles.length) cambiar({ niveles: NIVELES.filter((x) => niveles.includes(x)) });
  };
  const escenario = config?.escenarios.find((e) => e.id === filtros.escenario);
  const k = resumen?.kpis;

  return (
    <>
      <div className="app">
        <aside className="panel" aria-label="Filtros e indicadores">
          <section>
            <h2>Filtros</h2>
            <div className="field">
              <label htmlFor="f-escenario">Escenario</label>
              <select id="f-escenario" value={filtros.escenario} onChange={(e) => cambiar({ escenario: e.target.value as Escenario })}>
                {ESCENARIOS.map((id) => <option key={id} value={id}>{CORTO[id]}</option>)}
              </select>
            </div>
            <div className="field">
              <label htmlFor="f-edo">Entidad</label>
              <select id="f-edo" value={filtros.edo ?? ""}
                onChange={(e) => cambiar({ edo: e.target.value ? Number(e.target.value) : null, mun: null })}>
                <option value="">Nacional</option>
                {entidades.map((x) => <option key={x.edo} value={x.edo}>{x.nombre}</option>)}
              </select>
            </div>
            <div className="field">
              <label htmlFor="f-mun">Municipio</label>
              <select id="f-mun" value={filtros.mun ?? ""} disabled={filtros.edo === null}
                onChange={(e) => cambiar({ mun: e.target.value ? Number(e.target.value) : null })}>
                <option value="">{filtros.edo === null ? "Elige una entidad" : "Todos"}</option>
                {municipios.map((x) => <option key={x.mun} value={x.mun}>{x.nombre}</option>)}
              </select>
            </div>
            <fieldset>
              <legend>Nivel de riesgo</legend>
              <div className="chips">
                {NIVELES.map((n) => (
                  <label className="chip" key={n}>
                    <input type="checkbox" checked={filtros.niveles.includes(n)} onChange={() => alternarNivel(n)} />
                    <span className="swatch" style={{ background: nivelColor(n) }} />{n}
                  </label>
                ))}
              </div>
            </fieldset>
            <label className="check">
              <input type="checkbox" checked={filtros.top10} onChange={(e) => cambiar({ top10: e.target.checked })} />
              Sólo Top10 prioritario
            </label>
            <div className="field">
              <label htmlFor="f-sens">Persistencia / sensibilidad</label>
              <select id="f-sens" value={filtros.sensibilidad ?? ""} onChange={(e) => cambiar({ sensibilidad: e.target.value || null })}>
                <option value="">Todas</option>
                {Object.entries(SENSIBILIDADES).map(([v, t]) => <option key={v} value={v}>{t}</option>)}
              </select>
            </div>
            <label className="check">
              <input type="checkbox" checked={filtros.verNs} onChange={(e) => cambiar({ verNs: e.target.checked })} />
              <span className="swatch" style={{ background: "var(--ns-alto)" }} />
              Mostrar secciones con NS alto
            </label>
          </section>

          <section>
            <h2>Indicadores</h2>
            <div className="kpis" aria-live="polite">
              <div className="kpi"><span>Secciones mostradas</span><strong className="num">{k ? fmt.n(k.secciones) : "…"}</strong></div>
              <div className="kpi"><span>Abstención media</span><strong className="num">{k ? fmt.pct(k.abstencion_media) : "…"}</strong></div>
              <div className="kpi"><span>Riesgo ALTO</span><strong className="num">{k ? fmt.n(k.alto) : "…"}</strong></div>
              <div className="kpi"><span>Top10 prioritario</span><strong className="num">{k ? fmt.n(k.top10) : "…"}</strong></div>
              <div className="kpi wide">
                <span>Cobertura predictiva</span>
                <strong className="num">{k ? fmt.share(k.cobertura.con_estimacion / k.cobertura.cartografia) : "…"}</strong>
                {k && <small className="num">
                  {fmt.n(k.cobertura.con_estimacion)} de {fmt.n(k.cobertura.cartografia)} secciones
                  {k.cobertura.ns_alto ? ` · ${fmt.n(k.cobertura.ns_alto)} más con NS alto` : ""}
                </small>}
              </div>
            </div>
          </section>

          {escenario && (
            <div className={filtros.escenario === "S0" ? "note" : "note warn"}>
              {filtros.escenario === "S0"
                ? "Escenario base: la estimación territorial 2027. No representa una intervención."
                : `${escenario.descripcion} Es un supuesto de sensibilidad, no un efecto causal; los umbrales del semáforo se mantienen congelados.`}
            </div>
          )}
          {error && <div className="error" role="alert">No se pudieron cargar los datos: {error}</div>}
        </aside>

        <div className="map-wrap">
          <MapaSecciones {...capas(filtros)} tooltip={(p) => tooltipRiesgo(p, filtros)}
            bbox={resumen?.bbox ?? null} seleccion={seleccion} onSelect={setSeleccion} />
          {/* Cerrada al inicio en pantallas angostas, donde taparía medio mapa. */}
          <details className="legend" open={!matchMedia("(max-width: 60em)").matches}>
            <summary>Leyenda</summary>
            {NIVELES.map((n) => <div key={n}><span className="swatch" style={{ background: nivelColor(n) }} />{n}</div>)}
            <div><span className="swatch outline" />Top10 prioritario</div>
            {filtros.verNs && <div><span className="swatch" style={{ background: "var(--ns-alto)" }} />NS alto (fuera del semáforo)</div>}
            <div><span className="swatch" style={{ background: "var(--sin-estimacion)" }} />Sin estimación o fuera de filtros</div>
          </details>
          {seleccion && <Ficha clave={seleccion} onClose={() => setSeleccion(null)} />}
        </div>
      </div>

      {resumen && (
        <div className="debajo">
          <Tablas resumen={resumen}
            onEntidad={(edo) => cambiar({ edo, mun: null })}
            onMunicipio={(edo, mun) => cambiar({ edo, mun })} />
        </div>
      )}
    </>
  );
}
