/* SEDATI · cliente web del sistema experto.
 *
 * Esta página no contiene reglas ni lógica de inferencia: envía los síntomas y las respuestas a la
 * API REST (AWS Lambda + API Gateway) y muestra lo que el motor responde. El servicio no guarda
 * estado entre peticiones, así que el cliente conserva la lista de respuestas y la envía completa.
 *
 * Inicio de sesión: la persona crea su cuenta o ingresa con su correo y su contraseña. El servicio
 * responde un token firmado que viaja en la cabecera «Authorization: Bearer <token>» y que el servicio
 * renueva en cada respuesta; si vence (minutos sin actividad), se vuelve a la pantalla de acceso.
 * Cada diagnóstico guardado queda a nombre de la cuenta. El diagnóstico recorre el árbol de decisión en orden:
 * A. Energía y arranque → B. Video y pantalla → C. Sistema operativo… → G. Software y accesos.
 */
'use strict';

const API = ((window.SEDATI_CONFIG && window.SEDATI_CONFIG.apiUrl) || '').replace(/\/+$/, '');
const SERIE = ['#1F6FEB', '#13A89E', '#F2A541', '#8E6CEF', '#E5646E'];

const estado = {
  usuario: null,           // {id, nombre, correo} de la sesión iniciada
  token: null,             // token de sesión firmado por el servicio
  catalogo: null,
  escala: [],
  arbol: null,             // recorrido del árbol de decisión (ver arbolNuevo)
  categoria: null,         // letra de la categoría en la que se respondió «Sí» (null si se eligió de la lista completa)
  hoja: null,              // nodo del árbol donde terminó el recorrido: {pregunta, causas, pasos}
  respuestasArbol: [],     // [{evidencia_id, escala: 'NO'}] lo que se negó con «No» dentro de la rama
  sintomas: new Set(),     // id de evidencia elegidos como síntomas iniciales
  respuestas: [],          // [{evidencia_id, escala}] en el orden en que se respondieron
  sesion: null,            // última respuesta de la API (estado completo de la consulta)
  seleccion: 0,            // hipótesis seleccionada en la vista de resultado
  porQue: false,           // explicación de la pregunta visible
  origen: 'nueva',         // 'nueva' | 'historial'
  bcCargada: false,
  evidenciasCargadas: false,
  hipotesis: [],
  evidencias: [],
};

// ================================================================ utilidades
const $ = (sel) => document.querySelector(sel);

function esc(texto) {
  return String(texto ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

const fmtPct = (p, dec = 1) => (p ?? 0).toLocaleString('es-CO', { style: 'percent', minimumFractionDigits: dec, maximumFractionDigits: dec });
const fmtNum = (n, dec = 2) => (n ?? 0).toLocaleString('es-CO', { minimumFractionDigits: dec, maximumFractionDigits: dec });
const fmtSigno = (n, dec = 2) => (n > 0 ? '+' : n < 0 ? '−' : '') + fmtNum(Math.abs(n), dec);
const mayuscula = (t) => (t ? t[0].toUpperCase() + t.slice(1) : '');
const minuscula = (t) => (t ? t[0].toLowerCase() + t.slice(1) : '');

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
  if (respuesta.status === 401 && estado.token && !opciones.sinRedirigir) {
    cerrarSesion((datos && datos.error) || 'La sesión venció. Inicia sesión de nuevo.');
  }
  if (!respuesta.ok) throw new Error((datos && datos.error) || `El servicio respondió ${respuesta.status}.`);
  if (datos && datos._sesion) guardarToken(datos._sesion.token);
  return datos;
}

async function ocupado(promesa) {
  document.body.classList.add('ocupado');
  try { return await promesa; } finally { document.body.classList.remove('ocupado'); }
}

// ================================================================ sesión: iniciar sesión / crear cuenta
function guardarToken(token) {
  estado.token = token || null;
  try { if (token) sessionStorage.setItem('sedati_token', token); else sessionStorage.removeItem('sedati_token'); } catch (e) { /* sin almacenamiento */ }
}

function tokenGuardado() {
  try { return sessionStorage.getItem('sedati_token'); } catch (e) { return null; }
}

function fijarUsuario(usuario) {
  estado.usuario = usuario || null;
  const nombre = usuario ? usuario.nombre : '';
  document.body.classList.toggle('sin-sesion', !usuario);
  $('#usuario-nombre').textContent = nombre;
  $('#usuario-correo').textContent = usuario ? usuario.correo : '';
  $('#usuario-iniciales').textContent = nombre.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0].toUpperCase()).join('');
}

function modoAcceso(modo) {
  document.querySelectorAll('.selector-acceso [data-modo]').forEach((b) => {
    const activo = b.dataset.modo === modo;
    b.classList.toggle('activa', activo);
    b.setAttribute('aria-selected', String(activo));
  });
  $('#form-ingresar').hidden = modo !== 'ingresar';
  $('#form-registro').hidden = modo !== 'registro';
  $('#ingresar-error').textContent = '';
  $('#registro-error').textContent = '';
  setTimeout(() => (modo === 'ingresar' ? $('#ingresar-correo') : $('#registro-nombre')).focus(), 30);
}

function sesionIniciada(datos, saludo) {
  guardarToken(datos._sesion.token);
  fijarUsuario(datos.usuario);
  $('#form-ingresar').reset();
  $('#form-registro').reset();
  reiniciarArbol();
  mostrarVista('diagnostico');
  mostrarEtapa('arbol');
  aviso(`${saludo}, ${datos.usuario.nombre.split(' ')[0]}!`);
}

async function ingresar(evento) {
  evento.preventDefault();
  const error = $('#ingresar-error');
  error.textContent = '';
  try {
    const datos = await ocupado(api('/auth/ingresar', { method: 'POST', sinRedirigir: true, body: {
      correo: $('#ingresar-correo').value.trim(), contrasena: $('#ingresar-contrasena').value } }));
    sesionIniciada(datos, '¡Hola');
  } catch (e) {
    error.textContent = e.message;
    $('#ingresar-contrasena').value = '';
    $('#ingresar-contrasena').focus();
  }
}

async function registrarse(evento) {
  evento.preventDefault();
  const error = $('#registro-error');
  error.textContent = '';
  const contrasena = $('#registro-contrasena').value;
  if (contrasena !== $('#registro-confirmacion').value) {
    error.textContent = 'Las contraseñas no coinciden.';
    $('#registro-confirmacion').focus();
    return;
  }
  try {
    const datos = await ocupado(api('/auth/registro', { method: 'POST', sinRedirigir: true, body: {
      nombre: $('#registro-nombre').value.replace(/\s+/g, ' ').trim(), correo: $('#registro-correo').value.trim(), contrasena } }));
    sesionIniciada(datos, '¡Cuenta creada. Bienvenido');
  } catch (e) { error.textContent = e.message; }
}

function cerrarSesion(mensaje) {
  guardarToken(null);
  fijarUsuario(null);
  reiniciarArbol();
  estado.origen = 'nueva';
  modoAcceso('ingresar');
  mostrarVista('bienvenida');
  if (mensaje) $('#ingresar-error').textContent = mensaje;
}

async function restaurarSesion() {
  const token = tokenGuardado();
  if (!token) { cerrarSesion(); return; }
  estado.token = token;
  try {
    const datos = await api('/auth/sesion', { sinRedirigir: true });
    fijarUsuario(datos.usuario);
    mostrarVista('diagnostico');
  } catch (e) {
    cerrarSesion(/venci|válida|sesión/i.test(e.message) ? 'Tu sesión venció. Inicia sesión de nuevo.' : e.message);
  }
}

// ================================================================ navegación
function mostrarVista(nombre) {
  if (nombre !== 'bienvenida' && !estado.usuario) nombre = 'bienvenida';
  document.querySelectorAll('.pestana').forEach((b) => b.classList.toggle('activa', b.dataset.vista === nombre));
  document.querySelectorAll('.vista').forEach((v) => v.classList.toggle('activa', v.id === `vista-${nombre}`));
  if (nombre === 'conocimiento' && !estado.bcCargada) cargarConocimiento();
  if (nombre === 'historial') cargarHistorial();
  if (nombre === 'servicio') pintarServicio();
  window.scrollTo({ top: 0 });
}

function mostrarEtapa(nombre) {
  document.querySelectorAll('.etapa').forEach((e) => e.classList.toggle('activa', e.id === `etapa-${nombre}`));
  window.scrollTo({ top: 0 });
}

// ================================================================ catálogo: árbol de decisión
async function cargarCatalogo() {
  const pill = $('#estado-servicio');
  try {
    const cat = await api('/catalogo');
    estado.catalogo = cat;
    estado.escala = cat.escala;
    pill.className = 'estado-servicio ok';
    pill.querySelector('.texto').textContent = `En línea · ${cat.base_datos}`;
    pill.title = `API: ${API || location.origin}`;
    pintarArbol();
  } catch (e) {
    pill.className = 'estado-servicio error';
    pill.querySelector('.texto').textContent = 'Servicio no disponible';
    pill.title = e.message;
    $('#recorrido').innerHTML = '';
    $('#tarjeta-arbol').innerHTML = `<div class="error-carga"><b>No se pudo cargar el árbol de decisión.</b><br>${esc(e.message)}</div>
      <div class="botones-arbol"><button class="boton secundario" id="boton-reintentar">Reintentar</button></div>`;
    $('#boton-reintentar').addEventListener('click', cargarCatalogo);
  }
}

const categorias = () => (estado.catalogo ? estado.catalogo.categorias : []);

function textoSintoma(id) {
  for (const c of categorias()) {
    for (const r of c.ramas) {
      const s = r.sintomas.find((x) => x.id === id);
      if (s) return mayuscula(s.enunciado);
    }
  }
  return `E-${id}`;
}

// Recorrido del árbol con Sí / No (como la figura del árbol completo):
//   categoría → situación (rama) → detalle → … → hoja (causas)
//   · Sí entra al nodo: si tiene hijos pregunta por el primero; si es una hoja, empieza el motor de inferencia.
//   · No pasa al siguiente nodo del mismo nivel. Si no quedan, sube: siguiente rama o siguiente categoría.
// Cada nodo trae las evidencias de la base que confirma el Sí y las que niega el No; al llegar a la hoja se
// envían al motor (las confirmadas como síntomas iniciales y las negadas como respuestas «No»).
function arbolNuevo() {
  return { indice: 0, fase: 'categoria', respuestas: {}, camino: [], pos: 0, evid: [], pasos: [], historial: [] };
}

function reiniciarArbol() {
  estado.arbol = arbolNuevo();
  estado.categoria = null;
  estado.hoja = null;
  estado.sintomas.clear();
  estado.respuestasArbol = [];
  estado.respuestas = [];
  estado.sesion = null;
  if (estado.catalogo) pintarArbol();
}

function guardarPaso() {
  const { historial, ...resto } = estado.arbol;
  historial.push(JSON.parse(JSON.stringify(resto)));
}

function atrasArbol() {
  const a = estado.arbol;
  if (!a.historial.length) return;
  estado.arbol = Object.assign(a.historial.pop(), { historial: a.historial });
  estado.sintomas.clear();
  pintarArbol();
}

const categoriaActual = () => categorias()[estado.arbol.indice];

function nodoEn(camino) {
  let n = categoriaActual().ramas[camino[0]].nodo;
  for (const k of camino.slice(1)) n = n.hijos[k];
  return n;
}

function hermanos() {
  const a = estado.arbol;
  return a.camino.length ? nodoEn(a.camino).hijos : categoriaActual().ramas.map((r) => r.nodo);
}

function pintarRecorrido() {
  const a = estado.arbol;
  $('#recorrido').innerHTML = categorias().map((c, i) => {
    const r = a.respuestas[c.codigo];
    const actual = (a.fase === 'categoria' || a.fase === 'nodo') && i === a.indice;
    const clase = actual ? (a.fase === 'nodo' ? 'actual si' : 'actual') : r === 'si' ? 'si' : r === 'no' ? 'no' : '';
    const marca = actual ? (a.fase === 'nodo' ? 'Sí · aquí' : '← aquí') : r === 'si' ? 'Sí' : r === 'no' ? 'No' : '';
    return `<li class="${clase}"><span class="letra">${esc(c.codigo)}</span><span>${esc(c.nombre)}</span>
      <span class="marca-paso">${marca}</span></li>`;
  }).join('');
  const caja = $('#camino-arbol');
  caja.innerHTML = a.fase === 'nodo' && a.pasos.length ? `
    <p class="ayuda titulo-camino">Respuestas en ${esc(categoriaActual().codigo)}. ${esc(categoriaActual().nombre)}</p>
    <ol class="camino">${a.pasos.map((p) => `<li class="${p.si ? 'si' : 'no'}" style="--nivel:${p.nivel}">
      <span>${esc(p.pregunta)}</span><b>${p.si ? 'Sí' : 'No'}</b></li>`).join('')}</ol>` : '';
}

function pintarArbol() {
  pintarRecorrido();
  const a = estado.arbol;
  if (a.fase === 'categoria') pintarPreguntaCategoria();
  else if (a.fase === 'nodo') pintarPreguntaNodo();
  else if (a.fase === 'todos') pintarTodas();
  else pintarNinguna();
}

function botonesSiNo(caja, alSi, alNo) {
  caja.querySelector('[data-arbol=si]').addEventListener('click', alSi);
  caja.querySelector('[data-arbol=no]').addEventListener('click', alNo);
  const atras = caja.querySelector('[data-arbol=atras]');
  if (atras) atras.addEventListener('click', atrasArbol);
}

const htmlBotonesSiNo = () => `
    <div class="botones-arbol">
      <button class="boton grande exito" data-arbol="si" title="Tecla S">Sí</button>
      <button class="boton grande secundario" data-arbol="no" title="Tecla N">No</button>
      ${estado.arbol.historial.length ? '<button class="boton grande secundario" data-arbol="atras">← Atrás</button>' : ''}
    </div>`;

function pintarPreguntaCategoria() {
  const a = estado.arbol;
  const cats = categorias();
  const c = cats[a.indice];
  const caja = $('#tarjeta-arbol');
  caja.innerHTML = `
    <p class="paso">Pregunta ${a.indice + 1} de ${cats.length}</p>
    <div class="progreso"><span style="width:${((a.indice) / cats.length) * 100}%"></span></div>
    <p class="pregunta-texto">¿La falla tiene que ver con ${esc(minuscula(c.nombre))}?</p>
    <div class="ejemplos">Por ejemplo:
      <ul>${c.ramas.map((r) => `<li>${esc(mayuscula(r.nombre))}</li>`).join('')}</ul>
    </div>
    ${htmlBotonesSiNo()}`;
  botonesSiNo(caja, () => responderCategoria(true), () => responderCategoria(false));
}

function responderCategoria(si) {
  guardarPaso();
  const a = estado.arbol;
  a.respuestas[categoriaActual().codigo] = si ? 'si' : 'no';
  if (si) {
    Object.assign(a, { fase: 'nodo', camino: [], pos: 0, evid: [], pasos: [] });
  } else {
    siguienteCategoria();
  }
  pintarArbol();
}

function siguienteCategoria() {
  const a = estado.arbol;
  a.respuestas[categoriaActual().codigo] = 'no';
  Object.assign(a, { camino: [], pos: 0, evid: [], pasos: [] });
  if (a.indice < categorias().length - 1) {
    a.indice += 1;
    a.fase = 'categoria';
  } else {
    a.fase = 'ninguna';
  }
}

function pintarPreguntaNodo() {
  const a = estado.arbol;
  const lista = hermanos();
  const nodo = lista[a.pos];
  const c = categoriaActual();
  const migas = [`${c.codigo}. ${c.nombre}`, ...a.camino.map((_, i) => nodoEn(a.camino.slice(0, i + 1)).pregunta)];
  const caja = $('#tarjeta-arbol');
  caja.innerHTML = `
    <p class="paso migas">${migas.map((m) => `<span>${esc(m)}</span>`).join('<i>›</i>')}</p>
    <p class="pregunta-texto">${esc(nodo.pregunta)}</p>
    ${htmlBotonesSiNo()}`;
  botonesSiNo(caja, () => responderNodo(true), () => responderNodo(false));
}

function responderNodo(si) {
  guardarPaso();
  const a = estado.arbol;
  const lista = hermanos();
  const nodo = lista[a.pos];
  a.pasos.push({ pregunta: nodo.pregunta, si, nivel: a.camino.length });
  a.evid.push(...(si ? nodo.si : nodo.no));
  if (si) {
    if (nodo.hijos.length) {
      a.camino.push(a.pos);
      a.pos = 0;
      pintarArbol();
    } else {
      terminarArbol(nodo);
    }
    return;
  }
  a.pos += 1;
  if (a.pos >= lista.length) {
    agotarNivel();
    if (estado.arbol.fase === 'motor') return;
  }
  pintarArbol();
}

// Se respondió No a todas las opciones de un nivel.
function agotarNivel() {
  const a = estado.arbol;
  if (!a.camino.length) { siguienteCategoria(); return; }          // ninguna rama de la categoría
  const padre = nodoEn(a.camino);
  if (a.evid.some((e) => e.escala === 'SI')) { terminarArbol(padre); return; }   // ya hay síntomas: sigue el motor
  // la rama no aportó ningún síntoma: se pasa a la siguiente rama de la categoría
  a.pos = a.camino[0] + 1;
  a.camino = [];
  a.evid = [];
  if (a.pos >= categoriaActual().ramas.length) siguienteCategoria();
}

function causasDe(nodo) {
  return nodo.causas.length ? nodo.causas : nodo.hijos.flatMap(causasDe);
}

async function terminarArbol(nodo) {
  const a = estado.arbol;
  const finales = new Map();
  a.evid.forEach((e) => { finales.delete(e.evidencia_id); finales.set(e.evidencia_id, e.escala); });
  estado.sintomas = new Set([...finales].filter(([, v]) => v === 'SI').map(([id]) => id));
  estado.respuestasArbol = [...finales].filter(([, v]) => v === 'NO').map(([id]) => ({ evidencia_id: id, escala: 'NO' }));
  if (!estado.sintomas.size) {     // por si acaso: los síntomas de entrada de la rama
    categoriaActual().ramas[a.camino[0] ?? a.pos].sintomas.forEach((s) => estado.sintomas.add(s.id));
  }
  estado.hoja = { pregunta: nodo.pregunta, causas: causasDe(nodo), pasos: a.pasos.slice(), categoria: categoriaActual() };
  a.fase = 'motor';
  await iniciar(categoriaActual().codigo);
}

// ---------------------------------------------------------------- sin coincidencia: lista completa
function pintarNinguna() {
  const caja = $('#tarjeta-arbol');
  caja.innerHTML = `
    <p class="paso">Fin del árbol de decisión</p>
    <p class="pregunta-texto">La falla no coincide con ninguna categoría</p>
    <p class="ayuda">Respondiste «No» en las ${categorias().length} categorías. Puedes volver a empezar o elegir
      directamente entre todas las situaciones que conoce el sistema.</p>
    <div class="botones-arbol">
      <button class="boton" data-arbol="todos">Ver todas las situaciones</button>
      <button class="boton secundario" data-arbol="reiniciar">Volver a empezar</button>
      <button class="boton secundario" data-arbol="atras">← Atrás</button>
    </div>`;
  caja.querySelector('[data-arbol=todos]').addEventListener('click', () => {
    guardarPaso();
    estado.arbol.fase = 'todos';
    estado.sintomas.clear();
    pintarArbol();
  });
  caja.querySelector('[data-arbol=reiniciar]').addEventListener('click', reiniciarArbol);
  caja.querySelector('[data-arbol=atras]').addEventListener('click', atrasArbol);
}

function pintarTodas() {
  const caja = $('#tarjeta-arbol');
  caja.innerHTML = `
    <p class="paso">Todas las categorías del árbol</p>
    <p class="pregunta-texto">¿Qué ocurre con el equipo?</p>
    <p class="ayuda">Marca una o más situaciones. Con ellas el motor de inferencia empieza a razonar.</p>
    <div class="ramas">
      ${categorias().map((cat) => cat.ramas.map((r) => `
        <section class="rama">
          <header><span class="codigo">${esc(r.codigo)}</span><b>${esc(mayuscula(r.nombre))}</b></header>
          ${r.sintomas.map((s) => `
            <label class="sintoma">
              <input type="checkbox" value="${s.id}" ${estado.sintomas.has(s.id) ? 'checked' : ''}>
              <span>${esc(mayuscula(s.enunciado))}</span><span class="codigo">${esc(s.codigo)}</span>
            </label>`).join('')}
        </section>`).join('')).join('')}
    </div>
    <div class="pie-arbol">
      <span class="ayuda" id="resumen-sintomas"></span>
      <button class="boton secundario" data-arbol="atras">← Atrás</button>
      <button class="boton" id="boton-iniciar" disabled>Iniciar diagnóstico →</button>
    </div>`;
  caja.querySelectorAll('input[type=checkbox]').forEach((chk) => chk.addEventListener('change', () => {
    const id = Number(chk.value);
    chk.checked ? estado.sintomas.add(id) : estado.sintomas.delete(id);
    resumirSintomas();
  }));
  caja.querySelector('[data-arbol=atras]').addEventListener('click', atrasArbol);
  $('#boton-iniciar').addEventListener('click', () => {
    guardarPaso();
    estado.respuestasArbol = [];
    estado.hoja = null;
    estado.arbol.fase = 'motor';
    iniciar(null);
  });
  resumirSintomas();
}

function resumirSintomas() {
  const n = estado.sintomas.size;
  const boton = $('#boton-iniciar');
  if (boton) boton.disabled = n === 0;
  const resumen = $('#resumen-sintomas');
  if (resumen) {
    resumen.textContent = n
      ? `${n} seleccionada(s): ${[...estado.sintomas].map(textoSintoma).join('; ')}`
      : 'Marca al menos una situación para iniciar.';
  }
}

// Vuelve al árbol desde la consulta: a la última pregunta respondida, para poder cambiarla.
function volverAlArbol() {
  estado.respuestas = [];
  estado.sesion = null;
  if (estado.arbol.fase === 'motor') atrasArbol(); else pintarArbol();
  mostrarEtapa('arbol');
}

// ================================================================ consulta
function cuerpoConsulta() {
  return {
    categoria: estado.categoria || undefined,
    sintomas: [...estado.sintomas],
    respuestas: [...estado.respuestasArbol, ...estado.respuestas],
  };
}

async function diagnosticar() {
  estado.sesion = await ocupado(api('/diagnostico', { method: 'POST', body: cuerpoConsulta() }));
  estado.porQue = false;
  pintarConsulta();
}

async function iniciar(categoria) {
  if (!estado.sintomas.size) return;
  estado.categoria = categoria || null;
  estado.respuestas = [];
  estado.origen = 'nueva';
  try {
    await diagnosticar();
    mostrarEtapa('consulta');
  } catch (e) {
    aviso(e.message, true);
    atrasArbol();
  }
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

function nombreCategoria(codigo) {
  const c = categorias().find((x) => x.codigo === codigo);
  return c ? `${c.codigo}. ${c.nombre}` : codigo;
}

function pintarConsulta() {
  const s = estado.sesion;
  $('#subtitulo-consulta').textContent = `${estado.categoria ? `${nombreCategoria(estado.categoria)} · ` : ''}`
    + `${estado.respuestas.length} pregunta(s) del motor respondida(s) · `
    + `${s.diferencial} hipótesis y ${s.reglas_en_memoria} reglas en el diagnóstico diferencial`;
  $('#boton-deshacer').disabled = estado.respuestas.length === 0;
  pintarPregunta();
  pintarHoja();
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
  // las respuestas «No» del árbol cuentan para el máximo del motor, pero no se numeran como preguntas del motor
  const delArbol = s.preguntas_respondidas - estado.respuestas.length;
  const maximo = Math.max(1, s.maximo_preguntas - Math.max(0, delArbol));
  const avance = Math.min(100, (estado.respuestas.length / maximo) * 100);
  const tipo = q.evidencia.tipo === 'SINTOMA' ? 'síntoma' : 'prueba';
  html += `
    <div class="pregunta-numero"><span>Pregunta ${estado.respuestas.length + 1} del motor${s.motivo_conclusion ? ' (opcional)' : ''}</span>
      <span>${estado.respuestas.length} de ${maximo} como máximo</span></div>
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

// Hasta dónde llegó el recorrido del árbol y qué causas propone la figura para esa hoja.
function pintarHoja() {
  const caja = $('#tarjeta-hoja');
  const h = estado.hoja;
  caja.hidden = !h;
  if (!h) return;
  caja.innerHTML = `
    <h2>Recorrido del árbol de decisión</h2>
    <ol class="camino">
      <li class="si" style="--nivel:0"><span>¿La falla tiene que ver con ${esc(minuscula(h.categoria.nombre))}?</span><b>Sí</b></li>
      ${h.pasos.map((p) => `<li class="${p.si ? 'si' : 'no'}" style="--nivel:${p.nivel + 1}"><span>${esc(p.pregunta)}</span>
        <b>${p.si ? 'Sí' : 'No'}</b></li>`).join('')}
    </ol>
    <p class="ayuda">Posibles causas según el árbol (el motor les asigna el peso con tus respuestas):</p>
    <ul class="causas-hoja">${h.causas.map((c) => `<li>${esc(c)}</li>`).join('')}</ul>`;
}

function pintarRespuestas() {
  const lista = $('#lista-respuestas');
  const rs = estado.sesion.respuestas;
  const delArbol = new Set(estado.respuestasArbol.map((r) => r.evidencia_id));
  const origen = (r) => (r.origen === 'SINTOMA_INICIAL' ? (estado.hoja ? ' · árbol: Sí' : ' · síntoma inicial')
    : delArbol.has(r.evidencia.id) ? ' · árbol: No' : '');
  lista.innerHTML = rs.length ? rs.map((r) => `
    <li><span class="n">${r.orden}</span>
      <span class="t">${esc(mayuscula(r.evidencia.enunciado))} <span class="etiqueta-origen">· ${esc(r.evidencia.codigo)}${origen(r)}</span></span>
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
    aviso(`Diagnóstico #${estado.sesion.consulta_id} guardado a nombre de ${estado.usuario.nombre}.`);
    pintarResultado();
  } catch (e) { aviso(e.message, true); }
}

async function descargarInforme(id) {
  try {
    const datos = await ocupado(api(`/consultas/${id}/informe`));
    const blob = new Blob([datos.informe], { type: 'text/plain;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `informe_diagnostico_${id}.txt`;
    a.click();
    URL.revokeObjectURL(a.href);
  } catch (e) { aviso(e.message, true); }
}

function nuevoDiagnostico() {
  reiniciarArbol();
  mostrarVista('diagnostico');
  mostrarEtapa('arbol');
}

function pintarResultado() {
  const s = estado.sesion;
  const partes = [s.consulta_id ? `Diagnóstico #${s.consulta_id}` : 'Diagnóstico sin guardar'];
  if (s.nombre) partes.push(`consultó ${s.nombre}`);
  if (s.categoria) partes.push(nombreCategoria(s.categoria));
  partes.push(`${s.preguntas_respondidas} pregunta(s)`, `${s.respuestas.length} respuesta(s) registrada(s)`);
  partes.push(s.finalizada ? 'guardado en la base de datos' : 'abierto');
  $('#subtitulo-resultado').textContent = partes.join(' · ');

  const acciones = $('#acciones-resultado');
  const botones = [];
  if (estado.origen === 'historial') botones.push(['secundario', '← Volver al historial', () => mostrarVista('historial')]);
  if (s.finalizada) {
    botones.push(['secundario', 'Descargar informe', () => descargarInforme(s.consulta_id)]);
    botones.push(['', 'Nuevo diagnóstico', nuevoDiagnostico]);
  } else {
    botones.push(['secundario', '← Seguir preguntando', () => mostrarEtapa('consulta')]);
    botones.push(['exito', 'Guardar diagnóstico', guardarConsulta]);
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

function htmlRegla(g, evaluada) {
  const condiciones = g.condiciones.map((c) => {
    const [sim, clase, texto] = evaluada ? simboloCondicion(c) : ['', '', c.evidencia.codigo];
    return `<div class="condicion"><span class="s ${clase}">${sim}</span><span class="con">${esc(c.conector)}</span>
      <span>${esc(c.evidencia.enunciado)}</span><span class="v">${esc(texto)}</span></div>`;
  }).join('');
  return `
    <article class="regla">
      <header><b>${esc(g.regla)}</b><span class="insignia">FC del experto ${fmtPct(g.factor_certeza, 0)}</span>
        <small>Rama ${esc(g.rama_codigo)} · ${esc(g.rama_nombre)} · v${g.version}</small></header>
      ${condiciones}
      <div class="entonces"><span class="con">Then</span>${esc(g.conclusion)}</div>
      <div class="entonces"><span class="con">Acción</span>${esc(g.accion)}${g.riesgo_perdida_datos ? ' <b style="color:var(--peligro)">⚠ riesgo de pérdida de datos</b>' : ''}</div>
      ${evaluada ? `<div class="calculo">aplicabilidad ${fmtNum(g.aplicabilidad)} × grado ${fmtSigno(g.grado)} (${g.cumplidas}/${g.total} confirmadas, ${g.negadas} negadas) × FC ${fmtNum(g.factor_certeza)} = aporte ${fmtSigno(g.aporte, 3)}</div>` : ''}
    </article>`;
}

// ================================================================ base de conocimiento (consulta)
async function cargarConocimiento() {
  try {
    const datos = await api('/conocimiento/hipotesis');
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
    <tbody>${hs.map((h) => `<tr class="clic" data-id="${h.id}"><td class="mono">${esc(h.codigo)}</td><td>${esc(h.nombre)}</td>
      <td>${esc(h.dominio)}</td><td class="num">${fmtPct(h.probabilidad_previa)}</td><td class="num">${h.reglas}</td>
      <td class="num">${h.fc_min == null ? '—' : Math.round(h.fc_min) === Math.round(h.fc_max) ? `${Math.round(h.fc_min)} %` : `${Math.round(h.fc_min)}–${Math.round(h.fc_max)} %`}</td></tr>`).join('')}</tbody>`;
  tabla.querySelectorAll('tr.clic').forEach((tr) => tr.addEventListener('click', () => verGranulos(Number(tr.dataset.id), tr)));
}

async function verGranulos(id, fila) {
  document.querySelectorAll('#tabla-hipotesis tr.activa').forEach((tr) => tr.classList.remove('activa'));
  fila.classList.add('activa');
  const h = estado.hipotesis.find((x) => x.id === id);
  $('#titulo-granulos').textContent = `Gránulos de ${h.codigo} · ${h.nombre}`;
  $('#ayuda-granulos').textContent = 'Consultando la base de conocimiento…';
  try {
    const datos = await api(`/conocimiento/hipotesis/${id}`);
    $('#ayuda-granulos').textContent = `${datos.granulos.length} regla(s). Cada condición es una fila de la tabla granulo (orden, conector, peso).`;
    $('#lista-granulos').innerHTML = datos.granulos.map((g) => htmlRegla(g, false)).join('');
  } catch (e) {
    $('#ayuda-granulos').textContent = '';
    $('#lista-granulos').innerHTML = `<div class="error-carga">${esc(e.message)}</div>`;
  }
}

async function cargarEvidencias() {
  if (estado.evidenciasCargadas) return;
  try {
    estado.evidencias = (await api('/conocimiento/evidencias')).evidencias;
    estado.evidenciasCargadas = true;
    pintarEvidencias();
  } catch (e) {
    $('#tabla-evidencias').innerHTML = `<tr><td class="error-carga">${esc(e.message)}</td></tr>`;
  }
}

function pintarEvidencias() {
  const filtro = $('#filtro-evidencias').value.trim().toLowerCase();
  const es = estado.evidencias.filter((e) => !filtro || `${e.codigo} ${e.enunciado} ${e.variable || ''} ${e.tipo}`.toLowerCase().includes(filtro));
  $('#tabla-evidencias').innerHTML = `<thead><tr><th>Código</th><th>Tipo</th><th>Enunciado</th><th>Variable</th><th>Polaridad</th><th>Reglas</th></tr></thead>
    <tbody>${es.map((e) => `<tr><td class="mono">${esc(e.codigo)}</td><td>${e.tipo === 'SINTOMA' ? 'Síntoma' : 'Prueba'}</td>
      <td>${esc(e.enunciado)}</td><td class="mono">${esc(e.variable || '—')}</td><td class="num">${e.polaridad > 0 ? '+1' : '−1'}</td>
      <td class="num">${e.reglas}</td></tr>`).join('')}</tbody>`;
}

// ================================================================ historial
async function cargarHistorial() {
  const tabla = $('#tabla-historial');
  tabla.innerHTML = '<tr><td class="cargando">Cargando…</td></tr>';
  try {
    const { consultas } = await api('/consultas');
    if (!consultas.length) {
      tabla.innerHTML = '<tr><td class="vacio">Todavía no has guardado diagnósticos con tu cuenta.</td></tr>';
      return;
    }
    tabla.innerHTML = `<thead><tr><th>#</th><th>Fecha</th><th>Consultó</th><th>Categoría</th><th>Estado</th><th>Preguntas</th><th>Hipótesis principal</th><th>Peso</th></tr></thead>
      <tbody>${consultas.map((c) => `<tr class="clic" data-id="${c.id}"><td class="num">${c.id}</td><td class="mono">${esc((c.fecha_inicio || '').slice(0, 16))}</td>
        <td>${esc(c.nombre_usuario || '—')}</td><td>${c.categoria_codigo ? esc(nombreCategoria(c.categoria_codigo)) : '—'}</td>
        <td><span class="estado ${esc(c.estado)}">${esc(c.estado.replace('_', ' '))}</span></td>
        <td class="num">${c.total_preguntas ?? 0}</td><td>${esc(c.hipotesis_nombre || '—')}</td><td class="num">${c.probabilidad != null ? fmtPct(c.probabilidad) : '—'}</td></tr>`).join('')}</tbody>`;
    tabla.querySelectorAll('tr.clic').forEach((tr) => tr.addEventListener('click', () => abrirConsulta(Number(tr.dataset.id))));
  } catch (e) {
    tabla.innerHTML = `<tr><td class="error-carga">${esc(e.message)}</td></tr>`;
  }
}

async function abrirConsulta(id) {
  try {
    estado.hoja = null;
    estado.respuestasArbol = [];
    estado.sesion = await ocupado(api(`/consultas/${id}`));
    estado.origen = 'historial';
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
    $('#tabla-rutas').innerHTML = `<thead><tr><th>Método</th><th>Ruta</th><th>Qué hace</th></tr></thead><tbody>${s.rutas.map((r) => `<tr>
      <td><span class="metodo ${r.metodo.toLowerCase()}">${r.metodo}</span></td><td><code>${esc(r.ruta)}</code>${r.requiere_sesion ? '<span class="metodo-candado" title="Requiere sesión">🔒</span>' : ''}</td>
      <td>${esc(r.descripcion)}</td></tr>`).join('')}</tbody>`;
  } catch (e) {
    dl.innerHTML = `<dt>Estado</dt><dd style="color:var(--peligro)">${esc(e.message)}</dd><dt>URL de la API</dt><dd>${esc(url)}/api</dd>`;
  }
  const ejemplo = { categoria: estado.categoria || 'A',
    sintomas: estado.sintomas.size ? [...estado.sintomas] : [1], respuestas: estado.respuestas };
  $('#ejemplo-peticion').textContent = `# 1) Iniciar sesión: la respuesta trae el token en _sesion.token
curl -X POST ${url}/api/auth/ingresar \\
  -H "Content-Type: application/json" \\
  -d '{"correo": "usuario@sedati.example", "contrasena": "Sedati2026*"}'

# 2) Diagnosticar con el token
curl -X POST ${url}/api/diagnostico \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer <token>" \\
  -d '${JSON.stringify(ejemplo)}'`;
}

// ================================================================ eventos
document.querySelectorAll('.pestana').forEach((b) => b.addEventListener('click', () => mostrarVista(b.dataset.vista)));
$('#form-ingresar').addEventListener('submit', ingresar);
$('#form-registro').addEventListener('submit', registrarse);
document.querySelectorAll('.selector-acceso [data-modo]').forEach((b) => b.addEventListener('click', () => modoAcceso(b.dataset.modo)));
$('#boton-salir').addEventListener('click', () => {
  if (!estado.respuestas.length || confirm('Hay una consulta en curso sin guardar. ¿Cerrar sesión de todos modos?')) {
    cerrarSesion();
    aviso('Sesión cerrada.');
  }
});
$('#boton-deshacer').addEventListener('click', deshacer);
$('#boton-ver-resultado').addEventListener('click', verResultado);
$('#boton-cancelar').addEventListener('click', () => {
  if (!estado.respuestas.length || confirm('Se descartarán las respuestas dadas al motor. ¿Volver al árbol?')) volverAlArbol();
});
$('#boton-recargar-historial').addEventListener('click', cargarHistorial);
$('#filtro-hipotesis').addEventListener('input', pintarHipotesis);
$('#filtro-evidencias').addEventListener('input', pintarEvidencias);
$('#plegable-evidencias').addEventListener('toggle', (e) => { if (e.target.open) cargarEvidencias(); });

document.addEventListener('keydown', (e) => {
  if (!$('#vista-diagnostico').classList.contains('activa')) return;
  if (e.target.matches('input, textarea') || e.ctrlKey || e.metaKey || e.altKey) return;
  const fase = estado.arbol && estado.arbol.fase;
  if ($('#etapa-arbol').classList.contains('activa') && (fase === 'categoria' || fase === 'nodo') && estado.catalogo) {
    if (document.body.classList.contains('ocupado')) return;
    const tecla = e.key.toLowerCase();
    const responderArbol = fase === 'categoria' ? responderCategoria : responderNodo;
    if (tecla === 's') { e.preventDefault(); responderArbol(true); }
    if (tecla === 'n') { e.preventDefault(); responderArbol(false); }
    return;
  }
  if (!$('#etapa-consulta').classList.contains('activa')) return;
  const i = Number(e.key) - 1;
  if (i >= 0 && i < estado.escala.length) { e.preventDefault(); responder(estado.escala[i].codigo); }
});

// ================================================================ arranque
estado.arbol = arbolNuevo();
fijarUsuario(null);
mostrarVista('bienvenida');
restaurarSesion();
cargarCatalogo();
