// Tipos y llamadas a la API (api/main.py). Todo es GET al mismo origen.
import { useEffect, useState } from "react";

export type Escenario = "S0" | "S1" | "S2" | "S3";
export type Nivel = "BAJO" | "MEDIO" | "ALTO";
export const NIVELES: Nivel[] = ["BAJO", "MEDIO", "ALTO"];
export const CORTO: Record<Escenario, string> = {
  S0: "Base (sin intervención)", S1: "Top10 −2 pp", S2: "ALTO −2 pp", S3: "ALTO −5 pp",
};
export const SENSIBILIDADES: Record<string, string> = {
  NO_ALTO: "No está en ALTO",
  ALTO_SENSIBLE_2PP: "ALTO, a 2 pp o menos de salir",
  ALTO_SENSIBLE_5PP: "ALTO, a más de 2 y hasta 5 pp",
  ALTO_PERSISTENTE_MAS_5PP: "ALTO persistente (más de 5 pp)",
};

export interface Filtros {
  escenario: Escenario;
  edo: number | null;
  mun: number | null;
  niveles: Nivel[];
  top10: boolean;
  sensibilidad: string | null;
  verNs: boolean;
}

export interface Config {
  escenarios: { id: Escenario; etiqueta: string; delta_pp: number; descripcion: string }[];
  umbrales: { q50: number; q80: number; q90: number };
}
export interface Entidad { edo: number; nombre: string; secciones: number }
export interface Municipio { mun: number; nombre: string }
interface Metricas { secciones: number; alto: number; top10: number; abstencion_media: number | null }
export interface FilaEntidad extends Metricas { edo: number; nombre: string; share_alto: number; share_top10: number; cobertura: number }
export interface FilaMunicipio extends Metricas { edo: number; entidad: string; mun: number; nombre: string; share_alto: number }
export interface Resumen {
  kpis: Metricas & { cobertura: { cartografia: number; con_estimacion: number; ns_alto: number } };
  bbox: [number, number, number, number];
  entidades: FilaEntidad[];
  municipios: FilaMunicipio[];
}
export interface Seccion {
  clave: string;
  entidad: { edo: number; nombre: string | null };
  municipio: { mun: number; nombre: string | null };
  seccion: number;
  tipo: string | null;
  capa: "semaforo" | "ns_alto" | "sin_estimacion";
  estimacion: {
    pred: number | null; inferior_90: number | null; superior_90: number | null; percentil: number | null;
    nivel: Nivel | null; top10: boolean | null; nivel_indicativo: Nivel | null;
  };
  ns: { "2021": number | null; "2024": number | null };
  sensibilidad: { clase: string | null; para_salir_de_alto_pp: number | null; para_salir_de_top10_pp: number | null };
  escenarios: { id: Escenario; etiqueta: string; nivel: Nivel; top10: boolean; pred: number }[];
  historia: { anio: number; tipo: string; abstencion: number | null; ns: number | null }[];
  grupo: { id: number | null; nombre: string | null };
  oscar: { nivel: Nivel | null; pred: number | null; comparacion: string | null };
}

type Param = string | number | boolean | null | undefined | string[];

export async function get<T>(path: string, params: Record<string, Param> = {}, signal?: AbortSignal): Promise<T> {
  const url = new URL(path, location.origin);
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === false) continue;
    for (const v of Array.isArray(value) ? value : [value]) url.searchParams.append(key, String(v));
  }
  const res = await fetch(url, { signal });
  if (!res.ok) throw new Error(`La API respondió ${res.status} en ${url.pathname}`);
  return res.json() as Promise<T>;
}

/** Pide `path` cada vez que cambian los parámetros; conserva el dato anterior mientras carga. */
export function useApi<T>(path: string, params: Record<string, Param> = {}) {
  const clave = path + JSON.stringify(params);
  const [estado, setEstado] = useState<{ data: T | null; error: string | null }>({ data: null, error: null });
  useEffect(() => {
    const ctl = new AbortController();
    get<T>(path, params, ctl.signal)
      .then((data) => setEstado({ data, error: null }))
      .catch((e) => e.name !== "AbortError" && setEstado((s) => ({ ...s, error: e.message })));
    return () => ctl.abort();
  }, [clave]);
  return estado;
}

export const ANIOS = [2009, 2012, 2015, 2018, 2021, 2024];
export const TIPO_ANIO: Record<number, "intermedia" | "presidencial"> = {
  2009: "intermedia", 2012: "presidencial", 2015: "intermedia", 2018: "presidencial", 2021: "intermedia", 2024: "presidencial",
};

export interface Historico {
  anios: { anio: number; tipo: string; secciones: number; ln: number; sv: number; nv: number; ns: number;
    abstencion: number; pct_ns: number; en_cartografia: number }[];
  ns_rangos: { anio: number; rango: string; secciones: number }[];
  cambios: { anio: number; comparada_con: number; secciones: number; nuevas: number; desaparecidas: number;
    cambio_municipio: number; cambio_tipo: number }[];
  bbox: [number, number, number, number];
}
export interface Grupos {
  config: { k: number; silhouette_k: number; sections_clustered: number; max_ns: number;
    naming_rules_pp: { trend: number; level: number }; groups: Record<string, string> };
  k_seleccion: { k: string; silhouette: string; tamanos: string }[];
  kpis: { agrupadas: number; agrupadas_en_cartografia: number; cartografia: number };
  perfil: { grupo: number; nombre: string; secciones: number; pct: number; intermedias: number; presidenciales: number;
    tendencia: number; volatilidad: number; urbana: number; rural: number; ln_mediana: number; jovenes: number }[];
  trayectorias: { grupo: number | null; anio: number; tipo: string; abstencion: number }[];
  composicion: { clave: number; nombre: string; grupo: number; secciones: number; pct: number; total: number }[];
  bbox: [number, number, number, number];
}
export interface Oscar {
  kpis: { ambos: number; mismo_nivel: number | null; dif_media_pp: number | null; solo_oscar: number; solo_oficial: number };
  matriz: { oficial: Nivel; oscar: Nivel; secciones: number }[];
  motivos: { motivo: string; secciones: number }[];
  por_unidad: { clave: number; nombre: string; ambos: number; mismo_nivel: number; dif_media_pp: number;
    alto_oficial: number; alto_oscar: number; solo_oscar: number }[];
  umbrales: Record<"oficial" | "oscar", { q50: number; q80: number; q90: number }>;
  nacional: { coincidencia_esperada_al_azar: number; coincidencia_top10: number; spearman_estimaciones: number };
  bbox: [number, number, number, number];
}

export const fmt = {
  n: (v: number) => v.toLocaleString("es-MX"),
  pct: (v: number | null | undefined, d = 1) => (v === null || v === undefined ? "—" : `${v.toFixed(d)}%`),
  share: (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${(v * 100).toFixed(1)}%`),
  pp: (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(1)} pp`),
};
