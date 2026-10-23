import { useEffect, useState } from "react";
import { CORTO, fmt, get, SENSIBILIDADES, type Seccion } from "../lib/api";
import { nivelColor } from "../lib/tokens";

const TIPOS: Record<string, string> = { U: "urbana", M: "mixta", R: "rural" };
const COMPARACION: Record<string, string> = {
  coincide: "mismo nivel que el oficial", oscar_mas_alto: "más alto que el oficial",
  oscar_mas_bajo: "más bajo que el oficial", solo_oscar: "sólo está en el de Oscar",
};

export default function Ficha({ clave, onClose }: { clave: string; onClose: () => void }) {
  const [s, setS] = useState<Seccion | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const ctl = new AbortController();
    setS(null);
    setError(null);
    get<Seccion>(`/api/secciones/${clave}`, {}, ctl.signal)
      .then(setS)
      .catch((e) => e.name !== "AbortError" && setError(e.message));
    return () => ctl.abort();
  }, [clave]);

  return (
    <aside className="ficha" aria-label={`Ficha de la sección ${clave}`}>
      <header>
        <div>
          <h3>Sección {s?.seccion ?? clave}</h3>
          <div className="muted">
            {s ? `${s.municipio.nombre ?? "Municipio sin nombre"}, ${s.entidad.nombre ?? "—"}` : "Cargando…"}
            {s?.tipo ? ` · ${TIPOS[s.tipo] ?? s.tipo}` : ""}
          </div>
        </div>
        <button type="button" onClick={onClose} aria-label="Cerrar ficha">×</button>
      </header>
      {error && <div className="error" role="alert">{error}</div>}
      {s && <Contenido s={s} />}
    </aside>
  );
}

function Contenido({ s }: { s: Seccion }) {
  const e = s.estimacion;
  const sens = s.sensibilidad;
  const maxAbst = Math.max(...s.historia.map((h) => h.abstencion ?? 0), 1);
  return (
    <>
      <span className="badge">
        <span className="swatch" style={{ background: s.capa === "ns_alto" ? "var(--ns-alto)" : nivelColor(e.nivel) }} />
        {s.capa === "semaforo" ? `Riesgo ${e.nivel}${e.top10 ? " · Top10 prioritario" : ""}`
          : s.capa === "ns_alto" ? "NS alto: fuera del semáforo" : "Sin estimación"}
      </span>

      {e.pred !== null && (
        <div>
          <div className="muted">Abstención estimada 2027{s.capa === "ns_alto" ? " (indicativa)" : ""}</div>
          <div className="big num">{fmt.pct(e.pred)}</div>
          <div className="muted num">
            Intervalo empírico 90%: {fmt.pct(e.inferior_90)} – {fmt.pct(e.superior_90)}
            {e.percentil !== null && ` · percentil ${e.percentil.toFixed(0)}`}
          </div>
        </div>
      )}

      {s.capa === "ns_alto" && (
        <div className="note warn">
          Más de 10% de registros sin información (NS): {fmt.pct(s.ns["2021"])} en 2021 y {fmt.pct(s.ns["2024"])} en 2024.
          Con los umbrales del semáforo su nivel sería {e.nivel_indicativo}, pero la estimación es poco confiable.
        </div>
      )}
      {s.capa === "sin_estimacion" && (
        <div className="note">
          No tiene historia comparable en 2021 y 2024 (sección nueva, sin datos o con cambios de municipio o tipo),
          así que no recibe estimación.
        </div>
      )}

      {sens.clase && (
        <div>
          <b>Persistencia:</b> {SENSIBILIDADES[sens.clase] ?? sens.clase}
          {sens.clase !== "NO_ALTO" && sens.para_salir_de_alto_pp !== null &&
            <span className="muted"> · {sens.para_salir_de_alto_pp.toFixed(1)} pp sobre el umbral</span>}
        </div>
      )}

      {s.escenarios.length > 0 && (
        <table className="mini">
          <caption className="muted">Escenarios (umbrales congelados)</caption>
          <thead><tr><th>Escenario</th><th>Nivel</th><th className="num">Abstención</th></tr></thead>
          <tbody>
            {s.escenarios.map((x) => (
              <tr key={x.id}>
                <td>{CORTO[x.id]}</td>
                <td><span className="swatch" style={{ background: nivelColor(x.nivel) }} /> {x.nivel}{x.top10 ? " · Top10" : ""}</td>
                <td className="num">{fmt.pct(x.pred)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <table className="mini">
        <caption className="muted">Abstención observada</caption>
        <thead><tr><th>Año</th><th>Tipo</th><th>Abstención</th><th className="num">NS</th></tr></thead>
        <tbody>
          {s.historia.map((h) => (
            <tr key={h.anio}>
              <td className="num">{h.anio}</td>
              <td>{h.tipo}</td>
              <td>
                {h.abstencion === null ? "—" : (
                  <div className="bar-cell">
                    <div className="bar" style={{ width: `${(h.abstencion / maxAbst) * 70}%` }} />
                    <span className="num">{fmt.pct(h.abstencion)}</span>
                  </div>
                )}
              </td>
              <td className="num">{fmt.pct(h.ns)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="muted">
        {s.grupo.nombre && <div>Grupo histórico: {s.grupo.nombre}</div>}
        {s.oscar.nivel && <div>Semáforo alternativo (Oscar): {s.oscar.nivel}, {COMPARACION[s.oscar.comparacion ?? ""] ?? ""}</div>}
        <div>Clave {s.clave}</div>
      </div>
    </>
  );
}
