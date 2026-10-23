import { useEffect, useRef, useState } from "react";
import {
  Map as MapLibre, NavigationControl, Popup, addProtocol, setWorkerUrl,
  type ExpressionSpecification, type FilterSpecification, type MapGeoJSONFeature,
} from "maplibre-gl";
// MapLibre 6 busca su worker junto a su propio módulo; al empaquetar hay que emitirlo y darle la URL.
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import { Protocol } from "pmtiles";
import "maplibre-gl/dist/maplibre-gl.css";
import { fmt, type Escenario, type Filtros } from "../lib/api";
import { rem, token } from "../lib/tokens";

setWorkerUrl(workerUrl);
addProtocol("pmtiles", new Protocol().tile);

const SL = "secciones";
const HOVER_LAYERS = ["riesgo", "ns", "base"];
const sufijo = (e: Escenario) => (e === "S0" ? "" : `_${e.toLowerCase()}`);

/** Los mismos filtros que /api/resumen, como expresiones de MapLibre sobre los atributos de la tesela. */
function expresiones(f: Filtros) {
  const nivel = `nivel${sufijo(f.escenario)}`;
  const top = `top10${sufijo(f.escenario)}`;
  const ambito: ExpressionSpecification[] = [];
  if (f.edo !== null) ambito.push(["==", ["get", "edo"], f.edo]);
  if (f.mun !== null) ambito.push(["==", ["get", "mun"], f.mun]);
  const riesgo: ExpressionSpecification = [
    "all", ["==", ["get", "capa"], "semaforo"], ...ambito,
    ["in", ["get", nivel], ["literal", f.niveles]],
    ...(f.top10 ? [["==", ["get", top], true] as ExpressionSpecification] : []),
    ...(f.sensibilidad ? [["==", ["get", "sensibilidad"], f.sensibilidad] as ExpressionSpecification] : []),
  ];
  return {
    nivel,
    riesgo: riesgo as FilterSpecification,
    top10: ["all", riesgo, ["==", ["get", top], true]] as FilterSpecification,
    ns: ["all", ["==", ["get", "capa"], "ns_alto"], ...ambito] as FilterSpecification,
  };
}

function tooltip(p: MapGeoJSONFeature["properties"], f: Filtros) {
  const nivel = p[`nivel${sufijo(f.escenario)}`];
  const filas: [string, string][] = [["Sección", p.clave]];
  if (p.capa === "semaforo") {
    filas.push(["Riesgo", `${nivel}${p[`top10${sufijo(f.escenario)}`] ? " · Top10" : ""}`],
      ["Abstención estimada (base)", fmt.pct(p.pred)]);
  } else if (p.capa === "ns_alto") {
    filas.push(["NS alto", "fuera del semáforo"], ["Abstención indicativa", fmt.pct(p.pred)]);
  } else {
    filas.push(["Sin estimación", "fuera del universo comparable"]);
  }
  const div = document.createElement("div");
  div.className = "tooltip";
  for (const [k, v] of filas) {
    const row = div.appendChild(document.createElement("div"));
    row.appendChild(document.createElement("b")).textContent = `${k}: `;
    row.append(v);
  }
  div.appendChild(document.createElement("div")).className = "muted";
  (div.lastChild as HTMLElement).textContent = "Clic para ver la ficha";
  return div;
}

interface Props {
  filtros: Filtros;
  bbox: [number, number, number, number] | null;
  seleccion: string | null;
  onSelect: (clave: string | null) => void;
}

export default function Mapa({ filtros, bbox, seleccion, onSelect }: Props) {
  const contenedor = useRef<HTMLDivElement>(null);
  const mapa = useRef<MapLibre | null>(null);
  const [listo, setListo] = useState(false);
  // El mapa se crea una vez; sus manejadores leen siempre los props vigentes.
  const vigentes = useRef({ filtros, onSelect });
  vigentes.current = { filtros, onSelect };

  useEffect(() => {
    const m = new MapLibre({
      container: contenedor.current!,
      center: [-102, 23.6], zoom: 4.2, minZoom: 3, maxZoom: 16,
      attributionControl: { compact: true },
      style: {
        version: 8,
        sources: { s: { type: "vector", url: `pmtiles://${location.origin}/tiles/secciones.pmtiles` } },
        layers: [
          { id: "fondo", type: "background", paint: { "background-color": token("map-bg") } },
          { id: "base", type: "fill", source: "s", "source-layer": SL, paint: { "fill-color": token("sin-estimacion") } },
          { id: "riesgo", type: "fill", source: "s", "source-layer": SL, paint: { "fill-color": token("sin-estimacion") } },
          { id: "ns", type: "fill", source: "s", "source-layer": SL, paint: { "fill-color": token("ns-alto") } },
          { id: "borde-seccion", type: "line", source: "s", "source-layer": SL, minzoom: 9,
            paint: { "line-color": token("map-borde"), "line-width": ["interpolate", ["linear"], ["zoom"], 9, 0.2, 14, 1] } },
          { id: "borde-municipio", type: "line", source: "s", "source-layer": "municipios", minzoom: 6,
            paint: { "line-color": token("ink-2"), "line-opacity": 0.45, "line-width": ["interpolate", ["linear"], ["zoom"], 6, 0.3, 12, 1.2] } },
          { id: "borde-estado", type: "line", source: "s", "source-layer": "estados",
            paint: { "line-color": token("ink"), "line-opacity": 0.55, "line-width": ["interpolate", ["linear"], ["zoom"], 3, 0.5, 10, 2] } },
          { id: "top10", type: "line", source: "s", "source-layer": SL, minzoom: 7,
            paint: { "line-color": token("top10"), "line-width": ["interpolate", ["linear"], ["zoom"], 7, 0.8, 13, 2] } },
          { id: "seleccion", type: "line", source: "s", "source-layer": SL, filter: ["==", ["get", "clave"], ""],
            paint: { "line-color": token("seleccion"), "line-width": 3 } },
        ],
      },
    });
    m.addControl(new NavigationControl({ showCompass: false }), "top-left");
    const popup = new Popup({ closeButton: false, closeOnClick: false, offset: rem(0.625), maxWidth: "18rem" });
    const bajo = (point: Parameters<MapLibre["queryRenderedFeatures"]>[0]) =>
      m.queryRenderedFeatures(point, { layers: HOVER_LAYERS })[0];

    m.on("mousemove", (e) => {
      const f = bajo(e.point);
      m.getCanvas().style.cursor = f ? "pointer" : "";
      if (f) popup.setLngLat(e.lngLat).setDOMContent(tooltip(f.properties, vigentes.current.filtros)).addTo(m);
      else popup.remove();
    });
    m.on("mouseout", () => popup.remove());
    m.on("click", (e) => vigentes.current.onSelect(bajo(e.point)?.properties.clave ?? null));
    m.on("load", () => setListo(true));
    mapa.current = m;
    return () => { popup.remove(); m.remove(); };
  }, []);

  useEffect(() => {
    const m = mapa.current;
    if (!m || !listo) return;
    const e = expresiones(filtros);
    m.setFilter("riesgo", e.riesgo);
    m.setPaintProperty("riesgo", "fill-color", ["match", ["get", e.nivel],
      "BAJO", token("riesgo-bajo"), "MEDIO", token("riesgo-medio"), "ALTO", token("riesgo-alto"), token("sin-estimacion")]);
    m.setFilter("top10", e.top10);
    m.setFilter("ns", e.ns);
    m.setLayoutProperty("ns", "visibility", filtros.verNs ? "visible" : "none");
  }, [listo, filtros]);

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
