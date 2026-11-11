/**
 * MADERA TUS IDEAS · Asistente de correo
 *
 * 1) ~00:00 Guarda los adjuntos de las facturas en "FACTURAS PENDIENTES"
 *    y marca el correo con "Facturas/Procesada" para no repetirlo nunca.
 *    Después lee cada factura de PENDIENTES con Gemini, la apunta en la
 *    hoja GASTOS y la mueve a AÑO/TRIMESTRE/GASTOS. Si algo no cuadra,
 *    la deja en PENDIENTES y lo avisa en el resumen.
 * 2) ~07:00 Envía un resumen diario (ventas, pagos, envíos, gastos, facturas).
 *
 * Requiere la propiedad del script GEMINI_API_KEY (Configuración del
 * proyecto → Propiedades del script).
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
const ID_HOJA_CONTABILIDAD = '1JYa4juKbMj5mJcqL-4eWTmXdvHXwrLG63FN8aABSgIo';
const ID_CARPETA_PRINCIPAL = '1h1HbsWqXxaK7h_S2oFo9GfKHd7vzkv9p'; // Contabilidad Láser
const MODELO_GEMINI = 'gemini-3.5-flash-lite';
const INSTRUCCIONES_LECTURA = [
  'Eres un asistente contable español. Lee esta factura o ticket de COMPRA',
  'y devuelve SOLO un JSON con estas claves:',
  '- proveedor: nombre comercial del emisor (texto corto)',
  '- fecha: fecha de emisión en formato AAAA-MM-DD',
  '- numero_factura: número de factura o ticket ("" si no aparece)',
  '- concepto: resumen breve de lo comprado (máx. 8 palabras)',
  '- base_imponible: número, suma de bases imponibles',
  '- iva: número, suma de cuotas de IVA',
  '- total: número, total pagado',
  'Si hay varios tipos de IVA, suma las bases y las cuotas.',
  'Si un dato no aparece, usa "" o 0. No inventes datos.'
].join('\n');
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
        const nombreAdj = (adjunto.getName() || '').toLowerCase();
        const porExtension = /\.pdf$/.test(nombreAdj) ? 'application/pdf'
          : /\.(jpe?g)$/.test(nombreAdj) ? 'image/jpeg'
          : /\.png$/.test(nombreAdj) ? 'image/png' : '';
        const tipo = TIPOS_VALIDOS.indexOf(adjunto.getContentType()) !== -1
          ? adjunto.getContentType() : porExtension;
        if (!tipo) return;
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

  // Registro automático de todo lo que haya en PENDIENTES
  try {
    registrarPendientes();
  } catch (e) {
    anotarAccion_({ tipo: 'revisar', archivo: '(registro automático)', motivo: 'Error general: ' + e.message });
  }
}


/** Lee cada factura de PENDIENTES, la apunta en GASTOS y la archiva en su trimestre. */
function registrarPendientes() {
  const clave = PropertiesService.getScriptProperties().getProperty('GEMINI_API_KEY');
  if (!clave) {
    anotarAccion_({ tipo: 'revisar', archivo: '(configuración)', motivo: 'Falta GEMINI_API_KEY en las propiedades del script' });
    return;
  }

  const pendientes = DriveApp.getFolderById(ID_CARPETA_PENDIENTES);
  const hoja = SpreadsheetApp.openById(ID_HOJA_CONTABILIDAD).getSheetByName('GASTOS');
  const existentes = hoja.getLastRow() > 1
    ? hoja.getRange(2, 1, hoja.getLastRow() - 1, 8).getValues()
    : [];
  const zona = 'Europe/Madrid';
  const hoy = new Date();
  const archivos = pendientes.getFiles();

  while (archivos.hasNext()) {
    const archivo = archivos.next();
    const nombre = archivo.getName();
    try {
      const blob = archivo.getBlob();
      const tipo = TIPOS_VALIDOS.indexOf(blob.getContentType()) !== -1
        ? blob.getContentType()
        : (/\.pdf$/i.test(nombre) ? 'application/pdf' : /\.png$/i.test(nombre) ? 'image/png' : 'image/jpeg');

      const d = leerFacturaGemini_(clave, blob.getBytes(), tipo);
      const total = aNumero_(d.total);
      let base = aNumero_(d.base_imponible);
      let iva = aNumero_(d.iva);
      const proveedor = String(d.proveedor || '').trim();
      const numero = String(d.numero_factura || '').trim();
      const fecha = new Date(String(d.fecha || '').slice(0, 10) + 'T12:00:00');

      // ---- Comprobaciones: si algo falla, se deja para revisión manual ----
      const problemas = [];
      if (!proveedor) problemas.push('sin proveedor');
      if (!(total > 0)) problemas.push('sin total');
      if (isNaN(fecha.getTime())) problemas.push('fecha ilegible');
      else if (Utilities.formatDate(fecha, zona, 'yyyy-MM-dd') > Utilities.formatDate(hoy, zona, 'yyyy-MM-dd')) problemas.push('fecha futura');
      if (base > 0 && Math.abs(base + iva - total) > 0.05) problemas.push('base + IVA no cuadra con el total');
      if (!(base > 0)) { base = Math.round(total / 1.21 * 100) / 100; iva = Math.round((total - base) * 100) / 100; }

      const fechaTxt = isNaN(fecha.getTime()) ? '' : Utilities.formatDate(fecha, zona, 'yyyy-MM-dd');
      const duplicado = existentes.some(f => {
        const fFecha = f[0] instanceof Date ? Utilities.formatDate(f[0], zona, 'yyyy-MM-dd') : String(f[0]);
        return (numero && String(f[3]).indexOf(numero) !== -1) ||
               (Math.abs(aNumero_(f[6]) - total) < 0.01 && fFecha === fechaTxt);
      });
      if (duplicado) problemas.push('posible duplicado (ya hay un gasto igual en la hoja)');

      if (problemas.length) {
        anotarAccion_({ tipo: 'revisar', archivo: nombre, motivo: problemas.join(', '), enlace: archivo.getUrl() });
        continue;
      }

      // ---- Archivar en AÑO / TRIMESTRE / GASTOS ----
      const carpetaAnio = obtenerCarpeta_(String(fecha.getFullYear()), DriveApp.getFolderById(ID_CARPETA_PRINCIPAL));
      const carpetaTrim = obtenerCarpeta_('T' + (Math.floor(fecha.getMonth() / 3) + 1), carpetaAnio);
      const carpetaGastos = obtenerCarpeta_('GASTOS', carpetaTrim);
      archivo.moveTo(carpetaGastos);

      const concepto = String(d.concepto || '').trim() + (numero ? ` (Fra. ${numero})` : '');
      const fila = [
        fechaTxt,
        Utilities.formatDate(hoy, zona, 'HH:mm:ss'),
        proveedor,
        concepto,
        Math.round(base * 100) / 100,
        Math.round(iva * 100) / 100,
        Math.round(total * 100) / 100,
        archivo.getUrl()
      ];
      hoja.appendRow(fila);
      existentes.push(fila);

      anotarAccion_({
        tipo: 'registrada', archivo: nombre, enlace: archivo.getUrl(),
        detalle: `${proveedor} · ${concepto} · ${total.toFixed(2).replace('.', ',')} € · fra. ${Utilities.formatDate(fecha, zona, 'dd/MM')}`
      });
    } catch (e) {
      anotarAccion_({ tipo: 'revisar', archivo: nombre, motivo: 'no se pudo leer (' + e.message + ')', enlace: archivo.getUrl() });
    }
  }
}


function leerFacturaGemini_(clave, bytes, tipo) {
  const respuesta = UrlFetchApp.fetch(
    `https://generativelanguage.googleapis.com/v1beta/models/${MODELO_GEMINI}:generateContent`,
    {
      method: 'post',
      contentType: 'application/json',
      headers: { 'x-goog-api-key': clave },
      muteHttpExceptions: true,
      payload: JSON.stringify({
        contents: [{ parts: [
          { text: INSTRUCCIONES_LECTURA },
          { inline_data: { mime_type: tipo, data: Utilities.base64Encode(bytes) } }
        ] }],
        generationConfig: { responseMimeType: 'application/json', temperature: 0 }
      })
    }
  );
  if (respuesta.getResponseCode() !== 200) {
    throw new Error('Gemini respondió ' + respuesta.getResponseCode());
  }
  const texto = JSON.parse(respuesta.getContentText()).candidates[0].content.parts[0].text;
  return JSON.parse(texto);
}


function anotarAccion_(accion) {
  const props = PropertiesService.getScriptProperties();
  const lista = JSON.parse(props.getProperty('ACCIONES_PARA_RESUMEN') || '[]');
  lista.push(accion);
  props.setProperty('ACCIONES_PARA_RESUMEN', JSON.stringify(lista.slice(-60)));
}


function obtenerCarpeta_(nombre, padre) {
  const it = padre.getFoldersByName(nombre);
  return it.hasNext() ? it.next() : padre.createFolder(nombre);
}


function aNumero_(v) {
  if (typeof v === 'number') return v;
  const t = String(v || '').replace(/[€\s]/g, '');
  return parseFloat(t.indexOf(',') !== -1 ? t.replace(/\./g, '').replace(',', '.') : t) || 0;
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

  // Acciones del asistente
  const acciones = JSON.parse(props.getProperty('ACCIONES_PARA_RESUMEN') || '[]');
  const registradas = acciones.filter(a => a.tipo === 'registrada');
  const aRevisar = acciones.filter(a => a.tipo === 'revisar');
  const enlaceA = a => a.enlace ? `<a href="${a.enlace}">${esc(a.archivo)}</a>` : esc(a.archivo);

  html += `<h3 style="margin:16px 0 6px">🤖 Acciones del asistente</h3>` +
    (registradas.length
      ? `<div>Facturas registradas automáticamente: <b>${registradas.length}</b></div>` +
        '<ul style="padding-left:18px;margin:4px 0">' +
        registradas.map(a => `<li>✅ ${esc(a.detalle)} · ${enlaceA(a)}</li>`).join('') + '</ul>'
      : '<div style="color:#999">Ninguna factura registrada</div>') +
    (aRevisar.length
      ? `<div style="margin-top:6px;color:#b45309"><b>⚠️ Necesitan tu revisión: ${aRevisar.length}</b></div>` +
        '<ul style="padding-left:18px;margin:4px 0">' +
        aRevisar.map(a => `<li>${enlaceA(a)} — ${esc(a.motivo)}</li>`).join('') + '</ul>'
      : '');

  // Gastos registrados en la hoja desde el último resumen
  const hojaGastos = SpreadsheetApp.openById(ID_HOJA_CONTABILIDAD).getSheetByName('GASTOS');
  const ultimaFila = hojaGastos.getLastRow();
  const filaAnterior = Number(props.getProperty('ULTIMA_FILA_GASTOS') || ultimaFila);
  const nuevos = ultimaFila > filaAnterior
    ? hojaGastos.getRange(filaAnterior + 1, 1, ultimaFila - filaAnterior, 7).getValues()
    : [];
  const aNumero = v => typeof v === 'number' ? v : (parseFloat(String(v).replace(',', '.')) || 0);
  const totalGastos = nuevos.reduce((suma, f) => suma + aNumero(f[6]), 0);
  const euros = n => n.toFixed(2).replace('.', ',') + ' €';
  const fechaTexto = v => v instanceof Date ? Utilities.formatDate(v, zona, 'dd/MM') : String(v);

  html += `<h3 style="margin:16px 0 6px">💸 Gastos registrados (${nuevos.length})</h3>` +
    (nuevos.length
      ? '<ul style="padding-left:18px;margin:0">' + nuevos.map(f =>
          `<li style="margin-bottom:4px"><b>${esc(f[2])}</b> · ${esc(f[3])} · ` +
          `${euros(aNumero(f[6]))} <span style="color:#777">· fra. ${fechaTexto(f[0])}</span></li>`
        ).join('') + '</ul>' +
        `<div style="margin-top:4px">Total: <b>${euros(totalGastos)}</b></div>`
      : '<div style="color:#999">Ninguno desde el último resumen</div>');

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
  props.setProperty('ULTIMA_FILA_GASTOS', String(ultimaFila));
  props.setProperty('ACCIONES_PARA_RESUMEN', '[]');
}


function obtenerEtiqueta_(nombre) {
  return GmailApp.getUserLabelByName(nombre) || GmailApp.createLabel(nombre);
}

function limpiar_(texto) {
  return texto.replace(/[\\/:*?"<>|]/g, '').slice(0, 40);
}
