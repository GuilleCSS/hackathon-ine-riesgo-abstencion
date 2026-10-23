// Los colores del mapa salen de las variables CSS (src/styles/global.css): una sola fuente.
export const token = (name: string) =>
  getComputedStyle(document.documentElement).getPropertyValue(`--${name}`).trim();

// Para las opciones de MapLibre que piden píxeles: así también escalan con el tamaño de letra.
export const rem = (n: number) => n * parseFloat(getComputedStyle(document.documentElement).fontSize);

export const nivelColor = (nivel: string | null | undefined) =>
  nivel === "BAJO" ? "var(--riesgo-bajo)" : nivel === "MEDIO" ? "var(--riesgo-medio)"
    : nivel === "ALTO" ? "var(--riesgo-alto)" : "var(--sin-estimacion)";
