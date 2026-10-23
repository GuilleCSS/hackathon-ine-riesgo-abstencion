import { fmt, type Resumen } from "../lib/api";

interface Props {
  resumen: Resumen;
  onEntidad: (edo: number) => void;
  onMunicipio: (edo: number, mun: number) => void;
}

export default function Tablas({ resumen, onEntidad, onMunicipio }: Props) {
  return (
    <div className="tablas">
      <section className="card">
        <h2>Resumen por entidad</h2>
        {resumen.entidades.length === 0 ? <p className="muted">Sin secciones con estos filtros.</p> : (
          <table className="tabla">
            <thead>
              <tr>
                <th>Entidad</th><th className="num">Secciones</th><th className="num">ALTO</th><th className="num">Top10</th>
                <th className="num">Abst. media</th><th className="num">% ALTO</th><th className="num">Cobertura</th>
              </tr>
            </thead>
            <tbody>
              {resumen.entidades.map((r) => (
                <tr key={r.edo} onClick={() => onEntidad(r.edo)} title="Ver en el mapa">
                  <td>{r.nombre}</td>
                  <td className="num">{fmt.n(r.secciones)}</td>
                  <td className="num">{fmt.n(r.alto)}</td>
                  <td className="num">{fmt.n(r.top10)}</td>
                  <td className="num">{fmt.pct(r.abstencion_media)}</td>
                  <td className="num">{fmt.share(r.share_alto)}</td>
                  <td className="num">{fmt.share(r.cobertura)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
      <section className="card">
        <h2>Municipios con mayor concentración</h2>
        {resumen.municipios.length === 0 ? <p className="muted">Sin secciones con estos filtros.</p> : (
          <table className="tabla">
            <thead>
              <tr>
                <th>Municipio</th><th>Entidad</th><th className="num">Secciones</th><th className="num">ALTO</th>
                <th className="num">Top10</th><th className="num">Abst. media</th><th className="num">% ALTO</th>
              </tr>
            </thead>
            <tbody>
              {resumen.municipios.map((r) => (
                <tr key={`${r.edo}-${r.mun}`} onClick={() => onMunicipio(r.edo, r.mun)} title="Ver en el mapa">
                  <td>{r.nombre}</td>
                  <td>{r.entidad}</td>
                  <td className="num">{fmt.n(r.secciones)}</td>
                  <td className="num">{fmt.n(r.alto)}</td>
                  <td className="num">{fmt.n(r.top10)}</td>
                  <td className="num">{fmt.pct(r.abstencion_media)}</td>
                  <td className="num">{fmt.share(r.share_alto)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="muted">Primeros 30, ordenados por secciones Top10 y luego ALTO.</p>
      </section>
    </div>
  );
}
