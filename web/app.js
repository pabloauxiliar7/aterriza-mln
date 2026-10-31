/* =====================================================================
   Aterriza MLN · lógica de la web (JavaScript sin librerías)

   Lee los archivos de data/ que genera GitHub Actions y dibuja las
   cuatro pantallas. Todo el cálculo de mínimos se hace en Python
   (scripts/reglas.py); aquí solo se muestra, salvo los comparadores
   del histórico, que recalculan al momento con el valor que elijas.
   ===================================================================== */

"use strict";

const ZONA = "Europe/Madrid";          // hora de Melilla
const MINUTOS_DESACTUALIZADO = 90;     // aviso si el METAR es más antiguo

const ESTADOS = {
  verde: { icono: "✓", nombre: "Por encima de los mínimos" },
  ambar: { icono: "!", nombre: "Condiciones marginales" },
  rojo:  { icono: "✕", nombre: "Por debajo de los mínimos" },
  gris:  { icono: "?", nombre: "Sin datos suficientes" },
};
const ESTADO_NUM = ["verde", "ambar", "rojo", "gris"];   // como en estadisticas.json
const MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];
const MESES_LARGOS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
  "agosto", "septiembre", "octubre", "noviembre", "diciembre"];

const AVISO_LEGAL = "Información orientativa elaborada con datos meteorológicos públicos. " +
  "No es información aeronáutica oficial ni anticipa las decisiones de las aerolíneas. " +
  "Consulte siempre con su compañía.";

const datos = { ahora: null, prevision: null, estadisticas: null };


/* ---------------------------------------------------------------------
   Utilidades
   --------------------------------------------------------------------- */

// Crea HTML escapando el texto (evita que un dato raro rompa la página).
function esc(texto) {
  return String(texto ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// 1150 → «1.150» (punto de millares, como en España)
function miles(n) {
  return String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}

function decimal(n, cifras = 1) {
  return n.toFixed(cifras).replace(".", ",");
}

// «2026-10-31T11:00Z» → objeto Date
function fecha(iso) {
  return new Date(iso.replace("Z", ":00Z"));
}

function horaLocal(d) {
  return new Intl.DateTimeFormat("es-ES", { timeZone: ZONA, hour: "2-digit", minute: "2-digit" }).format(d);
}
function horaUTC(d) {
  return new Intl.DateTimeFormat("es-ES", { timeZone: "UTC", hour: "2-digit", minute: "2-digit" }).format(d);
}
function diaLocal(d) {
  return new Intl.DateTimeFormat("es-ES", { timeZone: ZONA, weekday: "long", day: "numeric", month: "long" }).format(d);
}
function fechaCorta(d) {
  return new Intl.DateTimeFormat("es-ES", { timeZone: ZONA, day: "numeric", month: "short", year: "numeric" }).format(d);
}
function fechaHora(d) {
  return new Intl.DateTimeFormat("es-ES", {
    timeZone: ZONA, weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
  }).format(d);
}

function haceCuanto(d) {
  const min = Math.round((Date.now() - d.getTime()) / 60000);
  if (min < 1) return "hace un momento";
  if (min < 60) return `hace ${min} min`;
  const h = Math.floor(min / 60);
  if (h < 48) return `hace ${h} h ${min % 60 ? (min % 60) + " min" : ""}`.trim();
  return `hace ${Math.floor(h / 24)} días`;
}

function etiqueta(estado, texto) {
  const e = ESTADOS[estado] || ESTADOS.gris;
  return `<span class="etiqueta ${estado}"><span class="punto" aria-hidden="true">${e.icono}</span>${esc(texto || e.nombre)}</span>`;
}

function pie() {
  return `<p class="pie">${esc(AVISO_LEGAL)}</p>`;
}

async function cargarJSON(nombre) {
  // «no-store»: pide siempre la versión más reciente; si no hay conexión,
  // el service worker (sw.js) devuelve la última guardada.
  const respuesta = await fetch(`data/${nombre}`, { cache: "no-store" });
  if (!respuesta.ok) throw new Error(`${nombre}: ${respuesta.status}`);
  return respuesta.json();
}


/* ---------------------------------------------------------------------
   1. Pantalla «Ahora»
   --------------------------------------------------------------------- */

function pintarAhora() {
  const caja = document.getElementById("ahora-contenido");
  const a = datos.ahora;
  if (!a) {
    caja.innerHTML = `<p class="aviso">No se han podido cargar los datos actuales.</p>${pie()}`;
    return;
  }
  const s = a.semaforo;
  const e = ESTADOS[s.estado] || ESTADOS.gris;
  const hora = fecha(a.metar.hora_utc);
  const minutos = (Date.now() - hora.getTime()) / 60000;

  let html = "";
  if (minutos > MINUTOS_DESACTUALIZADO) {
    html += `<p class="aviso aviso-alerta" role="alert"><strong>Dato desactualizado:</strong>
      el último parte es de ${haceCuanto(hora)}. La situación puede haber cambiado.</p>`;
  }

  html += `
    <div class="semaforo ${s.estado}" role="status" aria-live="polite">
      <div class="luz" aria-hidden="true">${e.icono}</div>
      <div>
        <p class="estado-texto">${esc(s.texto)}</p>
        <p class="motivo">${esc(s.motivo)}</p>
      </div>
    </div>
    <p class="hora-dato">Parte de las <strong>${horaLocal(hora)}</strong> (hora de Melilla) ·
      ${horaUTC(hora)} UTC · ${haceCuanto(hora)}</p>`;

  if (a.aviso_viento) {
    html += `<p class="aviso">${esc(a.aviso_viento)}</p>`;
  }

  // Viento por pista
  html += `<h3>Viento por pista</h3>`;
  if (a.viento_por_pista) {
    const conRacha = (v, r) => (r != null && r !== v ? `${v} kt <span class="nota">(ráfagas ${r})</span>` : `${v} kt`);
    html += `<table class="tabla"><thead><tr><th>Pista</th><th>Cruzado</th><th>De cara</th><th>De cola</th></tr></thead><tbody>`;
    for (const p of a.viento_por_pista) {
      html += `<tr><td><strong>${esc(p.pista)}</strong></td>
        <td class="num">${conRacha(p.cruzado, p.cruzado_racha)}</td>
        <td class="num">${conRacha(p.cara, p.cara_racha)}</td>
        <td class="num">${conRacha(p.cola, p.cola_racha)}</td></tr>`;
    }
    html += `</tbody></table>`;
  } else {
    html += `<p class="nota">Sin dato de viento.</p>`;
  }

  // METAR descifrado y original
  html += `<h3>Parte meteorológico (METAR)</h3>
    <ul class="lista">${a.metar.descifrado.map((f) => `<li>${esc(f)}</li>`).join("")}</ul>
    <p class="nota">Texto original:</p>
    <code class="codigo">${esc(a.metar.texto)}</code>`;

  // Procedimientos evaluados
  html += `<h3>Procedimientos</h3><table class="tabla"><tbody>`;
  for (const p of a.procedimientos) {
    const est = p.ok === true ? (p.marginal ? "ambar" : "verde") : p.ok === false ? "rojo" : "gris";
    const texto = { verde: "Se cumple", ambar: "Se cumple, en el margen", rojo: "No se cumple", gris: "Sin datos" }[est];
    html += `<tr><td>${esc(p.nombre)}</td><td>${etiqueta(est, texto)}</td></tr>`;
  }
  html += `</tbody></table>`;

  caja.innerHTML = html + pie();
}


/* ---------------------------------------------------------------------
   2. Pantalla «Próximas 24 h»
   --------------------------------------------------------------------- */

function pintarPrevision() {
  const caja = document.getElementById("prevision-contenido");
  const p = datos.prevision;
  if (!p) {
    caja.innerHTML = `<p class="aviso">No se ha podido cargar la previsión.</p>${pie()}`;
    return;
  }
  const hasta = fecha(p.taf.hasta_utc);
  const ahora = new Date();
  // Solo las horas que aún no han terminado
  const horas = p.horas.filter((h) => fecha(h.inicio_utc).getTime() + 3600000 > ahora.getTime());

  let html = `<p class="nota">Previsión del aeropuerto (TAF) emitida el ${fechaHora(fecha(p.taf.emision_utc))},
    válida hasta el ${fechaHora(hasta)}. Horas en hora de Melilla.</p>`;

  if (hasta < ahora || horas.length === 0) {
    html += `<p class="aviso aviso-alerta">No hay una previsión en vigor ahora mismo.
      El aeropuerto suele publicarla durante su horario de apertura.</p>`;
  }

  let diaAnterior = "";
  let motivoAnterior = "";
  for (const h of horas) {
    const inicio = fecha(h.inicio_utc);
    const dia = diaLocal(inicio);
    if (dia !== diaAnterior) {
      html += `<h3 class="dia">${esc(dia[0].toUpperCase() + dia.slice(1))}</h3>`;
      diaAnterior = dia;
      motivoAnterior = "";
    }
    // El motivo solo se repite cuando cambia, para que la lista se lea de un vistazo.
    const motivo = h.motivo !== motivoAnterior ? `<p class="motivo">${esc(h.motivo)}</p>` : "";
    motivoAnterior = h.motivo;
    html += `<div class="franja">
      <div class="franja-cabecera">
        <span class="franja-hora">${horaLocal(inicio)}</span>
        ${etiqueta(h.estado, h.texto)}
      </div>
      ${motivo}`;
    for (const pos of h.posibles) {
      html += `<div class="posible">
        <span class="posible-titulo">Posible · ${esc(pos.tipo)}</span>
        ${etiqueta(pos.estado, pos.texto)}
        <div>${esc(pos.motivo)}</div>
      </div>`;
    }
    html += `</div>`;
  }

  html += `<details><summary>Ver el TAF original</summary><code class="codigo">${esc(p.taf.texto)}</code></details>
    <p class="nota">«Posible» corresponde a los grupos TEMPO (cambios temporales) y PROB
    (probabilidad del 30 o 40 %) del TAF. Se muestran aparte porque no son la previsión principal.</p>`;
  caja.innerHTML = html + pie();
}


/* ---------------------------------------------------------------------
   3. Pantalla «Histórico»
   --------------------------------------------------------------------- */

const historico = {
  causa: "todas",        // todas | techo | visibilidad | viento
  vientoPrueba: 30,      // límite de prueba de viento cruzado (kt)
  techoAlternativo: 350, // comparador (ft)
  celda: null,           // celda seleccionada {mes, hora}
};

// ¿La hora i cuenta como «en rojo» para la causa elegida?
function enRojo(D, i, causa, reglas) {
  if (causa === "todas") return D.e[i] === 2;
  if (causa === "techo") return (D.c[i] & 1) !== 0;
  if (causa === "visibilidad") return (D.c[i] & 2) !== 0;
  // Viento: si hay límites oficiales en config.yaml se usan; si no, el límite de prueba.
  if (reglas.viento_evaluado) return (D.c[i] & 4) !== 0;
  return D.x[i] > historico.vientoPrueba;
}

// Porcentaje por mes (0–11) × hora local (0–23)
function calcularMapa() {
  const est = datos.estadisticas;
  const D = est.datos;
  const total = Array.from({ length: 12 }, () => new Array(24).fill(0));
  const rojas = Array.from({ length: 12 }, () => new Array(24).fill(0));
  for (let i = 0; i < D.e.length; i++) {
    if (D.e[i] === 3) continue;                       // sin datos: no cuenta
    if (historico.causa === "viento" && D.x[i] < 0) continue;
    const m = D.m[i] - 1, h = D.h[i];
    total[m][h]++;
    if (enRojo(D, i, historico.causa, est.reglas)) rojas[m][h]++;
  }
  return { total, rojas };
}

// Escalones de color: 0 = nada; 1–7 = de menos a más.
const LIMITES = [0, 1, 2.5, 5, 7.5, 10, 15, 20];    // % (inicio de cada escalón)
function nivel(pct) {
  if (pct <= 0) return 0;
  let n = 1;
  for (let k = 1; k < LIMITES.length; k++) if (pct >= LIMITES[k]) n = k;
  return Math.min(n, 7);
}

// Comparador de techo: horas en rojo con un techo mínimo alternativo.
function compararTecho(alternativo) {
  const D = datos.estadisticas.datos;
  let validas = 0, rojasActual = 0, rojasAlt = 0;
  for (let i = 0; i < D.e.length; i++) {
    if (D.e[i] === 3) continue;
    validas++;
    if (D.e[i] === 2) rojasActual++;
    const otrasCausas = (D.c[i] & 6) !== 0;          // visibilidad o viento
    const techoFalla = D.t[i] >= 0 && D.t[i] * 100 < alternativo;
    if (otrasCausas || techoFalla) rojasAlt++;
  }
  const anos = validas / 8766;
  return {
    pctActual: (100 * rojasActual) / validas,
    pctAlt: (100 * rojasAlt) / validas,
    horasAno: (rojasActual - rojasAlt) / anos,
  };
}

function pintarHistorico() {
  const caja = document.getElementById("historico-contenido");
  const est = datos.estadisticas;
  if (!est) {
    caja.innerHTML = `<p class="aviso">No se han podido cargar las estadísticas.</p>${pie()}`;
    return;
  }
  const reglas = est.reglas;
  const techoActual = Math.min(...reglas.procedimientos.map((p) => p.techo_minimo_ft ?? Infinity));
  const D = est.datos;
  const validas = D.e.filter((e) => e !== 3).length;
  const rojas = D.e.filter((e) => e === 2).length;

  let html = `<p>Del ${fechaCorta(fecha(est.desde_utc))} al ${fechaCorta(fecha(est.hasta_utc))}
    (${decimal(est.anos)} años con datos), el aeropuerto estuvo <strong>por debajo de los mínimos
    el ${decimal((100 * rojas) / validas)} % de las horas</strong>.</p>

    <h3>Porcentaje de horas en rojo</h3>
    <p class="nota">Por mes y hora de Melilla. Toca una casilla para ver el detalle.</p>
    <div class="selector" role="group" aria-label="Causa">
      ${[["todas", "Cualquier causa"], ["techo", "Techo"], ["visibilidad", "Visibilidad"], ["viento", "Viento"]]
        .map(([v, t]) => `<button type="button" data-causa="${v}" aria-pressed="${historico.causa === v}">${t}</button>`).join("")}
    </div>`;

  if (historico.causa === "viento" && !reglas.viento_evaluado) {
    html += `<div class="tarjeta">
      <label for="viento-prueba">Límite de prueba de viento cruzado: <span id="viento-valor">${historico.vientoPrueba}</span> kt</label>
      <input id="viento-prueba" type="range" min="10" max="50" step="1" value="${historico.vientoPrueba}">
      <p class="nota">No hay límites oficiales de viento en config.yaml. Este control solo sirve para
      explorar: cuenta las horas en que el viento cruzado (con ráfagas) supera el valor elegido.</p>
    </div>`;
  }

  html += `<div id="mapa"></div>
    <p id="detalle-celda" class="detalle-celda" aria-live="polite"></p>

    <h3>¿Y si el techo mínimo fuera otro?</h3>
    <div class="tarjeta">
      <label for="techo-alt">Techo mínimo alternativo (ft)</label>
      <input id="techo-alt" type="number" inputmode="numeric" min="0" max="5000" step="50" value="${historico.techoAlternativo}">
      <p id="resultado-techo" class="resultado" aria-live="polite"></p>
      <p class="nota">Compara con el techo mínimo actual (${miles(techoActual)} ft), sin cambiar
      la visibilidad ni el viento. Cuenta todas las horas del día, también las de aeropuerto cerrado.</p>
    </div>`;

  caja.innerHTML = html + pie();

  caja.querySelectorAll("[data-causa]").forEach((b) =>
    b.addEventListener("click", () => { historico.causa = b.dataset.causa; pintarHistorico(); }));
  const deslizador = document.getElementById("viento-prueba");
  if (deslizador) {
    deslizador.addEventListener("input", () => {
      historico.vientoPrueba = Number(deslizador.value);
      document.getElementById("viento-valor").textContent = deslizador.value;
      pintarMapa();
    });
  }
  const entrada = document.getElementById("techo-alt");
  const actualizarComparador = () => {
    const valor = Number(entrada.value);
    const salida = document.getElementById("resultado-techo");
    if (!Number.isFinite(valor) || valor < 0 || valor > 5000) {
      salida.textContent = "Escribe un valor entre 0 y 5.000 ft.";
      return;
    }
    historico.techoAlternativo = valor;
    const r = compararTecho(valor);
    const horas = Math.round(Math.abs(r.horasAno));
    let frase;
    if (horas === 0) frase = `Con ${miles(valor)} ft no cambiaría prácticamente nada.`;
    else if (r.horasAno > 0) frase = `Con ${miles(valor)} ft se ganarían unas <strong>${miles(horas)} horas al año</strong>.`;
    else frase = `Con ${miles(valor)} ft se perderían unas <strong>${miles(horas)} horas al año</strong>.`;
    salida.innerHTML = `${frase}<br><span class="nota">Horas en rojo: del ${decimal(r.pctActual)} % al ${decimal(r.pctAlt)} %.</span>`;
  };
  entrada.addEventListener("input", actualizarComparador);
  actualizarComparador();
  pintarMapa();
}

function pintarMapa() {
  const { total, rojas } = calcularMapa();
  const nombreCausa = { todas: "en rojo", techo: "en rojo por techo", visibilidad: "en rojo por visibilidad",
    viento: datos.estadisticas.reglas.viento_evaluado ? "en rojo por viento"
      : `con viento cruzado de más de ${historico.vientoPrueba} kt` }[historico.causa];

  // Tabla: columnas = meses, filas = horas (cabe mejor en un móvil en vertical)
  let html = `<div class="mapa-contenedor"><table class="mapa">
    <caption class="solo-lectores">Porcentaje de horas ${nombreCausa}, por mes y hora local</caption>
    <thead><tr><th class="hora" scope="col">Hora</th>${MESES.map((m) => `<th scope="col">${m}</th>`).join("")}</tr></thead><tbody>`;
  for (let h = 0; h < 24; h++) {
    html += `<tr><th class="hora" scope="row">${String(h).padStart(2, "0")}</th>`;
    for (let m = 0; m < 12; m++) {
      const pct = total[m][h] ? (100 * rojas[m][h]) / total[m][h] : 0;
      const sel = historico.celda && historico.celda.m === m && historico.celda.h === h ? " seleccionada" : "";
      const texto = pct === 0 ? "·" : pct < 1 ? "<1" : Math.round(pct);
      html += `<td class="n${nivel(pct)}${sel}" data-m="${m}" data-h="${h}"
        aria-label="${MESES_LARGOS[m]}, ${h} h: ${decimal(pct)} %">${texto}</td>`;
    }
    html += `</tr>`;
  }
  html += `</tbody></table></div>`;

  // Leyenda
  html += `<div class="leyenda" aria-hidden="true"><span>0 %</span>`;
  for (let k = 0; k <= 7; k++) html += `<span class="caja n${k}"></span>`;
  html += `<span>${LIMITES[7]} % o más</span></div>`;

  const contenedor = document.getElementById("mapa");
  contenedor.innerHTML = html;
  contenedor.querySelectorAll("td").forEach((td) =>
    td.addEventListener("click", () => {
      historico.celda = { m: Number(td.dataset.m), h: Number(td.dataset.h) };
      pintarMapa();
    }));

  // Detalle de la casilla elegida
  const detalle = document.getElementById("detalle-celda");
  if (historico.celda) {
    const { m, h } = historico.celda;
    const pct = total[m][h] ? (100 * rojas[m][h]) / total[m][h] : 0;
    detalle.innerHTML = `<strong>${MESES_LARGOS[m][0].toUpperCase() + MESES_LARGOS[m].slice(1)}, de ${String(h).padStart(2, "0")}:00 a ${String((h + 1) % 24).padStart(2, "0")}:00</strong>:
      ${decimal(pct)} % de horas ${nombreCausa} (${rojas[m][h]} de ${total[m][h]} horas en 10 años).`;
  } else {
    detalle.textContent = "";
  }
}


/* ---------------------------------------------------------------------
   4. Pantalla «Ajustes»
   --------------------------------------------------------------------- */

function leerTema() {
  try { return localStorage.getItem("tema") || "auto"; } catch { return "auto"; }
}
function aplicarTema(tema) {
  if (tema === "auto") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.setAttribute("data-theme", tema === "oscuro" ? "dark" : "light");
  try { localStorage.setItem("tema", tema); } catch { /* sin almacenamiento: no pasa nada */ }
}

function pintarAjustes() {
  const caja = document.getElementById("ajustes-contenido");
  const r = (datos.ahora && datos.ahora.reglas) || (datos.estadisticas && datos.estadisticas.reglas);
  const tema = leerTema();

  let html = `<h3>Aspecto</h3>
    <div class="selector" role="group" aria-label="Tema">
      ${[["auto", "Automático"], ["claro", "Claro"], ["oscuro", "Oscuro"]]
        .map(([v, t]) => `<button type="button" data-tema="${v}" aria-pressed="${tema === v}">${t}</button>`).join("")}
    </div>`;

  html += `<h3>Mínimos aplicados</h3>`;
  if (r) {
    const valor = (v, unidad) => (v == null ? "<em>Sin definir</em>" : `${miles(v)} ${unidad}`);
    html += `<table class="tabla"><thead><tr><th>Procedimiento</th><th>Techo</th><th>Visibilidad</th></tr></thead><tbody>`;
    for (const p of r.procedimientos) {
      const pista = p.pista === "cualquiera" ? "" : ` · pista ${esc(p.pista)}`;
      html += `<tr><td>${esc(p.nombre)}${pista}</td><td class="num">${valor(p.techo_minimo_ft, "ft")}</td>
        <td class="num">${valor(p.visibilidad_minima_m, "m")}</td></tr>`;
    }
    html += `</tbody></table>
      <ul class="lista">
        <li>Rumbo magnético de las pistas: ${Object.entries(r.pistas).map(([n, v]) => `${esc(n)} → ${v}°`).join(", ")}.</li>
        <li>Margen de «marginal» (ámbar): ${r.margen_marginal_pct} % por encima de los mínimos.</li>
        <li>Viento cruzado máximo: ${valor(r.cruzado_maximo_kt, "kt")} · de cola: ${valor(r.cola_maximo_kt, "kt")}.
          ${r.viento_evaluado ? "" : "Mientras no estén definidos, el viento se muestra solo como información."}</li>
      </ul>
      <p class="nota">Techo: capa de nubes nubosa (BKN), cubierta (OVC) o cielo oculto (VV) más baja,
      medida sobre el aeropuerto. La normativa europea limita la aproximación por visibilidad; el techo
      es un indicador muy útil, pero no una prohibición por sí mismo. Mínimos tomados del AIP de España
      y de la normativa europea de operaciones; se pueden cambiar en el archivo config.yaml.</p>`;
  }

  html += `<h3>Última actualización</h3><ul class="lista">`;
  if (datos.ahora) {
    html += `<li>Parte actual (METAR): ${fechaHora(fecha(datos.ahora.metar.hora_utc))}.</li>
      <li>Comprobado por última vez con datos nuevos: ${fechaHora(fecha(datos.ahora.generado_utc))}.</li>`;
  }
  if (datos.prevision) html += `<li>Previsión (TAF) emitida: ${fechaHora(fecha(datos.prevision.taf.emision_utc))}.</li>`;
  if (datos.estadisticas) html += `<li>Histórico: hasta el ${fechaCorta(fecha(datos.estadisticas.hasta_utc))}.</li>`;
  html += `</ul>`;

  html += `<h3>Fuentes</h3><ul class="lista">
    <li>Partes actuales (METAR y TAF): <a href="https://aviationweather.gov/" rel="noopener">aviationweather.gov</a>
      (Servicio Meteorológico de Estados Unidos).</li>
    <li>Histórico de 10 años: <a href="https://mesonet.agron.iastate.edu/request/download.phtml" rel="noopener">Iowa Environmental Mesonet</a>
      (Universidad Estatal de Iowa).</li>
    <li>Rumbos de pista y mínimos de aproximación: <a href="https://aip.enaire.es/AIP/#GEML" rel="noopener">AIP de España, aeropuerto de Melilla</a>.</li>
  </ul>
  <p class="nota">Esta web no usa cookies, no recoge datos personales y no tiene analítica.</p>

  <h3>Aviso legal</h3>
  <p class="aviso">${esc(AVISO_LEGAL)}</p>`;

  caja.innerHTML = html;
  caja.querySelectorAll("[data-tema]").forEach((b) =>
    b.addEventListener("click", () => { aplicarTema(b.dataset.tema); pintarAjustes(); }));
}


/* ---------------------------------------------------------------------
   Navegación entre pantallas
   --------------------------------------------------------------------- */

const PANTALLAS = ["ahora", "prevision", "historico", "ajustes"];

function mostrar(nombre) {
  if (!PANTALLAS.includes(nombre)) nombre = "ahora";
  for (const p of PANTALLAS) document.getElementById(p).hidden = p !== nombre;
  document.querySelectorAll(".navegacion button").forEach((b) => {
    if (b.dataset.pantalla === nombre) b.setAttribute("aria-current", "page");
    else b.removeAttribute("aria-current");
  });
  if (location.hash !== "#" + nombre) history.replaceState(null, "", "#" + nombre);
  window.scrollTo(0, 0);
}

document.querySelectorAll(".navegacion button").forEach((b) =>
  b.addEventListener("click", () => mostrar(b.dataset.pantalla)));
window.addEventListener("hashchange", () => mostrar(location.hash.slice(1)));


/* ---------------------------------------------------------------------
   Arranque
   --------------------------------------------------------------------- */

function avisoConexion() {
  document.getElementById("aviso-conexion").hidden = navigator.onLine;
}

async function cargarTodo() {
  const [ahora, prevision] = await Promise.allSettled([cargarJSON("ahora.json"), cargarJSON("24h.json")]);
  datos.ahora = ahora.status === "fulfilled" ? ahora.value : datos.ahora;
  datos.prevision = prevision.status === "fulfilled" ? prevision.value : datos.prevision;
  pintarAhora();
  pintarPrevision();
  pintarAjustes();
  // Las estadísticas pesan más: se cargan después y solo una vez.
  if (!datos.estadisticas) {
    try { datos.estadisticas = await cargarJSON("estadisticas.json"); } catch { /* se avisa al pintar */ }
    pintarHistorico();
    pintarAjustes();
  }
}

aplicarTema(leerTema());
mostrar(location.hash.slice(1));
avisoConexion();
window.addEventListener("online", () => { avisoConexion(); cargarTodo(); });
window.addEventListener("offline", avisoConexion);
// Al volver a la aplicación (por ejemplo, desde otra app del iPhone), refrescar.
document.addEventListener("visibilitychange", () => { if (!document.hidden) cargarTodo(); });
// Y cada 5 minutos mientras está abierta.
setInterval(cargarTodo, 5 * 60 * 1000);
cargarTodo();

// Funcionamiento sin conexión
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("sw.js").catch(() => { /* sin service worker: la web funciona igual */ });
}
