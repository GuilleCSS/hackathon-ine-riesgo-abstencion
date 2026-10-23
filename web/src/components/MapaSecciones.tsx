import { useEffect, useRef, useState } from "react";
import {
  Map as MapLibre, NavigationControl, Popup, addProtocol, setWorkerUrl,
  type ExpressionSpecification, type FilterSpecification,
} from "maplibre-gl";
// MapLibre 6 busca su worker junto a su propio módulo; al empaquetar hay que emitirlo y darle la URL.
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import { Protocol } from "pmtiles";
import "maplibre-gl/dist/maplibre-gl.css";
import { get } from "../lib/api";
import { rem, token } from "../lib/tokens";

setWorkerUrl(workerUrl);
addProtocol("pmtiles", new Protocol().tile);

const SL = "secciones";
const HOVER_LAYERS = ["extra", "datos", "base"];

/** Secciones a colorear: filtro sobre los atributos de la tesela y color (expresión de MapLibre). */
export interface Capa {
  filtro: FilterSpecification;
  color: ExpressionSpecification | string;
}
export type Propiedades = Record<string, any>;

/** Filtro de entidad/municipio sobre los atributos `edo` y `mun` de la tesela. */
export function ambito(edo: number | null, mun: number | null = null): ExpressionSpecification[] {
  const out: ExpressionSpecification[] = [];
  if (edo !== null) out.push(["==", ["get", "edo"], edo]);
  if (mun !== null) out.push(["==", ["get", "mun"], mun]);
  return out;
}

interface Props {
  datos: Capa;
  /** Segunda capa encima de la principal (p. ej. NS alto en el mapa de riesgo). */
  extra?: Capa & { visible: boolean };
  /** Contorno oscuro (p. ej. Top10). */
  contorno?: FilterSpecification | null;
  tooltip: (p: Propiedades) => [string, string][];
  bbox: [number, number, number, number] | null;
  seleccion: string | null;
  onSelect: (clave: string | null) => void;
}

function contenidoTooltip(filas: [string, string][]) {
  const div = document.createElement("div");
  div.className = "tooltip";
  for (const [k, v] of filas) {
    const row = div.appendChild(document.createElement("div"));
    row.appendChild(document.createElement("b")).textContent = `${k}: `;
    row.append(v);
  }
  const pie = div.appendChild(document.createElement("div"));
  pie.className = "muted";
  pie.textContent = "Clic para ver la ficha";
  return div;
}

const NADA: FilterSpecification = ["==", ["get", "clave"], ""];
// La versión va en la URL de las teselas: si la etapa 21 las regenera, el navegador no reusa las de su caché.
const version = get<{ teselas: number }>("/api/salud").then((s) => s.teselas).catch(() => 0);

export default function MapaSecciones({ datos, extra, contorno, tooltip, bbox, seleccion, onSelect }: Props) {
  const contenedor = useRef<HTMLDivElement>(null);
  const mapa = useRef<MapLibre | null>(null);
  const [listo, setListo] = useState(false);
  // El mapa se crea una vez; sus manejadores leen siempre los props vigentes.
  const vigentes = useRef({ tooltip, onSelect });
  vigentes.current = { tooltip, onSelect };

  useEffect(() => {
    let m: MapLibre | undefined;
    let popup: Popup | undefined;
    let cancelado = false;
    version.then((v) => {
      if (cancelado) return;
      ({ m, popup } = crear(v));
    });
    return () => { cancelado = true; popup?.remove(); m?.remove(); };
  }, []);

  function crear(v: number) {
    const capa = (id: string, color: string) =>
      ({ id, type: "fill", source: "s", "source-layer": SL, filter: NADA, paint: { "fill-color": color } }) as const;
    const m = new MapLibre({
      container: contenedor.current!,
      center: [-102, 23.6], zoom: 4.2, minZoom: 3, maxZoom: 16,
      attributionControl: { compact: true },
      style: {
        version: 8,
        sources: { s: { type: "vector", url: `pmtiles://${location.origin}/tiles/secciones.pmtiles?v=${v}` } },
        layers: [
          { id: "fondo", type: "background", paint: { "background-color": token("map-bg") } },
          { id: "base", type: "fill", source: "s", "source-layer": SL, paint: { "fill-color": token("sin-estimacion") } },
          capa("datos", token("sin-estimacion")),
          capa("extra", token("ns-alto")),
          { id: "borde-seccion", type: "line", source: "s", "source-layer": SL, minzoom: 9,
            paint: { "line-color": token("map-borde"), "line-width": ["interpolate", ["linear"], ["zoom"], 9, 0.2, 14, 1] } },
          { id: "borde-municipio", type: "line", source: "s", "source-layer": "municipios", minzoom: 6,
            paint: { "line-color": token("ink-2"), "line-opacity": 0.45, "line-width": ["interpolate", ["linear"], ["zoom"], 6, 0.3, 12, 1.2] } },
          { id: "borde-estado", type: "line", source: "s", "source-layer": "estados",
            paint: { "line-color": token("ink"), "line-opacity": 0.55, "line-width": ["interpolate", ["linear"], ["zoom"], 3, 0.5, 10, 2] } },
          { id: "contorno", type: "line", source: "s", "source-layer": SL, minzoom: 7, filter: NADA,
            paint: { "line-color": token("top10"), "line-width": ["interpolate", ["linear"], ["zoom"], 7, 0.8, 13, 2] } },
          { id: "seleccion", type: "line", source: "s", "source-layer": SL, filter: NADA,
            paint: { "line-color": token("seleccion"), "line-width": 3 } },
        ],
      },
    });
    m.addControl(new NavigationControl({ showCompass: false }), "top-left");
    const popup = new Popup({ closeButton: false, closeOnClick: false, offset: rem(0.625), maxWidth: "20rem" });
    const bajo = (point: Parameters<MapLibre["queryRenderedFeatures"]>[0]) =>
      m.queryRenderedFeatures(point, { layers: HOVER_LAYERS })[0];

    m.on("mousemove", (e) => {
      const f = bajo(e.point);
      m.getCanvas().style.cursor = f ? "pointer" : "";
      if (f) popup.setLngLat(e.lngLat).setDOMContent(contenidoTooltip(vigentes.current.tooltip(f.properties))).addTo(m);
      else popup.remove();
    });
    m.on("mouseout", () => popup.remove());
    m.on("click", (e) => vigentes.current.onSelect(bajo(e.point)?.properties.clave ?? null));
    m.on("load", () => setListo(true));
    mapa.current = m;
    return { m, popup };
  }

  // Las expresiones son objetos nuevos en cada render: se comparan por contenido.
  const estilo = JSON.stringify([datos, extra, contorno]);
  useEffect(() => {
    const m = mapa.current;
    if (!m || !listo) return;
    m.setFilter("datos", datos.filtro);
    m.setPaintProperty("datos", "fill-color", datos.color);
    m.setFilter("extra", extra ? extra.filtro : NADA);
    if (extra) m.setPaintProperty("extra", "fill-color", extra.color);
    m.setLayoutProperty("extra", "visibility", extra?.visible ? "visible" : "none");
    m.setFilter("contorno", contorno ?? NADA);
  }, [listo, estilo]);

  // Sólo cambia cuando cambia el ámbito (entidad o municipio), no con los demás filtros.
  const caja = bbox?.join();
  useEffect(() => {
    if (listo && bbox) mapa.current!.fitBounds(bbox, { padding: rem(3), duration: 700, maxZoom: 13 });
  }, [listo, caja]);

  useEffect(() => {
    if (listo) mapa.current!.setFilter("seleccion", ["==", ["get", "clave"], seleccion ?? ""]);
  }, [listo, seleccion]);

  return <div ref={contenedor} className="map" role="region" aria-label="Mapa de secciones electorales" />;
}
