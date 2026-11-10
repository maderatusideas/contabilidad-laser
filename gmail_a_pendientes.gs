/**
 * MADERA TUS IDEAS · Facturas del correo → FACTURAS PENDIENTES
 *
 * Cada día revisa Gmail, guarda los adjuntos de las facturas en la
 * carpeta "FACTURAS PENDIENTES" de Drive y marca el correo con la
 * etiqueta "Facturas/Procesada" para no repetirlo nunca.
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
    .filter(t => t.getHandlerFunction() === 'recogerFacturas')
    .forEach(t => ScriptApp.deleteTrigger(t));

  ScriptApp.newTrigger('recogerFacturas')
    .timeBased()
    .everyDays(1)
    .atHour(0)
    .inTimezone('Europe/Madrid')
    .create();

  recogerFacturas();
  Logger.log('✅ Instalado. Se revisará el correo cada día hacia las 00:00.');
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
    (desde ? `after:${desde} ` : '') +
    `(${PALABRAS} OR label:${ETIQUETA_RECOGER.replace('/', '-')})`;

  const hilos = GmailApp.search(consulta, 0, 50);
  let guardados = 0;

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

        carpeta
          .createFile(adjunto.copyBlob())
          .setName(`${fecha} ${remitente} - ${adjunto.getName()}`);
        guardados++;
      });
    });

    hilo.addLabel(procesada);
    hilo.removeLabel(recoger);
  });

  Logger.log(`Facturas guardadas en PENDIENTES: ${guardados}`);
}


function obtenerEtiqueta_(nombre) {
  return GmailApp.getUserLabelByName(nombre) || GmailApp.createLabel(nombre);
}

function limpiar_(texto) {
  return texto.replace(/[\\/:*?"<>|]/g, '').slice(0, 40);
}
