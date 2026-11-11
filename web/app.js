/* SEDATI · cliente web del sistema experto (núcleo, diagnóstico, base de conocimiento e historial).
 *
 * Esta página no contiene reglas ni lógica de inferencia: envía los síntomas y las respuestas a la
 * API REST (AWS Lambda + API Gateway) y muestra lo que el motor responde. El servicio no guarda
 * estado entre peticiones, así que el cliente conserva la lista de respuestas y la envía completa.
 * La sesión viaja en un token firmado que el servicio renueva en cada respuesta (15 min sin actividad).
 * Los procesos transaccionales (acceso, incidentes, citas, usuarios, indicadores) están en atencion.js.
 */
'use strict';

const API = ((window.SEDATI_CONFIG && window.SEDATI_CONFIG.apiUrl) || '').replace(/\/+$/, '');
const SERIE = ['#1F6FEB', '#13A89E', '#F2A541', '#8E6CEF', '#E5646E'];

const estado = {
  catalogo: null,
  escala: [],
  sintomas: new Set(),     // id de evidencia marcados como síntomas iniciales
  respuestas: [],          // [{evidencia_id, escala}] en el orden en que se respondieron
  sesion: null,            // última respuesta de la API (estado completo de la consulta)
  seleccion: 0,            // hipótesis seleccionada en la vista de resultado
  porQue: false,           // explicación de la pregunta visible
  origen: 'nueva',         // 'nueva' | 'historial'
  bcCargada: false,
  evidenciasCargadas: false,
  hipotesis: [],
  evidencias: [],
  hipotesisSeleccionada: null,
  incidente: null,         // {id, codigo, ronda, descartadas} cuando el diagnóstico es una ronda de un incidente
  token: null,
  usuario: null,
};
const alMostrar = {};      // nombre de vista -> función que la carga (las registra atencion.js)
const esAdmin = () => !!(estado.usuario && estado.usuario.rol === 'ADMINISTRADOR');

function guardarToken(token) {
  estado.token = token;
  try { if (token) sessionStorage.setItem('sedati_token', token); else sessionStorage.removeItem('sedati_token'); } catch (e) { /* sin almacenamiento */ }
}
function tokenGuardado() {
  try { return sessionStorage.getItem('sedati_token'); } catch (e) { return null; }
}

// ================================================================ utilidades
const $ = (sel) => document.querySelector(sel);

function esc(texto) {
  return String(texto ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

const fmtPct = (p, dec = 1) => (p ?? 0).toLocaleString('es-CO', { style: 'percent', minimumFractionDigits: dec, maximumFractionDigits: dec });
const fmtNum = (n, dec = 2) => (n ?? 0).toLocaleString('es-CO', { minimumFractionDigits: dec, maximumFractionDigits: dec });
const fmtSigno = (n, dec = 2) => (n > 0 ? '+' : n < 0 ? '−' : '') + fmtNum(Math.abs(n), dec);
const mayuscula = (t) => (t ? t[0].toUpperCase() + t.slice(1) : '');

let temporizadorAviso;
function aviso(texto, error = false) {
  const el = $('#aviso');
  el.textContent = texto;
  el.className = 'aviso-flotante visible' + (error ? ' error' : '');
  clearTimeout(temporizadorAviso);
  temporizadorAviso = setTimeout(() => { el.className = 'aviso-flotante'; }, error ? 6000 : 3000);
}

async function api(ruta, opciones = {}) {
  const init = { method: opciones.method || 'GET', headers: {} };
  if (estado.token) init.headers.Authorization = `Bearer ${estado.token}`;
  if (opciones.body !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(opciones.body);
  }
  let respuesta;
  try {
    respuesta = await fetch(`${API}/api${ruta}`, init);
  } catch (e) {
    throw new Error(`No fue posible contactar el servicio (${API || 'mismo sitio'}). Revise la URL en config.js y la configuración CORS.`);
  }
  let datos = null;
  try { datos = await respuesta.json(); } catch (e) { /* respuesta sin JSON */ }
  if (datos && datos._sesion) { guardarToken(datos._sesion.token); window.dispatchEvent(new Event('sedati:actividad')); }
  if (respuesta.status === 401 && !ruta.startsWith('/auth/ingresar')) {
    window.dispatchEvent(new CustomEvent('sedati:sesion-vencida', { detail: datos && datos.error }));
  }
  if (!respuesta.ok) {
    const error = new Error((datos && datos.error) || `El servicio respondió ${respuesta.status}.`);
    error.estado = respuesta.status;
    throw error;
  }
  return datos;
}

async function ocupado(promesa) {
  document.body.classList.add('ocupado');
  try { return await promesa; } finally { document.body.classList.remove('ocupado'); }
}

// ================================================================ navegación
function mostrarVista(nombre, ...args) {
  const pestana = { incidente: 'incidentes' }[nombre] || nombre;
  document.querySelectorAll('.pestana').forEach((b) => b.classList.toggle('activa', b.dataset.vista === pestana));
  document.querySelectorAll('.vista').forEach((v) => v.classList.toggle('activa', v.id === `vista-${nombre}`));
  if (nombre === 'diagnostico' && !estado.catalogo) cargarCatalogo();
  if (alMostrar[nombre]) alMostrar[nombre](...args);
  if (nombre === 'conocimiento' && !estado.bcCargada) cargarConocimiento();
  if (nombre === 'historial') cargarHistorial();
  if (nombre === 'servicio') pintarServicio();
  window.scrollTo({ top: 0 });
}

function mostrarEtapa(nombre) {
  document.querySelectorAll('.etapa').forEach((e) => e.classList.toggle('activa', e.id === `etapa-${nombre}`));
  window.scrollTo({ top: 0 });
}

// ================================================================ inicio: catálogo de síntomas
async function cargarCatalogo() {
  try {
    const cat = await api('/catalogo');
    estado.catalogo = cat;
    estado.escala = cat.escala;
    pintarSintomas();
    return cat;
  } catch (e) {
    $('#lista-sintomas').innerHTML = `<div class="error-carga"><b>No se pudo cargar el catálogo.</b><br>${esc(e.message)}</div>`;
    return null;
  }
}

async function revisarServicio() {
  const pill = $('#estado-servicio');
  try {
    const s = await api('/salud');
    pill.className = 'estado-servicio ok';
    pill.querySelector('.texto').textContent = `En línea · ${s.base_datos}`;
    pill.title = `API: ${API || location.origin}`;
    return s;
  } catch (e) {
    pill.className = 'estado-servicio error';
    pill.querySelector('.texto').textContent = 'Servicio no disponible';
    pill.title = e.message;
    return null;
  }
}

function pintarSintomas() {
  const cont = $('#lista-sintomas');
  cont.innerHTML = estado.catalogo.categorias.filter((c) => c.sintomas.length).map((c) => `
    <section class="categoria">
      <header><span class="letra">${esc(c.codigo)}</span><b>${esc(c.nombre)}</b><small>${c.reglas} reglas</small></header>
      ${c.sintomas.map((s) => `
        <label class="sintoma">
          <input type="checkbox" value="${s.id}" ${estado.sintomas.has(s.id) ? 'checked' : ''}>
          <span>${esc(mayuscula(s.enunciado))}</span><span class="codigo">${esc(s.codigo)}</span>
        </label>`).join('')}
    </section>`).join('');
  cont.querySelectorAll('input[type=checkbox]').forEach((chk) => chk.addEventListener('change', () => {
    const id = Number(chk.value);
    chk.checked ? estado.sintomas.add(id) : estado.sintomas.delete(id);
    resumirSintomas();
  }));
  resumirSintomas();
}

function textoSintoma(id) {
  for (const c of estado.catalogo.categorias) {
    const s = c.sintomas.find((x) => x.id === id);
    if (s) return mayuscula(s.enunciado);
  }
  return `E-${id}`;
}

function resumirSintomas() {
  const n = estado.sintomas.size;
  $('#boton-iniciar').disabled = n === 0;
  $('#resumen-sintomas').textContent = n
    ? `${n} síntoma(s): ${[...estado.sintomas].map(textoSintoma).join('; ')}`
    : 'Marque al menos un síntoma para iniciar.';
}

function limpiarInicio() {
  estado.sintomas.clear();
  ['#campo-equipo', '#campo-ubicacion', '#campo-descripcion'].forEach((s) => { $(s).value = ''; });
  if (estado.catalogo) pintarSintomas();
}

// ================================================================ ronda de diagnóstico de un incidente
function pintarBannerIncidente() {
  const b = $('#banner-incidente');
  const inc = estado.incidente;
  b.hidden = !inc;
  $('#caja-datos-equipo').hidden = !!inc;
  $('#titulo-diagnostico').textContent = inc ? `Ronda ${inc.ronda} de diagnóstico` : 'Nuevo diagnóstico';
  if (!inc) { b.innerHTML = ''; return; }
  b.innerHTML = `<div><b>${esc(inc.codigo)}</b> · ronda ${inc.ronda} · ${esc(inc.inventario)} · ${esc(inc.ubicacion)}
      <small>${esc(inc.descripcion)}</small>
      ${inc.descartadas.length ? `<small>Hipótesis excluidas por rondas anteriores: ${inc.descartadas.map(esc).join(', ')}</small>` : ''}</div>
    <button class="boton secundario pequeno" id="boton-salir-ronda">Volver al incidente</button>`;
  $('#boton-salir-ronda').addEventListener('click', () => {
    const id = inc.id;
    terminarRonda();
    mostrarVista('incidente', id);
  });
}

async function iniciarRondaIncidente(incidenteId) {
  const datos = await ocupado(api(`/incidentes/${incidenteId}/ronda`));
  if (!estado.catalogo) await cargarCatalogo();
  const i = datos.incidente;
  estado.incidente = { id: i.id, codigo: i.codigo, ronda: datos.ronda, descartadas: datos.descartadas,
    inventario: i.inventario, ubicacion: i.ubicacion, descripcion: i.descripcion };
  estado.sintomas = new Set(datos.sintomas);
  estado.respuestas = [];
  estado.sesion = null;
  mostrarVista('diagnostico');
  pintarBannerIncidente();
  pintarSintomas();
  mostrarEtapa('inicio');
  if (datos.sintomas.length) aviso('Se marcaron los síntomas de la ronda anterior; ajústelos si es necesario.');
}

function terminarRonda() {
  estado.incidente = null;
  estado.sesion = null;
  estado.respuestas = [];
  limpiarInicio();
  pintarBannerIncidente();
  mostrarEtapa('inicio');
}

async function guardarRonda() {
  const inc = estado.incidente;
  try {
    const s = await ocupado(api(`/incidentes/${inc.id}/diagnosticos`, { method: 'POST', body: cuerpoConsulta() }));
    aviso(`Ronda ${s.ronda} guardada en ${inc.codigo}. Confirme o descarte las hipótesis propuestas.`);
    terminarRonda();
    mostrarVista('incidente', inc.id);
  } catch (e) { aviso(e.message, true); }
}

// ================================================================ consulta
function cuerpoConsulta() {
  return {
    sintomas: [...estado.sintomas],
    respuestas: estado.respuestas,
    incidente_id: estado.incidente ? estado.incidente.id : undefined,
    equipo: $('#campo-equipo').value.trim(),
    ubicacion: $('#campo-ubicacion').value.trim(),
    descripcion: $('#campo-descripcion').value.trim(),
  };
}

async function diagnosticar() {
  estado.sesion = await ocupado(api('/diagnostico', { method: 'POST', body: cuerpoConsulta() }));
  estado.porQue = false;
  pintarConsulta();
}

async function iniciar() {
  if (!estado.sintomas.size) return;
  estado.respuestas = [];
  estado.origen = 'nueva';
  try {
    await diagnosticar();
    mostrarEtapa('consulta');
  } catch (e) { aviso(e.message, true); }
}

async function responder(codigo) {
  const q = estado.sesion && estado.sesion.pregunta;
  if (!q || document.body.classList.contains('ocupado')) return;
  estado.respuestas.push({ evidencia_id: q.evidencia.id, escala: codigo });
  try {
    await diagnosticar();
  } catch (e) {
    estado.respuestas.pop();
    aviso(e.message, true);
  }
}

async function deshacer() {
  if (!estado.respuestas.length) return;
  const quitada = estado.respuestas.pop();
  try { await diagnosticar(); } catch (e) { estado.respuestas.push(quitada); aviso(e.message, true); }
}

function pintarConsulta() {
  const s = estado.sesion;
  $('#subtitulo-consulta').textContent = `${estado.incidente ? `${estado.incidente.codigo} · ronda ${estado.incidente.ronda} · ` : ''}${estado.sintomas.size} síntoma(s) inicial(es) · ${s.preguntas_respondidas} pregunta(s) respondida(s) · `
    + `${s.diferencial} hipótesis y ${s.reglas_en_memoria} reglas en el diagnóstico diferencial`;
  $('#boton-deshacer').disabled = estado.respuestas.length === 0;
  pintarPregunta();
  pintarRespuestas();
  pintarBarras($('#barras-vivo'), s.top);
  $('#resumen-diferencial').textContent = `Las ${s.top.length} hipótesis con mayor peso entre las ${s.diferencial} del diagnóstico diferencial.`;
  pintarEvolucion($('#grafico-evolucion'), s);
  pintarTraza(s.traza);
}

function pintarPregunta() {
  const s = estado.sesion;
  const q = s.pregunta;
  const caja = $('#tarjeta-pregunta');
  let html = '';
  if (s.motivo_conclusion) {
    html += `<div class="aviso-conclusion"><p><b>El motor recomienda concluir</b>${esc(s.motivo_conclusion)}</p>
      <button class="boton" data-accion="resultado">Ver diagnóstico</button></div>`;
  }
  if (!q) {
    html += '<p class="vacio">No quedan preguntas pendientes en el diagnóstico diferencial.</p>';
    caja.innerHTML = html;
    caja.querySelectorAll('[data-accion=resultado]').forEach((b) => b.addEventListener('click', verResultado));
    return;
  }
  const avance = Math.min(100, (s.preguntas_respondidas / s.maximo_preguntas) * 100);
  const tipo = q.evidencia.tipo === 'SINTOMA' ? 'síntoma' : 'prueba';
  html += `
    <div class="pregunta-numero"><span>Pregunta ${q.numero}${s.motivo_conclusion ? ' (opcional)' : ''}</span>
      <span>${s.preguntas_respondidas} de ${s.maximo_preguntas} como máximo</span></div>
    <div class="progreso"><span style="width:${avance}%"></span></div>
    <p class="pregunta-texto">${esc(q.evidencia.pregunta)}</p>
    <p class="pregunta-meta">${esc(q.evidencia.codigo)} · ${tipo} · aparece en ${q.reglas.length} regla(s) · ganancia esperada ${fmtNum(q.ganancia, 3)} bits</p>
    <div class="opciones">
      ${estado.escala.map((o, i) => `
        <button class="opcion" style="--c:${esc(o.color)}" data-escala="${esc(o.codigo)}" title="Tecla ${i + 1}">
          <i></i>${esc(o.etiqueta)}<small>${fmtSigno(o.valor, 1)}</small><kbd>${i + 1}</kbd>
        </button>`).join('')}
    </div>
    <div class="por-que">
      <button class="enlace" data-accion="porque">${estado.porQue ? 'Ocultar explicación' : '¿Por qué pregunta esto?'}</button>
      ${estado.porQue ? `<pre>${esc(q.por_que.join('\n'))}</pre>` : ''}
    </div>`;
  caja.innerHTML = html;
  caja.querySelectorAll('[data-escala]').forEach((b) => b.addEventListener('click', () => responder(b.dataset.escala)));
  caja.querySelectorAll('[data-accion=resultado]').forEach((b) => b.addEventListener('click', verResultado));
  caja.querySelector('[data-accion=porque]').addEventListener('click', () => { estado.porQue = !estado.porQue; pintarPregunta(); });
}

function colorEscala(codigo) {
  const o = estado.escala.find((x) => x.codigo === codigo);
  return o ? o.color : '#8A94A6';
}

function pintarRespuestas() {
  const lista = $('#lista-respuestas');
  const rs = estado.sesion.respuestas;
  lista.innerHTML = rs.length ? rs.map((r) => `
    <li><span class="n">${r.orden}</span>
      <span class="t">${esc(mayuscula(r.evidencia.enunciado))} <span class="etiqueta-origen">· ${esc(r.evidencia.codigo)}${r.origen === 'SINTOMA_INICIAL' ? ' · síntoma inicial' : ''}</span></span>
      <span class="etiqueta-respuesta" style="--c:${esc(colorEscala(r.escala))}">${esc(r.etiqueta)}</span></li>`).join('')
    : '<li class="vacio">Sin respuestas.</li>';
  lista.scrollTop = lista.scrollHeight;
}

function pintarBarras(cont, top) {
  cont.innerHTML = top.map((r, i) => `
    <div class="barra-h" style="--c:${SERIE[i % SERIE.length]}">
      <span class="nombre" title="${esc(r.hipotesis.nombre)}">${r.posicion}. ${esc(r.hipotesis.nombre)}</span>
      <span class="valor">${fmtPct(r.probabilidad)}</span>
      <span class="pista"><span style="width:${(r.probabilidad * 100).toFixed(2)}%"></span></span>
    </div>`).join('');
}

function pintarEvolucion(cont, s) {
  const pasos = s.evolucion;
  const W = 560, H = 210, iz = 34, de = 10, ar = 10, ab = 24;
  const ancho = W - iz - de, alto = H - ar - ab;
  const x = (i) => iz + (pasos.length > 1 ? (i / (pasos.length - 1)) * ancho : ancho / 2);
  const y = (p) => ar + (1 - p) * alto;
  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Evolución del peso probabilístico de las hipótesis">`;
  [0, 0.25, 0.5, 0.75, 1].forEach((p) => {
    svg += `<line class="eje" x1="${iz}" x2="${W - de}" y1="${y(p)}" y2="${y(p)}" stroke-dasharray="${p ? '3 4' : ''}"/>`;
    svg += `<text x="${iz - 6}" y="${y(p) + 3}" text-anchor="end">${p * 100}%</text>`;
  });
  pasos.forEach((p, i) => {
    if (pasos.length <= 12 || i % Math.ceil(pasos.length / 12) === 0) {
      svg += `<text x="${x(i)}" y="${H - 6}" text-anchor="middle">${i === 0 ? 'inicio' : 'P' + i}</text>`;
    }
  });
  s.top.forEach((r, k) => {
    const id = String(r.hipotesis.id);
    const puntos = pasos.map((p, i) => `${x(i).toFixed(1)},${y(p.probabilidades[id] || 0).toFixed(1)}`).join(' ');
    const color = SERIE[k % SERIE.length];
    svg += `<polyline points="${puntos}" fill="none" stroke="${color}" stroke-width="${k === 0 ? 2.6 : 1.8}" stroke-linejoin="round" stroke-linecap="round"/>`;
    const ultimo = pasos[pasos.length - 1];
    svg += `<circle cx="${x(pasos.length - 1)}" cy="${y(ultimo.probabilidades[id] || 0)}" r="3.2" fill="${color}"><title>${esc(r.hipotesis.nombre)}: ${fmtPct(ultimo.probabilidades[id] || 0)}</title></circle>`;
  });
  svg += '</svg>';
  const leyenda = s.top.map((r, k) => `<span style="--c:${SERIE[k % SERIE.length]}"><i></i>${esc(r.hipotesis.codigo)} · ${esc(r.hipotesis.nombre)}</span>`).join('');
  cont.className = 'grafico';
  cont.innerHTML = svg + `<div class="leyenda">${leyenda}</div>`;
}

function pintarTraza(traza) {
  const filas = traza.reduce((a, t) => a + t.filas, 0);
  $('#resumen-traza').textContent = `El motor no carga toda la base: hizo ${traza.length} consultas sucesivas que devolvieron ${filas} fila(s) en total.`;
  let texto = '', paso = -1;
  for (const t of traza) {
    if (t.paso !== paso) {
      paso = t.paso;
      texto += `${texto ? '\n' : ''}── ${paso === 0 ? 'Síntomas iniciales' : 'Respuesta ' + paso} ${'─'.repeat(30)}\n`;
    }
    texto += `  ${t.descripcion.padEnd(52)} ${String(t.filas).padStart(3)} fila(s)\n`;
  }
  $('#traza').textContent = texto;
}

// ================================================================ resultado
function verResultado() {
  estado.seleccion = 0;
  pintarResultado();
  mostrarEtapa('resultado');
}

async function guardarConsulta() {
  try {
    estado.sesion = await ocupado(api('/consultas', { method: 'POST', body: cuerpoConsulta() }));
    aviso(`Consulta #${estado.sesion.consulta_id} guardada en la base de datos.`);
    pintarResultado();
  } catch (e) { aviso(e.message, true); }
}

async function descargarInforme(id) {
  try {
    const datos = await ocupado(api(`/consultas/${id}/informe`));
    const blob = new Blob([datos.informe], { type: 'text/plain;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `informe_consulta_${id}.txt`;
    a.click();
    URL.revokeObjectURL(a.href);
  } catch (e) { aviso(e.message, true); }
}

function nuevoDiagnostico() {
  estado.sesion = null;
  estado.respuestas = [];
  estado.incidente = null;
  limpiarInicio();
  pintarBannerIncidente();
  mostrarVista('diagnostico');
  mostrarEtapa('inicio');
}

function pintarResultado() {
  const s = estado.sesion;
  const partes = [s.consulta_id ? `Diagnóstico #${s.consulta_id}` : 'Diagnóstico sin guardar'];
  if (s.datos && s.datos.incidente) partes.push(`${s.datos.incidente} · ronda ${s.ronda}`);
  else if (estado.incidente) partes.push(`${estado.incidente.codigo} · ronda ${estado.incidente.ronda}`);
  if (s.datos && s.datos.equipo) partes.push(`equipo ${s.datos.equipo}`);
  partes.push(`${s.preguntas_respondidas} pregunta(s)`, `${s.respuestas.length} respuesta(s) registrada(s)`);
  partes.push(s.finalizada ? 'guardada en la base de datos' : 'abierta');
  $('#subtitulo-resultado').textContent = partes.join(' · ');

  const acciones = $('#acciones-resultado');
  const botones = [];
  const deIncidente = estado.origen && typeof estado.origen === 'object' ? estado.origen.incidente : null;
  if (estado.origen === 'historial') botones.push(['secundario', '← Volver al historial', () => mostrarVista('historial')]);
  if (deIncidente) botones.push(['secundario', '← Volver al incidente', () => mostrarVista('incidente', deIncidente)]);
  if (s.finalizada) {
    botones.push(['secundario', 'Descargar informe', () => descargarInforme(s.consulta_id)]);
    if (estado.origen === 'nueva') botones.push(['', 'Nuevo diagnóstico', nuevoDiagnostico]);
  } else if (estado.incidente) {
    botones.push(['secundario', '← Seguir preguntando', () => mostrarEtapa('consulta')]);
    botones.push(['exito', `Guardar ronda ${estado.incidente.ronda} en ${estado.incidente.codigo}`, guardarRonda]);
  } else {
    botones.push(['secundario', '← Seguir preguntando', () => mostrarEtapa('consulta')]);
    botones.push(['exito', 'Guardar consulta', guardarConsulta]);
  }
  acciones.innerHTML = '';
  botones.forEach(([clase, texto, fn]) => {
    const b = document.createElement('button');
    b.className = `boton ${clase}`;
    b.textContent = texto;
    b.addEventListener('click', fn);
    acciones.appendChild(b);
  });

  pintarLider(s.top[0]);
  pintarTop();
  pintarDetalle();
}

function pintarLider(r) {
  const caja = $('#tarjeta-lider');
  if (!r) { caja.innerHTML = '<p class="vacio">Sin resultados.</p>'; return; }
  const p = r.principal;
  caja.innerHTML = `
    <div class="porcentaje"><b>${fmtPct(r.probabilidad, 0)}</b><small>peso probabilístico</small></div>
    <div class="cuerpo">
      <div class="insignias">
        <span class="insignia acento">Hipótesis más probable</span>
        <span class="insignia">${esc(r.hipotesis.codigo)} · ${esc(r.hipotesis.dominio)}</span>
        <span class="insignia">FC combinado ${fmtSigno(r.certeza)}</span>
      </div>
      <h2>${esc(r.hipotesis.nombre)}</h2>
      ${p ? `<p>Conclusión (${esc(p.regla)}): ${esc(p.conclusion)}.</p>
        <p class="accion">Acción recomendada: ${esc(p.accion)}</p>
        ${p.riesgo_perdida_datos ? '<p class="riesgo">⚠ Esta acción puede ocasionar pérdida de información: respalde antes de aplicarla.</p>' : ''}` : ''}
    </div>`;
}

function pintarTop() {
  const cont = $('#lista-top');
  cont.innerHTML = estado.sesion.top.map((r, i) => `
    <button class="top-fila ${i === estado.seleccion ? 'activa' : ''}" data-i="${i}" style="--c:${SERIE[i % SERIE.length]}">
      <span class="pos">${r.posicion}.</span><span class="nom">${esc(r.hipotesis.nombre)}</span><span class="pct">${fmtPct(r.probabilidad)}</span>
      <span class="pista"><span style="width:${(r.probabilidad * 100).toFixed(2)}%"></span></span>
      <span class="fc">${esc(r.hipotesis.codigo)} · FC ${fmtSigno(r.certeza)} · previa ${fmtPct(r.hipotesis.probabilidad_previa)}</span>
    </button>`).join('');
  cont.querySelectorAll('.top-fila').forEach((b) => b.addEventListener('click', () => {
    estado.seleccion = Number(b.dataset.i);
    pintarTop();
    pintarDetalle();
  }));
}

function pintarDetalle() {
  const r = estado.sesion.top[estado.seleccion];
  if (!r) return;
  const beta = estado.catalogo ? estado.catalogo.parametros.beta : 5;
  $('#resumen-detalle').textContent = `${r.hipotesis.codigo} · ${r.hipotesis.nombre}. Probabilidad previa ${fmtPct(r.hipotesis.probabilidad_previa)} (global) → `
    + `${fmtPct(r.previa_contextual)} según los síntomas → factor de certeza combinado ${fmtSigno(r.certeza, 3)} → peso ${fmtPct(r.probabilidad)}. `
    + `Cada regla aporta aplicabilidad × grado de cumplimiento × FC del experto; los aportes positivos se combinan con MYCIN y el peso es previa · e^(${beta}·FC), normalizado.`;
  $('#detalle-reglas').innerHTML = r.reglas.map((g) => htmlRegla(g, true)).join('');
}

function simboloCondicion(c) {
  if (c.valor === null || c.valor === undefined) return ['?', 'nose', 'sin dato'];
  const v = `${fmtSigno(c.valor, 1)}${c.deducido ? ` · deducido de ${c.deducido_de}` : ''}`;
  if (c.valor > 0) return ['✔', 'si', v];
  if (c.valor < 0) return ['✖', 'no', v];
  return ['·', 'nose', v];
}

function htmlRegla(g, evaluada, administrable = false) {
  const condiciones = g.condiciones.map((c) => {
    const [sim, clase, texto] = evaluada ? simboloCondicion(c) : ['', '', c.evidencia.codigo];
    return `<div class="condicion"><span class="s ${clase}">${sim}</span><span class="con">${esc(c.conector)}</span>
      <span>${esc(c.evidencia.enunciado)}</span><span class="v">${esc(texto)}</span></div>`;
  }).join('');
  const inactiva = g.activo === false;
  const botones = administrable ? `<span class="acciones-regla">
      <button class="boton secundario pequeno" data-regla="${esc(g.regla)}" data-accion-regla="simular">Simular</button>
      <button class="boton secundario pequeno" data-regla="${esc(g.regla)}" data-accion-regla="editar">Editar</button>
      <button class="boton secundario pequeno" data-regla="${esc(g.regla)}" data-accion-regla="${inactiva ? 'activar' : 'desactivar'}">${inactiva ? 'Activar' : 'Desactivar'}</button>
    </span>` : '';
  return `
    <article class="regla${inactiva ? ' inactiva' : ''}">
      <header><b>${esc(g.regla)}</b><span class="insignia">FC del experto ${fmtPct(g.factor_certeza, 0)}</span>
        ${inactiva ? '<span class="insignia peligro">desactivado</span>' : ''}
        <small>Rama ${esc(g.rama_codigo)} · ${esc(g.rama_nombre)} · v${g.version}</small>${botones}</header>
      ${condiciones}
      <div class="entonces"><span class="con">Then</span>${esc(g.conclusion)}</div>
      <div class="entonces"><span class="con">Acción</span>${esc(g.accion)}${g.riesgo_perdida_datos ? ' <b style="color:var(--peligro)">⚠ riesgo de pérdida de datos</b>' : ''}</div>
      ${evaluada ? `<div class="calculo">aplicabilidad ${fmtNum(g.aplicabilidad)} × grado ${fmtSigno(g.grado)} (${g.cumplidas}/${g.total} confirmadas, ${g.negadas} negadas) × FC ${fmtNum(g.factor_certeza)} = aporte ${fmtSigno(g.aporte, 3)}</div>` : ''}
    </article>`;
}

// ================================================================ base de conocimiento
async function cargarConocimiento() {
  try {
    const datos = await api(`/conocimiento/hipotesis${$('#mostrar-inactivos').checked ? '?todas=1' : ''}`);
    estado.bcCargada = true;
    estado.hipotesis = datos.hipotesis;
    const e = datos.estadisticas;
    $('#indicadores-bc').innerHTML = [
      [e.hipotesis, 'hipótesis'], [e.evidencias, 'evidencias (síntomas y pruebas)'],
      [e.reglas, 'reglas If / And / Then'], [e.filas_granulo, 'filas en la tabla granulo'],
    ].map(([n, t]) => `<div class="indicador"><b>${n}</b><span>${t}</span></div>`).join('');
    pintarHipotesis();
  } catch (err) {
    $('#tabla-hipotesis').innerHTML = `<tr><td class="error-carga">${esc(err.message)}</td></tr>`;
  }
}

function pintarHipotesis() {
  const filtro = $('#filtro-hipotesis').value.trim().toLowerCase();
  const hs = estado.hipotesis.filter((h) => !filtro || `${h.codigo} ${h.nombre} ${h.dominio}`.toLowerCase().includes(filtro));
  const tabla = $('#tabla-hipotesis');
  tabla.innerHTML = `<thead><tr><th>Código</th><th>Hipótesis</th><th>Dominio</th><th>Previa</th><th>Reglas</th><th>FC</th></tr></thead>
    <tbody>${hs.map((h) => `<tr class="clic${h.activo === 0 ? ' inactiva' : ''}${h.id === estado.hipotesisSeleccionada ? ' activa' : ''}" data-id="${h.id}"><td class="mono">${esc(h.codigo)}</td><td>${esc(h.nombre)}${h.activo === 0 ? ' <span class="insignia peligro">desactivada</span>' : ''}</td>
      <td>${esc(h.dominio)}</td><td class="num">${fmtPct(h.probabilidad_previa)}</td><td class="num">${h.reglas}</td>
      <td class="num">${h.fc_min == null ? '—' : Math.round(h.fc_min) === Math.round(h.fc_max) ? `${Math.round(h.fc_min)} %` : `${Math.round(h.fc_min)}–${Math.round(h.fc_max)} %`}</td></tr>`).join('')}</tbody>`;
  tabla.querySelectorAll('tr.clic').forEach((tr) => tr.addEventListener('click', () => verGranulos(Number(tr.dataset.id), tr)));
}

async function verGranulos(id, fila) {
  document.querySelectorAll('#tabla-hipotesis tr.activa').forEach((tr) => tr.classList.remove('activa'));
  if (fila) fila.classList.add('activa');
  estado.hipotesisSeleccionada = id;
  const h = estado.hipotesis.find((x) => x.id === id);
  if (!h) return;
  $('#titulo-granulos').textContent = `Gránulos de ${h.codigo} · ${h.nombre}`;
  $('#acciones-hipotesis').innerHTML = `<button class="boton secundario pequeno" data-hipotesis="${h.id}" data-activa="${h.activo === 0 ? 0 : 1}">${h.activo === 0 ? 'Activar hipótesis' : 'Desactivar hipótesis'}</button>`;
  $('#ayuda-granulos').textContent = 'Consultando la base de conocimiento…';
  try {
    const datos = await api(`/conocimiento/hipotesis/${id}${$('#mostrar-inactivos').checked ? '?todas=1' : ''}`);
    $('#ayuda-granulos').textContent = datos.granulos.length
      ? `${datos.granulos.length} regla(s). Cada condición es una fila de la tabla granulo (orden, conector, peso).`
      : 'Esta hipótesis no tiene gránulos activos. Agréguele uno con «+ Gránulo».';
    $('#lista-granulos').innerHTML = datos.granulos.map((g) => htmlRegla(g, false, true)).join('');
  } catch (e) {
    $('#ayuda-granulos').textContent = '';
    $('#lista-granulos').innerHTML = `<div class="error-carga">${esc(e.message)}</div>`;
  }
}

async function cargarEvidencias(forzar = false) {
  if (estado.evidenciasCargadas && !forzar) return;
  try {
    estado.evidencias = (await api(`/conocimiento/evidencias${$('#mostrar-inactivos').checked ? '?todas=1' : ''}`)).evidencias;
    estado.evidenciasCargadas = true;
    pintarEvidencias();
  } catch (e) {
    $('#tabla-evidencias').innerHTML = `<tr><td class="error-carga">${esc(e.message)}</td></tr>`;
  }
}

function pintarEvidencias() {
  const filtro = $('#filtro-evidencias').value.trim().toLowerCase();
  const es = estado.evidencias.filter((e) => !filtro || `${e.codigo} ${e.enunciado} ${e.variable || ''} ${e.tipo}`.toLowerCase().includes(filtro));
  $('#tabla-evidencias').innerHTML = `<thead><tr><th>Código</th><th>Tipo</th><th>Enunciado</th><th>Variable</th><th>Polaridad</th><th>Reglas</th><th></th></tr></thead>
    <tbody>${es.map((e) => `<tr class="${e.activo === 0 ? 'inactiva' : ''}"><td class="mono">${esc(e.codigo)}</td><td>${e.tipo === 'SINTOMA' ? 'Síntoma' : 'Prueba'}</td>
      <td>${esc(e.enunciado)}</td><td class="mono">${esc(e.variable || '—')}</td><td class="num">${e.polaridad > 0 ? '+1' : '−1'}</td>
      <td class="num">${e.reglas}</td><td><button class="boton secundario pequeno" data-evidencia="${e.id}" data-activa="${e.activo === 0 ? 0 : 1}">${e.activo === 0 ? 'Activar' : 'Desactivar'}</button></td></tr>`).join('')}</tbody>`;
}

// ================================================================ historial
async function cargarHistorial() {
  const tabla = $('#tabla-historial');
  tabla.innerHTML = '<tr><td class="cargando">Cargando…</td></tr>';
  try {
    const { consultas } = await api('/consultas');
    if (!consultas.length) { tabla.innerHTML = '<tr><td class="vacio">Todavía no hay diagnósticos guardados.</td></tr>'; return; }
    tabla.innerHTML = `<thead><tr><th>#</th><th>Fecha</th><th>Incidente / equipo</th><th>Ronda</th><th>Responsable</th><th>Estado</th><th>Preguntas</th><th>Hipótesis principal</th><th>Peso</th></tr></thead>
      <tbody>${consultas.map((c) => `<tr class="clic" data-id="${c.id}"><td class="num">${c.id}</td><td class="mono">${esc((c.fecha_inicio || '').slice(0, 16))}</td>
        <td>${c.incidente_codigo ? `<span class="mono">${esc(c.incidente_codigo)}</span>` : `${esc(c.equipo_texto || '—')} <small class="ayuda">consulta libre</small>`}</td>
        <td class="num">${c.incidente_id ? c.ronda : '—'}</td><td>${esc(c.administrador || '—')}</td><td><span class="estado ${esc(c.estado)}">${esc(c.estado.replace('_', ' '))}</span></td>
        <td class="num">${c.total_preguntas ?? 0}</td><td>${esc(c.hipotesis_nombre || '—')}</td><td class="num">${c.probabilidad != null ? fmtPct(c.probabilidad) : '—'}</td></tr>`).join('')}</tbody>`;
    tabla.querySelectorAll('tr.clic').forEach((tr) => tr.addEventListener('click', () => abrirConsulta(Number(tr.dataset.id))));
  } catch (e) {
    tabla.innerHTML = `<tr><td class="error-carga">${esc(e.message)}</td></tr>`;
  }
}

async function abrirConsulta(id, origen = 'historial') {
  try {
    if (!estado.catalogo) await cargarCatalogo();
    estado.sesion = await ocupado(api(`/consultas/${id}`));
    estado.origen = origen;
    estado.incidente = null;
    pintarBannerIncidente();
    estado.seleccion = 0;
    mostrarVista('diagnostico');
    pintarResultado();
    mostrarEtapa('resultado');
  } catch (e) { aviso(e.message, true); }
}

// ================================================================ servicio
async function pintarServicio() {
  const url = API || location.origin;
  const dl = $('#datos-servicio');
  try {
    const s = await api('/salud');
    const p = estado.catalogo ? estado.catalogo.parametros : null;
    const filas = [
      ['Estado', '✔ en línea'], ['URL de la API', `${url}/api`], ['Base de datos', s.base_datos],
      ['Base de conocimiento', `${s.estadisticas.hipotesis} hipótesis · ${s.estadisticas.evidencias} evidencias · ${s.estadisticas.reglas} reglas`],
    ];
    if (p) filas.push(['Parámetros del motor', `β = ${p.beta} · umbral ${fmtPct(p.umbral_probabilidad, 0)} · máx. ${p.max_preguntas} preguntas · top ${p.hipotesis_resultado}`]);
    dl.innerHTML = filas.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('');
    $('#tabla-rutas').innerHTML = `<thead><tr><th>Método</th><th>Ruta</th><th>Acceso</th><th>Qué hace</th></tr></thead><tbody>${s.rutas.map((r) => `<tr>
      <td><span class="metodo ${r.metodo.toLowerCase()}">${r.metodo}</span></td><td><code>${esc(r.ruta)}</code></td>
      <td>${r.publica ? 'pública' : 'con sesión'}</td><td>${esc(r.descripcion)}</td></tr>`).join('')}</tbody>`;
  } catch (e) {
    dl.innerHTML = `<dt>Estado</dt><dd style="color:var(--peligro)">${esc(e.message)}</dd><dt>URL de la API</dt><dd>${esc(url)}/api</dd>`;
  }
  const ejemplo = estado.sintomas.size ? [...estado.sintomas] : [79];
  $('#ejemplo-peticion').textContent = `curl -X POST ${url}/api/diagnostico \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer <token de /api/auth/ingresar>" \\
  -d '${JSON.stringify({ sintomas: ejemplo, respuestas: estado.respuestas.length ? estado.respuestas : [] })}'`;
}

// ================================================================ eventos
$('#boton-iniciar').addEventListener('click', iniciar);
$('#boton-limpiar').addEventListener('click', limpiarInicio);
$('#boton-deshacer').addEventListener('click', deshacer);
$('#boton-ver-resultado').addEventListener('click', verResultado);
$('#boton-cancelar').addEventListener('click', () => {
  if (!estado.respuestas.length || confirm('¿Descartar la consulta en curso?')) { estado.respuestas = []; mostrarEtapa('inicio'); }
});
$('#boton-recargar-historial').addEventListener('click', cargarHistorial);
$('#filtro-hipotesis').addEventListener('input', pintarHipotesis);
$('#filtro-evidencias').addEventListener('input', pintarEvidencias);
$('#plegable-evidencias').addEventListener('toggle', (e) => { if (e.target.open) cargarEvidencias(); });
$('#mostrar-inactivos').addEventListener('change', () => {
  estado.bcCargada = false;
  cargarConocimiento().then(() => { if (estado.hipotesisSeleccionada) verGranulos(estado.hipotesisSeleccionada); });
  if ($('#plegable-evidencias').open) cargarEvidencias(true); else estado.evidenciasCargadas = false;
});

document.addEventListener('keydown', (e) => {
  if (!$('#etapa-consulta').classList.contains('activa') || !$('#vista-diagnostico').classList.contains('activa')) return;
  if (e.target.matches('input, textarea') || e.ctrlKey || e.metaKey || e.altKey) return;
  const i = Number(e.key) - 1;
  if (i >= 0 && i < estado.escala.length) { e.preventDefault(); responder(estado.escala[i].codigo); }
});

revisarServicio();
