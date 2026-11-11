/* SEDATI · procesos transaccionales en la web.
 *
 *   RF-01  ingreso, sesión con vencimiento por inactividad, cambio de contraseña y gestión de cuentas
 *   RF-02  reporte de incidentes, bandeja con filtros, citas, rondas de diagnóstico ligadas al incidente,
 *          decisión sobre las hipótesis, solución aplicada, escalamiento, historial por equipo e indicadores
 *   RF-03  altas, cambios, activación y simulación de hipótesis, evidencias y gránulos
 *
 * El menú se arma según el rol, pero quien decide es el servidor: cada ruta valida el permiso.
 */
'use strict';

const MINUTOS_INACTIVIDAD = 15;
const PESTANAS = {
  ADMINISTRADOR: [['incidentes', 'Incidentes'], ['citas', 'Agenda'], ['diagnostico', 'Diagnóstico'],
    ['conocimiento', 'Base de conocimiento'], ['historial', 'Historial'], ['indicadores', 'Indicadores'],
    ['usuarios', 'Usuarios'], ['servicio', 'Servicio']],
  SOLICITANTE: [['incidentes', 'Mis incidentes'], ['citas', 'Mis citas']],
};
const NOMBRE_ESTADO = { ABIERTO: 'Abierto', EN_DIAGNOSTICO: 'En diagnóstico', ESCALADO: 'Escalado', CERRADO: 'Cerrado',
  PROGRAMADA: 'Programada', ATENDIDA: 'Atendida', CANCELADA: 'Cancelada', NO_ASISTIO: 'No asistió',
  PROPUESTA: 'Propuesta', CONFIRMADA: 'Confirmada', DESCARTADA: 'Descartada', SOLUCIONADO: 'Solucionado',
  NO_SOLUCIONADO: 'No solucionado' };
const DOMINIOS = ['Hardware', 'Sistema operativo', 'Periféricos', 'Red', 'Software', 'Accesos'];

const atencion = { catalogos: null, filtros: {}, incidenteActual: null, ramas: null, evidenciasBC: null };

const fecha = (t) => (t ? String(t).slice(0, 16) : '—');
const chip = (e) => `<span class="chip ${esc(e)}">${esc(NOMBRE_ESTADO[e] || e)}</span>`;
const vacio = (texto, columnas = 1) => `<tr><td class="vacio" colspan="${columnas}">${esc(texto)}</td></tr>`;
const valorLocal = (d) => {
  const z = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())}T${z(d.getHours())}:${z(d.getMinutes())}`;
};

function descargar(nombre, contenido, tipo) {
  const blob = new Blob([contenido], { type: tipo });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = nombre;
  a.click();
  URL.revokeObjectURL(a.href);
}

// ================================================================ diálogo genérico
function abrirDialogo({ titulo, cuerpo, botones, alAbrir, ancho }) {
  const d = $('#dialogo');
  $('#dialogo-titulo').textContent = titulo;
  $('#dialogo-cuerpo').innerHTML = cuerpo;
  $('#dialogo-error').textContent = '';
  d.classList.toggle('ancho', !!ancho);
  const pie = $('#dialogo-pie');
  pie.innerHTML = '';
  const todos = [{ texto: 'Cancelar', clase: 'secundario', cerrar: true }, ...(botones || [])];
  todos.forEach((b) => {
    const el = document.createElement('button');
    el.type = 'button';
    el.className = `boton ${b.clase || ''}`;
    el.textContent = b.texto;
    el.addEventListener('click', async () => {
      if (b.cerrar) { d.close(); return; }
      const form = $('#dialogo-form');
      if (b.validar !== false && !form.reportValidity()) return;
      $('#dialogo-error').textContent = '';
      el.disabled = true;
      try {
        const seguir = await b.accion(new FormData(form), form);
        if (seguir !== false) d.close();
      } catch (e) {
        $('#dialogo-error').textContent = e.message;
      } finally { el.disabled = false; }
    });
    pie.appendChild(el);
  });
  if (alAbrir) alAbrir($('#dialogo-cuerpo'));
  d.showModal();
}

function mostrarClave(titulo, mensaje, clave) {
  abrirDialogo({
    titulo,
    cuerpo: `<p>${esc(mensaje)}</p><p class="clave-temporal"><code>${esc(clave)}</code></p>
      <p class="ayuda">Entréguela por un medio seguro. Solo se muestra esta vez; el sistema guarda únicamente su hash
      y pedirá cambiarla en el primer ingreso.</p>`,
    botones: [{ texto: 'Copiar', clase: 'secundario', validar: false,
      accion: async () => { try { await navigator.clipboard.writeText(clave); aviso('Contraseña copiada.'); } catch (e) { /* sin portapapeles */ } return false; } }],
  });
}

// ================================================================ acceso y sesión (RF-01)
let temporizadorInactividad;
function reiniciarInactividad() {
  clearTimeout(temporizadorInactividad);
  if (!estado.usuario) return;
  temporizadorInactividad = setTimeout(() => cerrarSesion('La sesión se cerró tras 15 minutos de inactividad.'),
    MINUTOS_INACTIVIDAD * 60 * 1000);
}

function armarPestanas() {
  const nav = $('#pestanas');
  nav.innerHTML = (PESTANAS[estado.usuario.rol] || []).map(([v, t]) =>
    `<button class="pestana" data-vista="${v}">${esc(t)}</button>`).join('');
  nav.querySelectorAll('.pestana').forEach((b) => b.addEventListener('click', () => mostrarVista(b.dataset.vista)));
}

function aplicarRol() {
  document.querySelectorAll('[data-solo]').forEach((el) => { el.hidden = el.dataset.solo !== estado.usuario.rol; });
}

async function iniciarSesion(usuario) {
  estado.usuario = usuario;
  document.body.classList.remove('sin-sesion');
  $('#usuario-actual').hidden = false;
  $('#usuario-nombre').textContent = usuario.nombre;
  $('#usuario-rol').textContent = usuario.rol === 'ADMINISTRADOR' ? 'Administrador' : 'Solicitante';
  $('#usuario-iniciales').textContent = usuario.nombre.split(/\s+/).map((p) => p[0]).slice(0, 2).join('').toUpperCase();
  armarPestanas();
  aplicarRol();
  reiniciarInactividad();
  try { atencion.catalogos = await api('/catalogos'); } catch (e) { atencion.catalogos = null; }
  mostrarVista('incidentes');
  if (usuario.debe_cambiar_contrasena) dialogoContrasena(true);
}

function cerrarSesion(motivo) {
  clearTimeout(temporizadorInactividad);
  guardarToken(null);
  estado.usuario = null;
  estado.catalogo = null;
  estado.bcCargada = false;
  estado.evidenciasCargadas = false;
  estado.incidente = null;
  estado.sesion = null;
  atencion.ramas = null;
  atencion.evidenciasBC = null;
  document.body.classList.add('sin-sesion');
  $('#usuario-actual').hidden = true;
  $('#pestanas').innerHTML = '';
  if ($('#dialogo').open) $('#dialogo').close();
  document.querySelectorAll('.vista').forEach((v) => v.classList.toggle('activa', v.id === 'vista-acceso'));
  $('#acceso-error').textContent = motivo || '';
  $('#acceso-clave').value = '';
}

async function ingresar(ev) {
  ev.preventDefault();
  $('#acceso-error').textContent = '';
  const boton = $('#boton-ingresar');
  boton.disabled = true;
  try {
    const r = await api('/auth/ingresar', { method: 'POST',
      body: { correo: $('#acceso-correo').value.trim(), contrasena: $('#acceso-clave').value } });
    await iniciarSesion(r.usuario);
  } catch (e) {
    $('#acceso-error').textContent = e.message;
  } finally { boton.disabled = false; }
}

function dialogoContrasena(obligatorio = false) {
  if (obligatorio) {
    // la contraseña temporal se cambia sí o sí: cerrar el diálogo sin cambiarla cierra la sesión
    $('#dialogo').addEventListener('close', () => {
      if (estado.usuario && estado.usuario.debe_cambiar_contrasena) cerrarSesion('Debe cambiar su contraseña temporal para usar el sistema.');
    }, { once: true });
  }
  abrirDialogo({
    titulo: obligatorio ? 'Cambie su contraseña temporal' : 'Cambiar contraseña',
    cuerpo: `${obligatorio ? '<p class="ayuda">Es su primer ingreso o un administrador restableció la contraseña. Defina una nueva para continuar.</p>' : ''}
      <label>Contraseña actual<input name="actual" type="password" required autocomplete="current-password"></label>
      <label>Nueva contraseña<input name="nueva" type="password" required minlength="8" autocomplete="new-password"></label>
      <label>Repita la nueva contraseña<input name="repetida" type="password" required minlength="8" autocomplete="new-password"></label>
      <p class="ayuda">Mínimo 8 caracteres, con letras y números.</p>`,
    botones: [{ texto: 'Guardar', accion: async (f) => {
      if (f.get('nueva') !== f.get('repetida')) throw new Error('Las dos contraseñas nuevas no coinciden.');
      await api('/auth/contrasena', { method: 'POST', body: { actual: f.get('actual'), nueva: f.get('nueva') } });
      estado.usuario.debe_cambiar_contrasena = false;
      aviso('Contraseña actualizada.');
    } }],
  });
}

// ================================================================ incidentes (RF-02)
function filtrosIncidentes() {
  if (!esAdmin()) return '';
  const f = new FormData($('#filtros-incidentes'));
  const q = new URLSearchParams();
  for (const [k, v] of f.entries()) if (v) q.set(k, v);
  const t = q.toString();
  return t ? `?${t}` : '';
}

async function cargarIncidentes() {
  const admin = esAdmin();
  $('#titulo-incidentes').textContent = admin ? 'Incidentes' : 'Mis incidentes';
  $('#subtitulo-incidentes').textContent = admin
    ? 'Bandeja de atención. Tome un incidente, programe la cita, diagnostíquelo con el motor y registre la solución.'
    : 'Reporte una falla de su equipo y siga el estado de la atención. Solo usted ve sus incidentes.';
  const tabla = $('#tabla-incidentes');
  tabla.innerHTML = vacio('Cargando…');
  try {
    const { incidentes } = await api(`/incidentes${filtrosIncidentes()}`);
    const cuenta = { ABIERTO: 0, EN_DIAGNOSTICO: 0, ESCALADO: 0, CERRADO: 0 };
    incidentes.forEach((i) => { cuenta[i.estado] += 1; });
    $('#resumen-estados').innerHTML = Object.entries(cuenta).map(([e, n]) =>
      `<div class="resumen-estado ${e}"><b>${n}</b><span>${esc(NOMBRE_ESTADO[e])}</span></div>`).join('');
    if (!incidentes.length) {
      tabla.innerHTML = vacio(admin ? 'No hay incidentes con esos filtros.' : 'Todavía no ha reportado incidentes. Use «+ Reportar incidente».');
      return;
    }
    tabla.innerHTML = `<thead><tr><th>Incidente</th><th>Estado</th>${admin ? '<th>Cat.</th>' : ''}<th>Equipo</th><th>Ubicación</th>
      ${admin ? '<th>Solicitante</th>' : ''}<th>Responsable</th><th>Apertura</th><th>Próxima cita</th>${admin ? '<th>Rondas</th>' : ''}</tr></thead>
      <tbody>${incidentes.map((i) => `<tr class="clic" data-id="${i.id}"><td class="mono">${esc(i.codigo)}</td><td>${chip(i.estado)}</td>
        ${admin ? `<td class="num">${esc(i.categoria_codigo || '—')}</td>` : ''}<td><span class="mono">${esc(i.inventario)}</span><br><small class="ayuda">${esc(i.tipo_equipo)}</small></td>
        <td>${esc(i.ubicacion)}</td>${admin ? `<td>${esc(i.solicitante)}</td>` : ''}<td>${i.administrador ? esc(i.administrador) : '<span class="ayuda">Sin asignar</span>'}</td>
        <td class="mono">${fecha(i.fecha_apertura)}</td><td class="mono">${fecha(i.proxima_cita)}</td>${admin ? `<td class="num">${i.rondas}</td>` : ''}</tr>`).join('')}</tbody>`;
    tabla.querySelectorAll('tr.clic').forEach((tr) => tr.addEventListener('click', () => mostrarVista('incidente', Number(tr.dataset.id))));
  } catch (e) { tabla.innerHTML = `<tr><td class="error-carga">${esc(e.message)}</td></tr>`; }
}

function opciones(lista, valor, vacioTexto) {
  return `${vacioTexto ? `<option value="">${esc(vacioTexto)}</option>` : ''}${lista.map((o) =>
    `<option value="${esc(o.id)}" ${String(o.id) === String(valor) ? 'selected' : ''}>${esc(o.nombre)}</option>`).join('')}`;
}

function dialogoReportar() {
  const c = atencion.catalogos || { tipos_equipo: [], dependencias: [] };
  abrirDialogo({
    titulo: 'Reportar incidente',
    cuerpo: `<div class="rejilla-form">
        <label>Código de inventario *<input name="inventario" required minlength="3" maxlength="20" placeholder="PC-SALA2-014" pattern="[A-Za-z0-9][A-Za-z0-9\\-]{2,19}"></label>
        <label>Tipo de equipo<select name="tipo_equipo_id">${opciones(c.tipos_equipo, '', 'Elija si el equipo es nuevo')}</select></label>
        <label>Marca<input name="marca" maxlength="60"></label>
        <label>Modelo<input name="modelo" maxlength="60"></label>
        <label>Dependencia<select name="dependencia_id">${opciones(c.dependencias, '', '—')}</select></label>
        <label>Ubicación *<input name="ubicacion" required minlength="3" maxlength="100" placeholder="Sala de cómputo 2, puesto 14"></label>
      </div>
      <label>Descripción de la falla *<textarea name="descripcion" rows="4" required minlength="10" maxlength="2000" placeholder="Qué pasa, desde cuándo, qué mensaje aparece…"></textarea></label>
      <p class="ayuda">Si el equipo ya está en el inventario basta con su código; tipo, marca y modelo solo se piden para registrar un equipo nuevo.</p>`,
    botones: [{ texto: 'Reportar', accion: async (f) => {
      const r = await api('/incidentes', { method: 'POST', body: Object.fromEntries(f.entries()) });
      aviso(`Incidente ${r.incidente.codigo} reportado. Un administrador lo atenderá.`);
      mostrarVista('incidente', r.incidente.id);
    } }],
  });
}

// ---------------------------------------------------------------- detalle
async function cargarIncidente(id) {
  if (!id) id = atencion.incidenteActual;
  atencion.incidenteActual = id;
  ['#tarjeta-datos-incidente', '#tarjeta-citas', '#tarjeta-historial-estados', '#tarjeta-rondas', '#tarjeta-intervenciones']
    .forEach((s) => { $(s).innerHTML = '<div class="cargando">Cargando…</div>'; });
  $('#acciones-incidente').innerHTML = '';
  try {
    const d = await api(`/incidentes/${id}`);
    pintarIncidente(d);
  } catch (e) {
    $('#tarjeta-datos-incidente').innerHTML = `<div class="error-carga">${esc(e.message)}</div>`;
  }
}

function pintarIncidente(d) {
  const i = d.incidente;
  const admin = esAdmin();
  const abierto = i.estado === 'ABIERTO' || i.estado === 'EN_DIAGNOSTICO';
  $('#titulo-incidente').innerHTML = `${esc(i.codigo)} ${chip(i.estado)}`;
  $('#subtitulo-incidente').textContent = `${i.inventario} · ${i.ubicacion} · reportado el ${fecha(i.fecha_apertura)} por ${i.solicitante}`;
  // acciones según rol y estado
  const acciones = [];
  if (admin && abierto) {
    if (i.administrador_id !== estado.usuario.id) acciones.push(['secundario', i.administrador_id ? 'Asumir' : 'Tomar incidente', () => tomar(i)]);
    acciones.push(['secundario', 'Programar cita', () => dialogoCita(i)]);
    if (i.estado === 'EN_DIAGNOSTICO') acciones.push(['secundario', 'Escalar', () => dialogoEscalar(i)]);
    acciones.push(['', `Iniciar ronda ${(d.rondas || []).length + 1} de diagnóstico`, () => iniciarRondaIncidente(i.id).catch((e) => aviso(e.message, true))]);
  } else if (!admin && abierto && i.administrador_id) {
    acciones.push(['', 'Programar cita', () => dialogoCita(i)]);
  }
  const caja = $('#acciones-incidente');
  caja.innerHTML = '';
  acciones.forEach(([clase, texto, fn]) => {
    const b = document.createElement('button');
    b.className = `boton ${clase}`;
    b.textContent = texto;
    b.addEventListener('click', fn);
    caja.appendChild(b);
  });
  // datos
  const e = d.equipo || {};
  const filas = [['Estado', chip(i.estado)], ['Responsable', i.administrador ? esc(i.administrador) : '<span class="ayuda">Sin asignar</span>'],
    ['Equipo', `<span class="mono">${esc(i.inventario)}</span> · ${esc(e.tipo_nombre || i.tipo_equipo)}${e.marca ? ` · ${esc(e.marca)} ${esc(e.modelo || '')}` : ''}`],
    ['Ubicación', esc(i.ubicacion)], ['Solicitante', esc(i.solicitante)],
    ['Categoría del árbol', esc(i.categoria_codigo || 'Se fija con el diagnóstico')],
    ['Apertura', fecha(i.fecha_apertura)], ['Cierre', fecha(i.fecha_cierre)]];
  $('#tarjeta-datos-incidente').innerHTML = `<h2>Datos del incidente</h2><dl class="datos">${filas.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('')}</dl>
    <h3>Descripción de la falla</h3><p class="descripcion">${esc(i.descripcion)}</p>
    ${!admin && !i.administrador_id && abierto ? '<p class="nota">Su incidente está en la bandeja de soporte. Cuando un administrador lo tome, podrá programar la cita.</p>' : ''}
    ${i.estado === 'CERRADO' ? '<p class="nota">El incidente está cerrado y no admite cambios. Si la falla reaparece, reporte un incidente nuevo: quedará en el historial del mismo equipo.</p>' : ''}`;
  pintarCitas(d.citas, i);
  $('#tarjeta-historial-estados').innerHTML = `<h2>Historial de estados</h2><ol class="linea-tiempo">${d.historial.map((h) => `
    <li><span class="punto-linea ${esc(h.estado_nuevo)}"></span><div><b>${esc(NOMBRE_ESTADO[h.estado_nuevo])}</b>
      <small>${fecha(h.cambiado_en)} · ${esc(h.usuario || '—')}</small></div></li>`).join('')}</ol>
    <p class="ayuda">Lo registra un disparador de la base de datos en cada cambio de estado; no se puede modificar.</p>`;
  if (admin) { pintarRondas(d, abierto); pintarIntervenciones(d); }
}

function pintarCitas(citas, inc) {
  const admin = esAdmin();
  const caja = $('#tarjeta-citas');
  caja.innerHTML = `<h2>Citas</h2>${citas.length ? `<ul class="citas">${citas.map((c) => `
    <li><div><b class="mono">${fecha(c.inicio)} – ${esc(String(c.fin).slice(11, 16))}</b> ${chip(c.estado)}
      <small>${esc(c.lugar)} · ${esc(c.administrador)}</small></div>
      ${c.estado === 'PROGRAMADA' ? `<span class="acciones-cita">
        <button class="boton secundario pequeno" data-cita="${c.id}" data-accion="reprogramar">Reprogramar</button>
        <button class="boton secundario pequeno" data-cita="${c.id}" data-accion="CANCELADA">Cancelar</button>
        ${admin ? `<button class="boton secundario pequeno" data-cita="${c.id}" data-accion="ATENDIDA">Atendida</button>
        <button class="boton secundario pequeno" data-cita="${c.id}" data-accion="NO_ASISTIO">No asistió</button>` : ''}</span>` : ''}</li>`).join('')}</ul>`
    : '<p class="ayuda">No hay citas programadas.</p>'}`;
  caja.querySelectorAll('[data-cita]').forEach((b) => b.addEventListener('click', () => {
    const cita = citas.find((c) => c.id === Number(b.dataset.cita));
    if (b.dataset.accion === 'reprogramar') dialogoCita(inc, cita);
    else cambiarCita(cita, b.dataset.accion);
  }));
}

async function cambiarCita(cita, estadoNuevo) {
  if (estadoNuevo === 'CANCELADA' && !confirm('¿Cancelar la cita?')) return;
  try {
    await ocupado(api(`/citas/${cita.id}/estado`, { method: 'POST', body: { estado: estadoNuevo } }));
    aviso(`Cita marcada como ${NOMBRE_ESTADO[estadoNuevo].toLowerCase()}.`);
    refrescarVistaActual();
  } catch (e) { aviso(e.message, true); }
}

function dialogoCita(inc, cita) {
  const inicio = cita ? new Date(cita.inicio.replace(' ', 'T')) : new Date(Date.now() + 24 * 3600 * 1000);
  if (!cita) inicio.setMinutes(0, 0, 0);
  const duracion = cita ? Math.round((new Date(cita.fin.replace(' ', 'T')) - inicio) / 60000) : 60;
  abrirDialogo({
    titulo: cita ? `Reprogramar cita de ${inc.codigo || cita.incidente_codigo}` : `Programar cita · ${inc.codigo}`,
    cuerpo: `<div class="rejilla-form">
        <label>Fecha y hora *<input name="inicio" type="datetime-local" required value="${valorLocal(inicio)}"></label>
        <label>Duración<select name="duracion">${[30, 60, 90, 120, 180].map((m) => `<option value="${m}" ${m === duracion ? 'selected' : ''}>${m} minutos</option>`).join('')}</select></label>
      </div>
      <label>Lugar *<input name="lugar" required minlength="3" maxlength="100" value="${esc(cita ? cita.lugar : inc.ubicacion || '')}"></label>
      <p class="ayuda">El sistema rechaza la cita si el administrador responsable ya tiene otra en ese horario.</p>`,
    botones: [{ texto: cita ? 'Reprogramar' : 'Programar', accion: async (f) => {
      const a = new Date(f.get('inicio'));
      const b = new Date(a.getTime() + Number(f.get('duracion')) * 60000);
      const cuerpo = { inicio: f.get('inicio'), fin: valorLocal(b), lugar: f.get('lugar') };
      if (cita) await api(`/citas/${cita.id}`, { method: 'POST', body: cuerpo });
      else await api(`/incidentes/${inc.id}/citas`, { method: 'POST', body: cuerpo });
      aviso(cita ? 'Cita reprogramada.' : 'Cita programada.');
      refrescarVistaActual();
    } }],
  });
}

async function tomar(inc) {
  try {
    await ocupado(api(`/incidentes/${inc.id}/tomar`, { method: 'POST', body: {} }));
    aviso(`Usted es el responsable de ${inc.codigo}.`);
    cargarIncidente(inc.id);
  } catch (e) { aviso(e.message, true); }
}

function pintarRondas(d, abierto) {
  const caja = $('#tarjeta-rondas');
  const rondas = d.rondas || [];
  const intervenidas = new Map((d.intervenciones || []).map((x) => [x.diagnostico_hipotesis_id, x]));
  if (!rondas.length) {
    caja.innerHTML = `<h2>Diagnóstico</h2><p class="ayuda">Todavía no se ha ejecutado el motor de inferencia sobre este incidente.
      ${abierto ? 'Use «Iniciar ronda 1 de diagnóstico».' : ''}</p>`;
    return;
  }
  const ultima = rondas[rondas.length - 1].diagnostico.ronda;
  caja.innerHTML = `<h2>Rondas de diagnóstico</h2>
    ${d.descartadas.length ? `<p class="ayuda">No se volverán a proponer: ${d.descartadas.map((c) => `<span class="mono">${esc(c)}</span>`).join(', ')}.</p>` : ''}
    ${rondas.slice().reverse().map((r) => {
      const dg = r.diagnostico;
      const vigente = abierto && dg.ronda === ultima;
      const hayIntervencion = r.hipotesis.some((h) => intervenidas.has(h.id));
      const conAcciones = vigente && !hayIntervencion;
      return `<section class="ronda${vigente ? ' vigente' : ''}">
        <header><b>Ronda ${dg.ronda}</b><small>${fecha(dg.fecha_inicio)} · ${esc(dg.administrador || '—')} · ${r.respuestas} evidencia(s) · ${dg.total_preguntas} pregunta(s)</small>
          <button class="enlace" data-ver-diagnostico="${dg.id}">Ver razonamiento</button></header>
        <table class="tabla-ronda"><thead><tr><th>#</th><th>Hipótesis</th><th>Peso</th><th>FC</th><th>Gránulo</th><th>Decisión</th>${conAcciones ? '<th></th>' : ''}</tr></thead>
        <tbody>${r.hipotesis.map((h) => {
          const iv = intervenidas.get(h.id);
          let botones = '';
          if (conAcciones && !iv) {
            if (h.estado !== 'CONFIRMADA') botones += `<button class="boton secundario pequeno" data-propuesta="${h.id}" data-decision="CONFIRMADA">Confirmar</button>`;
            if (h.estado !== 'DESCARTADA') botones += `<button class="boton secundario pequeno" data-propuesta="${h.id}" data-decision="DESCARTADA">Descartar</button>`;
            if (h.estado !== 'PROPUESTA') botones += `<button class="enlace" data-propuesta="${h.id}" data-decision="PROPUESTA">Deshacer</button>`;
            if (h.estado === 'CONFIRMADA') botones += `<button class="boton exito pequeno" data-solucion="${h.id}">Registrar solución</button>`;
          }
          return `<tr class="${h.estado}"><td class="num">${h.posicion}</td><td><b>${esc(h.hipotesis_nombre)}</b><br><small class="mono ayuda">${esc(h.hipotesis_codigo)}</small>
            ${h.conclusion ? `<br><small>${esc(h.conclusion)}</small>` : ''}</td>
            <td class="num">${fmtPct(h.probabilidad)}</td><td class="num">${fmtSigno(h.certeza)}</td>
            <td class="mono">${esc(h.granulo_codigo || '—')}${h.granulo_version ? ` v${h.granulo_version}` : ''}${d.riesgos[h.granulo_codigo] ? ' <span title="La acción puede borrar información">⚠</span>' : ''}</td>
            <td>${chip(h.estado)}${iv ? `<br>${chip(iv.resultado)}` : ''}</td>${conAcciones ? `<td class="acciones-fila">${botones}</td>` : ''}</tr>`;
        }).join('')}</tbody></table></section>`;
    }).join('')}`;
  const todas = rondas.flatMap((r) => r.hipotesis);
  caja.querySelectorAll('[data-decision]').forEach((b) => b.addEventListener('click', () => decidir(Number(b.dataset.propuesta), b.dataset.decision)));
  caja.querySelectorAll('[data-solucion]').forEach((b) => b.addEventListener('click', () => {
    dialogoSolucion(d.incidente, todas.find((h) => h.id === Number(b.dataset.solucion)), d.riesgos);
  }));
  caja.querySelectorAll('[data-ver-diagnostico]').forEach((b) => b.addEventListener('click', () => {
    abrirConsulta(Number(b.dataset.verDiagnostico), { incidente: d.incidente.id });
  }));
}

async function decidir(propuestaId, decision) {
  try {
    await ocupado(api(`/propuestas/${propuestaId}/decision`, { method: 'POST', body: { estado: decision } }));
    cargarIncidente();
  } catch (e) { aviso(e.message, true); }
}

function dialogoSolucion(inc, h, riesgos) {
  abrirDialogo({
    titulo: `Registrar solución · ${inc.codigo}`,
    cuerpo: `<p><b>${esc(h.hipotesis_nombre)}</b> (${esc(h.granulo_codigo || '')}): ${esc(h.conclusion || '')}</p>
      ${riesgos[h.granulo_codigo] ? '<p class="riesgo">⚠ La acción recomendada puede ocasionar pérdida de información: respalde los datos del usuario antes de aplicarla.</p>' : ''}
      <label>Acción aplicada *<textarea name="accion_aplicada" rows="3" required minlength="5" maxlength="500">${esc(h.accion || '')}</textarea></label>
      <div class="rejilla-form">
        <label>Tiempo invertido (minutos)<input name="tiempo_min" type="number" min="0" max="1440" value="15"></label>
        <fieldset class="opciones-resultado"><legend>Resultado *</legend>
          <label class="en-linea"><input type="radio" name="resultado" value="SOLUCIONADO" required> Solucionado: cierra el incidente</label>
          <label class="en-linea"><input type="radio" name="resultado" value="NO_SOLUCIONADO"> No solucionado: nueva ronda sin esta hipótesis</label>
        </fieldset>
      </div>
      <label>Observaciones<textarea name="observaciones" rows="2" maxlength="2000"></textarea></label>`,
    botones: [{ texto: 'Registrar', clase: 'exito', accion: async (f) => {
      const r = await api(`/propuestas/${h.id}/intervencion`, { method: 'POST', body: Object.fromEntries(f.entries()) });
      aviso(r.incidente.estado === 'CERRADO' ? `${r.incidente.codigo} quedó cerrado.`
        : 'Solución registrada como no efectiva. Ejecute una nueva ronda de diagnóstico.');
      cargarIncidente();
    } }],
  });
}

function dialogoEscalar(inc) {
  abrirDialogo({
    titulo: `Escalar ${inc.codigo}`,
    cuerpo: `<label>Área de destino *<input name="destino" required minlength="3" maxlength="100" placeholder="Infraestructura de redes, proveedor, nivel 2…"></label>
      <label>Motivo *<textarea name="motivo" rows="4" required minlength="10" maxlength="2000" placeholder="Por qué no se puede resolver en este nivel y qué se probó"></textarea></label>
      <p class="ayuda">El incidente pasa a ESCALADO y ya no admite cambios en este nivel.</p>`,
    botones: [{ texto: 'Escalar', clase: 'peligro', accion: async (f) => {
      await api(`/incidentes/${inc.id}/escalar`, { method: 'POST', body: Object.fromEntries(f.entries()) });
      aviso(`${inc.codigo} escalado.`);
      cargarIncidente(inc.id);
    } }],
  });
}

function pintarIntervenciones(d) {
  const caja = $('#tarjeta-intervenciones');
  const iv = d.intervenciones || [];
  const es = d.escalamientos || [];
  if (!iv.length && !es.length) { caja.hidden = true; return; }
  caja.hidden = false;
  caja.innerHTML = `<h2>Soluciones y escalamientos</h2><ul class="citas">${iv.map((x) => `
    <li><div><b>Ronda ${x.ronda} · ${esc(x.hipotesis_nombre)}</b> ${chip(x.resultado)}
      <small>${fecha(x.registrado_en)} · ${esc(x.administrador)}${x.tiempo_min != null ? ` · ${x.tiempo_min} min` : ''}</small>
      <small>${esc(x.accion_aplicada)}</small>${x.observaciones ? `<small class="ayuda">${esc(x.observaciones)}</small>` : ''}</div></li>`).join('')}
    ${es.map((x) => `<li><div><b>Escalado a ${esc(x.destino)}</b> ${chip('ESCALADO')}<small>${fecha(x.escalado_en)} · ${esc(x.administrador)}</small>
      <small>${esc(x.motivo)}</small></div></li>`).join('')}</ul>`;
}

// ================================================================ citas
async function cargarCitas() {
  $('#titulo-citas').textContent = esAdmin() ? 'Agenda de citas' : 'Mis citas';
  $('#subtitulo-citas').textContent = esAdmin() ? 'Citas desde ayer en adelante. Seleccione una para abrir su incidente.'
    : 'Citas de sus incidentes. Seleccione una para reprogramarla o cancelarla desde el incidente.';
  const tabla = $('#tabla-citas');
  tabla.innerHTML = vacio('Cargando…');
  try {
    const { citas } = await api('/citas');
    if (!citas.length) { tabla.innerHTML = vacio('No hay citas.'); return; }
    tabla.innerHTML = `<thead><tr><th>Fecha</th><th>Hasta</th><th>Incidente</th><th>Lugar</th><th>Responsable</th><th>Estado</th></tr></thead>
      <tbody>${citas.map((c) => `<tr class="clic" data-id="${c.incidente_id}"><td class="mono">${fecha(c.inicio)}</td><td class="mono">${esc(String(c.fin).slice(11, 16))}</td>
        <td class="mono">${esc(c.incidente_codigo)}</td><td>${esc(c.lugar)}</td><td>${esc(c.administrador)}</td><td>${chip(c.estado)}</td></tr>`).join('')}</tbody>`;
    tabla.querySelectorAll('tr.clic').forEach((tr) => tr.addEventListener('click', () => mostrarVista('incidente', Number(tr.dataset.id))));
  } catch (e) { tabla.innerHTML = `<tr><td class="error-carga">${esc(e.message)}</td></tr>`; }
}

// ================================================================ indicadores e historial por equipo
async function cargarIndicadores() {
  const f = new FormData($('#filtro-indicadores'));
  const q = new URLSearchParams();
  for (const [k, v] of f.entries()) if (v) q.set(k, v);
  try {
    const r = await api(`/indicadores${q.toString() ? `?${q}` : ''}`);
    const kpis = [[r.total, 'incidentes reportados'], [r.cerrados, 'cerrados con solución'],
      [r.horas_promedio_solucion != null ? `${fmtNum(r.horas_promedio_solucion, 1)} h` : '—', 'tiempo promedio de solución'],
      [r.porcentaje_primera_ronda != null ? `${fmtNum(r.porcentaje_primera_ronda, 0)} %` : '—', 'resueltos en la primera ronda'],
      [r.escalamientos, 'escalamientos'],
      [r.minutos_promedio_intervencion != null ? `${fmtNum(r.minutos_promedio_intervencion, 0)} min` : '—', 'promedio por intervención']];
    $('#kpis').innerHTML = kpis.map(([n, t]) => `<div class="indicador"><b>${esc(n)}</b><span>${esc(t)}</span></div>`).join('');
    const maximo = Math.max(1, ...r.por_categoria.map((c) => c.n));
    const nombres = {};
    if (estado.catalogo) estado.catalogo.categorias.forEach((c) => { nombres[c.codigo] = c.nombre; });
    $('#grafico-categorias').innerHTML = r.por_categoria.length ? r.por_categoria.map((c, i) => `
      <div class="barra-h" style="--c:${SERIE[i % SERIE.length]}"><span class="nombre">${esc(c.categoria === '-' ? 'Sin diagnóstico' : `${c.categoria} · ${nombres[c.categoria] || ''}`)}</span>
        <span class="valor">${c.n}</span><span class="pista"><span style="width:${(100 * c.n) / maximo}%"></span></span></div>`).join('')
      : '<p class="ayuda">Sin datos.</p>';
    $('#tabla-confirmadas').innerHTML = r.hipotesis_confirmadas.length ? `<table><thead><tr><th>Hipótesis</th><th>Confirmada</th><th>Solucionó</th></tr></thead>
      <tbody>${r.hipotesis_confirmadas.map((h) => `<tr><td><span class="mono">${esc(h.hipotesis_codigo)}</span> ${esc(h.hipotesis_nombre)}</td>
        <td class="num">${h.confirmadas}</td><td class="num">${h.solucionadas}</td></tr>`).join('')}</tbody></table>` : '<p class="ayuda">Sin hipótesis confirmadas.</p>';
    $('#tabla-equipos').innerHTML = r.equipos.length ? `<table><thead><tr><th>Equipo</th><th>Tipo</th><th>Incidentes</th></tr></thead>
      <tbody>${r.equipos.map((e) => `<tr class="clic" data-inv="${esc(e.inventario)}"><td class="mono">${esc(e.inventario)}</td><td>${esc(e.tipo)}</td>
        <td class="num">${e.incidentes}</td></tr>`).join('')}</tbody></table>` : '<p class="ayuda">Sin datos.</p>';
    $('#tabla-equipos').querySelectorAll('tr.clic').forEach((tr) => tr.addEventListener('click', () => verHistorialEquipo(tr.dataset.inv)));
  } catch (e) { $('#kpis').innerHTML = `<div class="error-carga">${esc(e.message)}</div>`; }
}

async function verHistorialEquipo(inventario) {
  $('#form-historial-equipo').inventario.value = inventario;
  const caja = $('#historial-equipo');
  caja.innerHTML = '<div class="cargando">Cargando…</div>';
  try {
    const h = await api(`/equipos/${encodeURIComponent(inventario.trim())}/historial`);
    const e = h.equipo;
    caja.innerHTML = `<p><b class="mono">${esc(e.inventario)}</b> · ${esc(e.tipo_nombre)} ${esc(e.marca || '')} ${esc(e.modelo || '')} · ${esc(e.ubicacion)}</p>
      <ol class="linea-tiempo">${h.incidentes.map((x) => `<li><span class="punto-linea ${esc(x.incidente.estado)}"></span><div>
        <button class="enlace mono" data-inc="${x.incidente.id}">${esc(x.incidente.codigo)}</button> ${chip(x.incidente.estado)}
        <small>${fecha(x.incidente.fecha_apertura)} · ${esc(x.incidente.descripcion)}</small>
        ${x.confirmadas.map((c) => `<small>Ronda ${c.ronda}: ${esc(c.hipotesis_nombre)}</small>`).join('')}
        ${x.intervenciones.map((iv) => `<small>${chip(iv.resultado)} ${esc(iv.accion_aplicada)}</small>`).join('')}</div></li>`).join('') || '<li>Sin incidentes.</li>'}</ol>`;
    caja.querySelectorAll('[data-inc]').forEach((b) => b.addEventListener('click', () => mostrarVista('incidente', Number(b.dataset.inc))));
  } catch (err) { caja.innerHTML = `<div class="error-carga">${esc(err.message)}</div>`; }
}

async function exportarIncidentes() {
  try {
    const r = await ocupado(api(`/reportes/incidentes${filtrosIncidentes()}`));
    descargar(r.nombre, r.contenido, 'text/csv;charset=utf-8');
  } catch (e) { aviso(e.message, true); }
}

// ================================================================ usuarios (RF-01)
async function cargarUsuarios() {
  const tabla = $('#tabla-usuarios');
  tabla.innerHTML = vacio('Cargando…');
  try {
    const { usuarios } = await api('/usuarios');
    const ahora = new Date();
    tabla.innerHTML = `<thead><tr><th>Nombre</th><th>Documento</th><th>Correo</th><th>Rol</th><th>Dependencia</th><th>Estado</th><th>Último ingreso</th><th></th></tr></thead>
      <tbody>${usuarios.map((u) => {
        const bloqueada = u.bloqueado_hasta && new Date(u.bloqueado_hasta.replace(' ', 'T')) > ahora;
        const est = !u.activo ? '<span class="chip CANCELADA">Inactiva</span>' : bloqueada ? '<span class="chip ESCALADO">Bloqueada</span>' : '<span class="chip CERRADO">Activa</span>';
        return `<tr class="${u.activo ? '' : 'inactiva'}"><td>${esc(u.nombre)}</td><td class="mono">${esc(u.documento)}</td><td>${esc(u.correo)}</td>
          <td>${esc(u.rol_nombre)}</td><td>${esc(u.dependencia || '—')}</td><td>${est}${u.debe_cambiar_contrasena ? ' <small class="ayuda">clave temporal</small>' : ''}</td>
          <td class="mono">${fecha(u.ultimo_ingreso)}</td><td class="acciones-fila">
          <button class="boton secundario pequeno" data-usuario="${u.id}" data-accion="editar">Editar</button>
          <button class="boton secundario pequeno" data-usuario="${u.id}" data-accion="${u.activo ? 'desactivar' : 'activar'}">${u.activo ? 'Desactivar' : 'Activar'}</button>
          <button class="boton secundario pequeno" data-usuario="${u.id}" data-accion="restablecer">${bloqueada ? 'Desbloquear' : 'Restablecer clave'}</button></td></tr>`;
      }).join('')}</tbody>`;
    tabla.querySelectorAll('[data-usuario]').forEach((b) => b.addEventListener('click', () => {
      accionUsuario(usuarios.find((u) => u.id === Number(b.dataset.usuario)), b.dataset.accion);
    }));
  } catch (e) { tabla.innerHTML = `<tr><td class="error-carga">${esc(e.message)}</td></tr>`; }
  pintarPermisos();
  try {
    const { accesos } = await api('/usuarios/bitacora');
    $('#tabla-bitacora').innerHTML = `<thead><tr><th>Fecha</th><th>Correo</th><th>Resultado</th><th>IP</th></tr></thead><tbody>${accesos.map((a) => `
      <tr><td class="mono">${fecha(a.fecha)}</td><td>${esc(a.correo_intentado)}</td><td>${a.exitoso ? chip('ATENDIDA').replace('Atendida', 'Ingreso') : `<span class="chip CANCELADA">${esc(a.motivo)}</span>`}</td>
      <td class="mono">${esc(a.ip || '—')}</td></tr>`).join('')}</tbody>`;
  } catch (e) { /* sin bitácora */ }
}

function pintarPermisos() {
  const p = (atencion.catalogos && atencion.catalogos.permisos) || [];
  const modulos = [...new Map(p.map((x) => [x.modulo, x.modulo_nombre])).entries()];
  const celda = (rol, modulo) => {
    const x = p.find((y) => y.rol === rol && y.modulo === modulo);
    if (!x || !x.puede_consultar) return '<span class="ayuda">—</span>';
    return ['Consulta', x.puede_crear ? 'crea' : '', x.puede_modificar ? 'modifica' : ''].filter(Boolean).join(', ');
  };
  $('#matriz-permisos').innerHTML = `<table><thead><tr><th>Módulo</th><th>Solicitante</th><th>Administrador</th></tr></thead><tbody>${modulos.map(([m, n]) =>
    `<tr><td>${esc(n)}</td><td>${celda('SOLICITANTE', m)}</td><td>${celda('ADMINISTRADOR', m)}</td></tr>`).join('')}
    <tr><td>Eliminar registros</td><td colspan="2">Ningún rol</td></tr></tbody></table>`;
}

function dialogoUsuario(u) {
  const c = atencion.catalogos || { roles: [], dependencias: [] };
  abrirDialogo({
    titulo: u ? `Editar cuenta · ${u.nombre}` : 'Nueva cuenta',
    cuerpo: `<div class="rejilla-form">
        <label>Documento *<input name="documento" required minlength="4" maxlength="20" value="${esc(u ? u.documento : '')}" ${u ? 'disabled' : ''}></label>
        <label>Nombre completo *<input name="nombre" required maxlength="120" value="${esc(u ? u.nombre : '')}"></label>
        <label>Correo *<input name="correo" type="email" required maxlength="120" value="${esc(u ? u.correo : '')}"></label>
        <label>Rol *<select name="rol" required>${c.roles.map((r) => `<option value="${esc(r.codigo)}" ${u && u.rol_codigo === r.codigo ? 'selected' : ''}>${esc(r.nombre)}</option>`).join('')}</select></label>
        <label>Dependencia<select name="dependencia_id">${opciones(c.dependencias, u && u.dependencia_id, '—')}</select></label>
      </div>
      <p class="ayuda">${u ? 'Un cambio de rol rige desde la siguiente acción del usuario.' : 'El sistema genera una contraseña temporal y pedirá cambiarla en el primer ingreso.'}</p>`,
    botones: [{ texto: u ? 'Guardar' : 'Crear cuenta', accion: async (f) => {
      const datos = Object.fromEntries(f.entries());
      if (u) {
        await api(`/usuarios/${u.id}`, { method: 'POST', body: datos });
        aviso('Cuenta actualizada.');
        cargarUsuarios();
      } else {
        const r = await api('/usuarios', { method: 'POST', body: datos });
        cargarUsuarios();
        setTimeout(() => mostrarClave('Cuenta creada', `Contraseña temporal de ${r.usuario.nombre}:`, r.contrasena_temporal), 50);
      }
    } }],
  });
}

async function accionUsuario(u, accion) {
  try {
    if (accion === 'editar') { dialogoUsuario(u); return; }
    if (accion === 'activar' || accion === 'desactivar') {
      if (accion === 'desactivar' && !confirm(`¿Desactivar la cuenta de ${u.nombre}? No podrá ingresar, pero su historial se conserva.`)) return;
      await ocupado(api(`/usuarios/${u.id}/estado`, { method: 'POST', body: { activo: accion === 'activar' } }));
      aviso(accion === 'activar' ? 'Cuenta activada.' : 'Cuenta desactivada.');
    } else if (accion === 'restablecer') {
      if (!confirm(`¿Desbloquear la cuenta de ${u.nombre} y generarle una contraseña temporal nueva?`)) return;
      const r = await ocupado(api(`/usuarios/${u.id}/desbloquear`, { method: 'POST', body: { restablecer: true } }));
      mostrarClave('Contraseña restablecida', `Nueva contraseña temporal de ${u.nombre}:`, r.contrasena_temporal);
    }
    cargarUsuarios();
  } catch (e) { aviso(e.message, true); }
}

// ================================================================ administración de la base de conocimiento (RF-03)
async function recargarBC() {
  estado.bcCargada = false;
  estado.evidenciasCargadas = false;
  estado.catalogo = null;
  atencion.evidenciasBC = null;
  await cargarConocimiento();
  if (estado.hipotesisSeleccionada) verGranulos(estado.hipotesisSeleccionada);
  if ($('#plegable-evidencias').open) cargarEvidencias(true);
  if ($('#plegable-auditoria').open) cargarAuditoria();
}

function dialogoHipotesis() {
  abrirDialogo({
    titulo: 'Nueva hipótesis',
    cuerpo: `<label>Nombre (falla probable) *<input name="nombre" required minlength="3" maxlength="120" placeholder="Batería del portátil"></label>
      <div class="rejilla-form">
        <label>Dominio *<select name="dominio" required>${DOMINIOS.map((d) => `<option>${d}</option>`).join('')}</select></label>
        <label>Probabilidad previa<input name="probabilidad_previa" type="number" step="0.001" min="0.0001" max="1" value="0.01"></label>
      </div>
      <p class="ayuda">El código HIP-NN lo asigna el sistema y no cambia. La probabilidad previa es la frecuencia esperada de la falla antes de cualquier evidencia.</p>`,
    botones: [{ texto: 'Crear', accion: async (f) => {
      const r = await api('/conocimiento/hipotesis', { method: 'POST', body: Object.fromEntries(f.entries()) });
      aviso(`Hipótesis ${r.hipotesis.codigo} creada. Agréguele gránulos para que el motor la use.`);
      estado.hipotesisSeleccionada = r.hipotesis.id;
      recargarBC();
    } }],
  });
}

function dialogoEvidencia() {
  abrirDialogo({
    titulo: 'Nueva evidencia',
    cuerpo: `<div class="rejilla-form">
        <label>Tipo *<select name="tipo" required><option value="SINTOMA">Síntoma (lo que se observa)</option><option value="PRUEBA">Prueba (resultado de una prueba)</option></select></label>
        <label>Variable (opcional)<input name="variable" maxlength="40" placeholder="TENSION_TOMA" pattern="[A-Za-z0-9_]{2,40}"></label>
      </div>
      <label>Enunciado *<input name="enunciado" required minlength="5" maxlength="250" placeholder="la batería reporta menos del 40 % de su capacidad"></label>
      <label>Pregunta al usuario<input name="pregunta" maxlength="300" placeholder="Si se deja vacía: ¿La batería reporta…?"></label>
      <label class="en-linea"><input type="checkbox" name="polaridad" value="-1"> El enunciado niega la variable (polaridad −1)</label>
      <p class="ayuda">Las evidencias que describen la misma observación comparten variable; así el motor deduce la respuesta opuesta sin volver a preguntar.</p>`,
    botones: [{ texto: 'Crear', accion: async (f) => {
      const datos = Object.fromEntries(f.entries());
      datos.polaridad = datos.polaridad === '-1' ? -1 : 1;
      const r = await api('/conocimiento/evidencias', { method: 'POST', body: datos });
      aviso(`Evidencia ${r.evidencia.codigo} creada.`);
      recargarBC();
    } }],
  });
}

async function datosGranulo() {
  if (!atencion.ramas) atencion.ramas = (await api('/conocimiento/ramas')).ramas;
  if (!atencion.evidenciasBC) atencion.evidenciasBC = (await api('/conocimiento/evidencias')).evidencias;
  if (!estado.bcCargada) await cargarConocimiento();
}

async function dialogoGranulo() {
  try { await ocupado(datosGranulo()); } catch (e) { aviso(e.message, true); return; }
  const condiciones = [];
  const hs = estado.hipotesis.filter((h) => h.activo !== 0);
  abrirDialogo({
    titulo: 'Nuevo gránulo (regla If / And / Then)',
    ancho: true,
    cuerpo: `<div class="rejilla-form">
        <label>Hipótesis que concluye *<select name="hipotesis_id" required>${hs.map((h) => `<option value="${h.id}" ${h.id === estado.hipotesisSeleccionada ? 'selected' : ''}>${esc(h.codigo)} · ${esc(h.nombre)}</option>`).join('')}</select></label>
        <label>Rama del árbol *<select name="rama_codigo" required>${atencion.ramas.map((r) => `<option value="${esc(r.rama_codigo)}">${esc(r.rama_codigo)} · ${esc(r.rama_nombre)} (${esc(r.categoria_nombre)})</option>`).join('')}</select></label>
      </div>
      <h3>Condiciones</h3>
      <ol class="constructor" id="lista-condiciones"></ol>
      <div class="agregar-condicion"><input type="search" id="buscar-evidencia" placeholder="Busque una evidencia por código o texto y elíjala" list="evidencias-bc" autocomplete="off">
        <datalist id="evidencias-bc">${atencion.evidenciasBC.map((e) => `<option value="${esc(e.codigo)} · ${esc(e.enunciado)}"></option>`).join('')}</datalist>
        <button type="button" class="boton secundario pequeno" id="boton-agregar-condicion">Agregar</button></div>
      <label>Then (conclusión) *<input name="conclusion" required minlength="5" maxlength="250" placeholder="la falla está en la batería del portátil"></label>
      <label>Acción recomendada *<textarea name="accion" rows="2" required minlength="5" maxlength="500"></textarea></label>
      <div class="rejilla-form">
        <label>Factor de certeza del experto (0 a 100) *<input name="factor_certeza" type="number" min="0" max="100" step="1" value="80" required></label>
        <label class="en-linea"><input type="checkbox" name="riesgo_perdida_datos" value="1"> La acción puede borrar información</label>
      </div>`,
    alAbrir: (cuerpo) => {
      const lista = cuerpo.querySelector('#lista-condiciones');
      const pintar = () => {
        lista.innerHTML = condiciones.length ? condiciones.map((c, i) => `<li><span class="con">${i ? 'And' : 'If'}</span>
          <span><span class="mono">${esc(c.codigo)}</span> ${esc(c.enunciado)}</span>
          <span><button type="button" class="enlace" data-subir="${i}" ${i ? '' : 'disabled'}>↑</button>
          <button type="button" class="enlace" data-quitar="${i}">Quitar</button></span></li>`).join('')
          : '<li class="ayuda">Agregue al menos una condición. La primera es la condición If (síntoma de entrada).</li>';
        lista.querySelectorAll('[data-quitar]').forEach((b) => b.addEventListener('click', () => { condiciones.splice(Number(b.dataset.quitar), 1); pintar(); }));
        lista.querySelectorAll('[data-subir]').forEach((b) => b.addEventListener('click', () => {
          const i = Number(b.dataset.subir);
          [condiciones[i - 1], condiciones[i]] = [condiciones[i], condiciones[i - 1]];
          pintar();
        }));
      };
      const agregar = () => {
        const campo = cuerpo.querySelector('#buscar-evidencia');
        const codigo = campo.value.split('·')[0].trim().toUpperCase();
        const e = atencion.evidenciasBC.find((x) => x.codigo === codigo);
        if (!e) { $('#dialogo-error').textContent = 'Elija una evidencia de la lista.'; return; }
        if (condiciones.some((c) => c.id === e.id)) { $('#dialogo-error').textContent = 'Esa evidencia ya es una condición.'; return; }
        $('#dialogo-error').textContent = '';
        condiciones.push(e);
        campo.value = '';
        pintar();
      };
      cuerpo.querySelector('#boton-agregar-condicion').addEventListener('click', agregar);
      cuerpo.querySelector('#buscar-evidencia').addEventListener('keydown', (ev) => { if (ev.key === 'Enter') { ev.preventDefault(); agregar(); } });
      pintar();
    },
    botones: [{ texto: 'Crear gránulo', accion: async (f) => {
      if (!condiciones.length) throw new Error('El gránulo necesita al menos una condición.');
      const datos = Object.fromEntries(f.entries());
      datos.riesgo_perdida_datos = !!datos.riesgo_perdida_datos;
      datos.condiciones = condiciones.map((c) => ({ evidencia_id: c.id }));
      const r = await api('/conocimiento/granulos', { method: 'POST', body: datos });
      aviso(`Gránulo ${r.condiciones[0].regla} creado y activo: el motor lo usará en el siguiente diagnóstico.`);
      estado.hipotesisSeleccionada = Number(datos.hipotesis_id);
      atencion.ramas = null;
      recargarBC();
    } }],
  });
}

async function accionGranulo(regla, accion) {
  try {
    const { condiciones } = await ocupado(api(`/conocimiento/granulos/${regla}`));
    const g = condiciones[0];
    if (accion === 'editar') {
      abrirDialogo({
        titulo: `Modificar ${regla} (versión ${g.version} → ${g.version + 1})`,
        cuerpo: `<p class="ayuda">Las condiciones no cambian: para otra combinación de evidencias cree un gránulo nuevo y desactive este.
            Los diagnósticos anteriores conservan la versión que usaron.</p>
          <label>Then (conclusión) *<input name="conclusion" required minlength="5" maxlength="250" value="${esc(g.conclusion)}"></label>
          <label>Acción recomendada *<textarea name="accion" rows="3" required minlength="5" maxlength="500">${esc(g.accion)}</textarea></label>
          <div class="rejilla-form">
            <label>Factor de certeza (0 a 100) *<input name="factor_certeza" type="number" min="0" max="100" step="1" required value="${Number(g.factor_certeza)}"></label>
            <label class="en-linea"><input type="checkbox" name="riesgo_perdida_datos" value="1" ${g.riesgo_perdida_datos ? 'checked' : ''}> La acción puede borrar información</label>
          </div>`,
        botones: [{ texto: 'Guardar versión', accion: async (f) => {
          const datos = Object.fromEntries(f.entries());
          datos.riesgo_perdida_datos = !!datos.riesgo_perdida_datos;
          const r = await api(`/conocimiento/granulos/${regla}`, { method: 'POST', body: datos });
          aviso(`${regla} quedó en la versión ${r.condiciones[0].version}.`);
          recargarBC();
        } }],
      });
    } else if (accion === 'simular') {
      abrirDialogo({
        titulo: `Simular ${regla}`,
        cuerpo: `<p class="ayuda">Marque las evidencias que se observarían (con «Sí, con certeza») y vea la certeza que daría el gránulo.</p>
          <div class="simulador">${condiciones.map((c) => `<label class="en-linea"><input type="checkbox" name="ev" value="${c.evidencia_id}" checked>
            <span class="con">${esc(c.conector)}</span> ${esc(c.enunciado)}</label>`).join('')}</div>
          <p class="entonces"><span class="con">Then</span>${esc(g.conclusion)} · FC del experto ${fmtNum(g.factor_certeza, 0)} %</p>
          <div id="resultado-simulacion" class="resultado-simulacion"></div>`,
        botones: [{ texto: 'Calcular', validar: false, accion: async (f) => {
          const r = await api(`/conocimiento/granulos/${regla}/simular`, { method: 'POST', body: { evidencias: f.getAll('ev').map(Number) } });
          $('#resultado-simulacion').innerHTML = `<div><b>${r.cumplidas} de ${r.total}</b><span>condiciones cumplidas</span></div>
            <div><b>${fmtNum(r.certeza_proporcional, 1)} %</b><span>certeza proporcional (FC × cumplidas / total)</span></div>
            <div><b>${fmtSigno(r.aporte_motor, 3)}</b><span>aporte en el motor (aplicabilidad ${fmtNum(r.aplicabilidad)} × grado ${fmtNum(r.grado)} × FC)</span></div>`;
          return false;
        } }],
      });
    } else {
      const activo = accion === 'activar';
      if (!activo && !confirm(`¿Desactivar ${regla}? El motor dejará de usarlo en los diagnósticos nuevos; nada se elimina.`)) return;
      await ocupado(api(`/conocimiento/granulos/${regla}/estado`, { method: 'POST', body: { activo } }));
      aviso(`${regla} ${activo ? 'activado' : 'desactivado'}.`);
      recargarBC();
    }
  } catch (e) { aviso(e.message, true); }
}

async function cambiarEstadoElemento(ruta, activoActual, nombre) {
  const activo = !activoActual;
  if (!activo && !confirm(`¿Desactivar ${nombre}? Nada se elimina y puede volver a activarse.`)) return;
  try {
    await ocupado(api(ruta, { method: 'POST', body: { activo } }));
    aviso(`${nombre} ${activo ? 'activada' : 'desactivada'}.`);
    recargarBC();
  } catch (e) { aviso(e.message, true); }
}

async function cargarAuditoria() {
  try {
    const { auditoria } = await api('/conocimiento/auditoria');
    $('#tabla-auditoria').innerHTML = `<thead><tr><th>Fecha</th><th>Elemento</th><th>Código</th><th>Versión</th><th>Acción</th><th>Usuario</th></tr></thead>
      <tbody>${auditoria.map((a) => `<tr><td class="mono">${fecha(a.fecha)}</td><td>${esc(a.entidad)}</td><td class="mono">${esc(a.codigo || '—')}</td>
        <td class="num">${a.version ?? '—'}</td><td>${esc(a.accion)}</td><td>${esc(a.usuario || '—')}</td></tr>`).join('')}</tbody>`;
  } catch (e) { $('#tabla-auditoria').innerHTML = `<tr><td class="error-carga">${esc(e.message)}</td></tr>`; }
}

// ================================================================ navegación y eventos
function refrescarVistaActual() {
  const activa = document.querySelector('.vista.activa');
  if (!activa) return;
  if (activa.id === 'vista-incidente') cargarIncidente();
  else if (activa.id === 'vista-citas') cargarCitas();
}

alMostrar.incidentes = cargarIncidentes;
alMostrar.incidente = cargarIncidente;
alMostrar.citas = cargarCitas;
alMostrar.indicadores = () => { if (!estado.catalogo) cargarCatalogo().then(cargarIndicadores); else cargarIndicadores(); };
alMostrar.usuarios = cargarUsuarios;

$('#form-acceso').addEventListener('submit', ingresar);
document.querySelectorAll('[data-demo]').forEach((b) => b.addEventListener('click', () => {
  $('#acceso-correo').value = b.dataset.demo;
  $('#acceso-clave').value = 'Sedati2026*';
  $('#acceso-clave').focus();
}));
$('#boton-salir').addEventListener('click', () => cerrarSesion());
$('#boton-contrasena').addEventListener('click', () => dialogoContrasena(false));
$('#boton-reportar').addEventListener('click', dialogoReportar);
$('#boton-exportar').addEventListener('click', exportarIncidentes);
$('#boton-exportar-2').addEventListener('click', exportarIncidentes);
$('#volver-incidentes').addEventListener('click', () => mostrarVista('incidentes'));
$('#filtros-incidentes').addEventListener('submit', (e) => { e.preventDefault(); cargarIncidentes(); });
$('#filtros-incidentes').addEventListener('reset', () => setTimeout(cargarIncidentes, 0));
$('#filtro-indicadores').addEventListener('submit', (e) => { e.preventDefault(); cargarIndicadores(); });
$('#form-historial-equipo').addEventListener('submit', (e) => { e.preventDefault(); verHistorialEquipo(e.target.inventario.value); });
$('#boton-nuevo-usuario').addEventListener('click', () => dialogoUsuario(null));
$('#boton-nueva-hipotesis').addEventListener('click', dialogoHipotesis);
$('#boton-nueva-evidencia').addEventListener('click', dialogoEvidencia);
$('#boton-nuevo-granulo').addEventListener('click', dialogoGranulo);
$('#plegable-auditoria').addEventListener('toggle', (e) => { if (e.target.open) cargarAuditoria(); });
$('#lista-granulos').addEventListener('click', (e) => {
  const b = e.target.closest('[data-accion-regla]');
  if (b) accionGranulo(b.dataset.regla, b.dataset.accionRegla);
});
$('#acciones-hipotesis').addEventListener('click', (e) => {
  const b = e.target.closest('[data-hipotesis]');
  if (!b) return;
  const h = estado.hipotesis.find((x) => x.id === Number(b.dataset.hipotesis));
  cambiarEstadoElemento(`/conocimiento/hipotesis/${h.id}/estado`, b.dataset.activa === '1', `la hipótesis ${h.codigo}`);
});
$('#tabla-evidencias').addEventListener('click', (e) => {
  const b = e.target.closest('[data-evidencia]');
  if (!b) return;
  const ev = estado.evidencias.find((x) => x.id === Number(b.dataset.evidencia));
  cambiarEstadoElemento(`/conocimiento/evidencias/${ev.id}/estado`, b.dataset.activa === '1', `la evidencia ${ev.codigo}`);
});
window.addEventListener('sedati:actividad', reiniciarInactividad);
window.addEventListener('sedati:sesion-vencida', (e) => { if (estado.usuario) cerrarSesion(e.detail || 'La sesión venció. Ingrese de nuevo.'); });
['click', 'keydown'].forEach((t) => document.addEventListener(t, () => { if (estado.usuario) reiniciarInactividad(); }, { passive: true }));

// Al cargar: si la pestaña conserva una sesión vigente, se retoma.
(async () => {
  const token = tokenGuardado();
  if (!token) return;
  guardarToken(token);
  try {
    const r = await api('/auth/sesion');
    await iniciarSesion(r.usuario);
  } catch (e) { cerrarSesion(); }
})();
