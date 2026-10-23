import { useApi, type Entidad } from "../lib/api";

/** Opciones excluyentes como botones (tipo de elección, variable, año…). */
export function Segmentado<T extends string | number>({ nombre, etiqueta, opciones, valor, onCambio }: {
  nombre: string;
  etiqueta: string;
  opciones: [T, string][];
  valor: T;
  onCambio: (v: T) => void;
}) {
  return (
    <fieldset>
      <legend>{etiqueta}</legend>
      <div className="seg">
        {opciones.map(([v, texto]) => (
          <label key={String(v)}>
            <input type="radio" name={nombre} checked={v === valor} onChange={() => onCambio(v)} />
            {texto}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

export function SelectEntidad({ valor, onCambio }: { valor: number | null; onCambio: (edo: number | null) => void }) {
  const { data } = useApi<Entidad[]>("/api/entidades");
  return (
    <div className="field">
      <label htmlFor="f-edo">Entidad</label>
      <select id="f-edo" value={valor ?? ""} onChange={(e) => onCambio(e.target.value ? Number(e.target.value) : null)}>
        <option value="">Nacional</option>
        {data?.map((x) => <option key={x.edo} value={x.edo}>{x.nombre}</option>)}
      </select>
    </div>
  );
}

export function Kpi({ etiqueta, valor, nota, ancho }: { etiqueta: string; valor: string; nota?: string; ancho?: boolean }) {
  return (
    <div className={ancho ? "kpi wide" : "kpi"}>
      <span>{etiqueta}</span>
      <strong className="num">{valor}</strong>
      {nota && <small className="num">{nota}</small>}
    </div>
  );
}

export function Leyenda({ items }: { items: [string, string][] }) {
  // Cerrada al inicio en pantallas angostas, donde taparía medio mapa.
  return (
    <details className="legend" open={!matchMedia("(max-width: 60em)").matches}>
      <summary>Leyenda</summary>
      {items.map(([color, texto]) => <div key={texto}><span className="swatch" style={{ background: color }} />{texto}</div>)}
    </details>
  );
}

