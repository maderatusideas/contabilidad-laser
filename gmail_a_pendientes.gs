/**
 * MADERA TUS IDEAS · Asistente de correo
 *
 * 1) ~00:00 Guarda los adjuntos de las facturas en "FACTURAS PENDIENTES"
 *    y marca el correo con "Facturas/Procesada" para no repetirlo nunca.
 * 2) ~07:00 Envía un resumen diario (ventas, pagos, envíos, facturas).
 *
 * USO: pega este código en script.google.com, ejecuta "instalar" una
 * sola vez y acepta los permisos. A partir de ahí funciona solo.
 *
 * Para forzar que un correo se recoja aunque no diga "factura",
 * ponle a mano la etiqueta "Facturas/Recoger".
 */

const ID_CARPETA_PENDIENTES = '1t6iW1SF7EEFN3TQIlgPMb41bp3z6exs6';
const ETIQUETA_PROCESADA = 'Facturas/Procesada';
const ETIQUETA_RECOGER = 'Facturas/Recoger';
const PALABRAS = '(factura OR facturas OR invoice OR recibo OR ticket OR "justificante de compra")';
const TIPOS_VALIDOS = ['application/pdf', 'image/jpeg', 'image/png'];
const TAMANO_MINIMO_IMAGEN = 30 * 1024; // ignora logos y firmas pequeñas

// ---- Resumen diario ----
const DESTINATARIOS_RESUMEN = 'oscarmocha1@gmail.com, paplisia2009@gmail.com';
const HORA_RESUMEN = 7;
const CATEGORIAS = [
  { nombre: '🛍️ Ventas y pedidos', dominios: ['etsy.com', 'shopify.com'] },
  { nombre: '💶 Pagos', dominios: ['paypal.com', 'paypal.es', 'stripe.com'] },
  { nombre: '📦 Envíos', dominios: ['correos.es', 'seur.com', 'seur.es', 'gls-spain.es', 'gls-group.eu', 'gls-group.com', 'mrw.es'] },
];


/** Ejecutar UNA vez: crea etiquetas, fija la fecha de inicio y programa la tarea diaria. */
function instalar() {
  obtenerEtiqueta_(ETIQUETA_PROCESADA);
  obtenerEtiqueta_(ETIQUETA_RECOGER);

  // Solo se recogen correos desde hoy: lo anterior ya está registrado.
  const props = PropertiesService.getScriptProperties();
  if (!props.getProperty('FECHA_INICIO')) {
    props.setProperty(
      'FECHA_INICIO',
      Utilities.formatDate(new Date(), 'Europe/Madrid', 'yyyy/MM/dd')
    );
  }

  ScriptApp.getProjectTriggers()
    .filter(t => ['recogerFacturas', 'enviarResumen'].indexOf(t.getHandlerFunction()) !== -1)
    .forEach(t => ScriptApp.deleteTrigger(t));

  ScriptApp.newTrigger('enviarResumen')
    .timeBased()
    .everyDays(1)
    .atHour(HORA_RESUMEN)
    .inTimezone('Europe/Madrid')
    .create();

  ScriptApp.newTrigger('recogerFacturas')
    .timeBased()
    .everyDays(1)
    .atHour(0)
    .inTimezone('Europe/Madrid')
    .create();

  recogerFacturas();
  Logger.log('✅ Instalado: facturas ~00:00 y resumen ~07:00 cada día.');
}


/** Tarea diaria: guarda los adjuntos de facturas nuevas en PENDIENTES. */
function recogerFacturas() {
  const carpeta = DriveApp.getFolderById(ID_CARPETA_PENDIENTES);
  const procesada = obtenerEtiqueta_(ETIQUETA_PROCESADA);
  const recoger = obtenerEtiqueta_(ETIQUETA_RECOGER);
  const desde = PropertiesService.getScriptProperties().getProperty('FECHA_INICIO') || '';

  const consulta =
    `has:attachment -label:${ETIQUETA_PROCESADA.replace('/', '-')} ` +
    `-in:sent -in:chats ` +
    `((${desde ? `after:${desde} ` : ''}${PALABRAS}) ` +
    `OR label:${ETIQUETA_RECOGER.replace('/', '-')})`;

  const hilos = GmailApp.search(consulta, 0, 50);
  let guardados = 0;
  const nombresGuardados = [];

  hilos.forEach(hilo => {
    hilo.getMessages().forEach(mensaje => {
      const fecha = Utilities.formatDate(mensaje.getDate(), 'Europe/Madrid', 'yyyy-MM-dd');
      const remitente = limpiar_(
        mensaje.getFrom().replace(/<.*>/, '').replace(/"/g, '').trim() || 'remitente'
      );

      mensaje.getAttachments({ includeInlineImages: false }).forEach(adjunto => {
        const tipo = adjunto.getContentType();
        if (TIPOS_VALIDOS.indexOf(tipo) === -1) return;
        if (tipo !== 'application/pdf' && adjunto.getSize() < TAMANO_MINIMO_IMAGEN) return;

        const nombre = `${fecha} ${remitente} - ${adjunto.getName()}`;
        carpeta.createFile(adjunto.copyBlob()).setName(nombre);
        nombresGuardados.push(nombre);
        guardados++;
      });
    });

    hilo.addLabel(procesada);
    hilo.removeLabel(recoger);
  });

  // Se acumulan para el próximo resumen
  const props = PropertiesService.getScriptProperties();
  const previas = JSON.parse(props.getProperty('RECOGIDAS_PARA_RESUMEN') || '[]');
  props.setProperty(
    'RECOGIDAS_PARA_RESUMEN',
    JSON.stringify(previas.concat(nombresGuardados).slice(-100))
  );

  Logger.log(`Facturas guardadas en PENDIENTES: ${guardados}`);
}


/** Resumen diario: novedades de las últimas 24 h por categoría. */
function enviarResumen() {
  const zona = 'Europe/Madrid';
  const hoy = Utilities.formatDate(new Date(), zona, 'dd/MM/yyyy');
  const todos = [].concat.apply([], CATEGORIAS.map(c => c.dominios));
  const hilos = GmailApp.search(
    `newer_than:1d -in:sent -in:chats from:(${todos.join(' OR ')})`, 0, 100
  );

  const grupos = CATEGORIAS.map(c => ({ nombre: c.nombre, dominios: c.dominios, items: [] }));

  hilos.forEach(hilo => {
    const mensaje = hilo.getMessages().pop();
    const de = mensaje.getFrom().toLowerCase();
    const grupo = grupos.find(g => g.dominios.some(d => de.indexOf(d) !== -1));
    if (!grupo) return;
    grupo.items.push({
      remitente: mensaje.getFrom().replace(/<.*>/, '').replace(/"/g, '').trim(),
      asunto: mensaje.getSubject() || '(sin asunto)',
      hora: Utilities.formatDate(mensaje.getDate(), zona, 'dd/MM HH:mm'),
      enlace: 'https://mail.google.com/mail/u/0/#inbox/' + hilo.getId(),
    });
  });

  // Facturas
  const props = PropertiesService.getScriptProperties();
  const recogidas = JSON.parse(props.getProperty('RECOGIDAS_PARA_RESUMEN') || '[]');
  let pendientes = 0;
  const archivos = DriveApp.getFolderById(ID_CARPETA_PENDIENTES).getFiles();
  while (archivos.hasNext()) { archivos.next(); pendientes++; }

  const esc = t => String(t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  let html = `<div style="font-family:Arial,sans-serif;font-size:14px;color:#222">` +
    `<h2 style="margin:0 0 4px">☀️ Resumen Madera Tus Ideas</h2>` +
    `<div style="color:#777;margin-bottom:16px">${hoy} · últimas 24 horas</div>`;

  let total = 0;
  grupos.forEach(g => {
    html += `<h3 style="margin:16px 0 6px">${g.nombre} (${g.items.length})</h3>`;
    if (!g.items.length) {
      html += `<div style="color:#999">Sin novedades</div>`;
      return;
    }
    total += g.items.length;
    html += '<ul style="padding-left:18px;margin:0">' + g.items.map(i =>
      `<li style="margin-bottom:4px"><a href="${i.enlace}">${esc(i.asunto)}</a>` +
      ` <span style="color:#777">· ${esc(i.remitente)} · ${i.hora}</span></li>`
    ).join('') + '</ul>';
  });

  html += `<h3 style="margin:16px 0 6px">🧾 Facturas</h3>` +
    `<div>Recogidas del correo: <b>${recogidas.length}</b></div>` +
    (recogidas.length
      ? '<ul style="padding-left:18px;margin:4px 0">' +
        recogidas.map(n => `<li>${esc(n)}</li>`).join('') + '</ul>'
      : '') +
    `<div>Pendientes de registrar en la app: <b>${pendientes}</b></div>` +
    `</div>`;

  GmailApp.sendEmail(
    DESTINATARIOS_RESUMEN,
    `☀️ Resumen ${hoy} · ${total} novedades · ${pendientes} facturas pendientes`,
    'Abre este correo en un lector compatible con HTML.',
    { htmlBody: html, name: 'Asistente Madera Tus Ideas' }
  );

  props.setProperty('RECOGIDAS_PARA_RESUMEN', '[]');
}


function obtenerEtiqueta_(nombre) {
  return GmailApp.getUserLabelByName(nombre) || GmailApp.createLabel(nombre);
}

function limpiar_(texto) {
  return texto.replace(/[\\/:*?"<>|]/g, '').slice(0, 40);
}
