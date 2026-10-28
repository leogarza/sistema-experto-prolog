// Selector de materias con arrastrar y soltar.
//
// Modelo: cada materia vive en UNA sola caja — catálogo, "ya cursaste" o
// "quieres cursar". Se mueve con arrastre (drag & drop) o con un clic, que
// la va rotando: catálogo → quieres cursar → ya cursaste → catálogo.
// La selección se guarda en localStorage y el catálogo sale de GET /materias.
// El veredicto de seriación y la semana la pinta Prolog (/revisar,
// /horario): aquí no se calcula nada de eso, solo se muestra.

(() => {
  'use strict';

  const LLAVE = 'materias:seleccion-v1';

  // los dias que el prolog manda en horario/5 (inscripcion.pl: dias/1)
  const DIAS = ['lun', 'mar', 'mie', 'jue', 'vie'];

  const estado = {
    materias: new Map(), // clave -> {clave, nombre, creditos, semestre, tipo, prerrequisitos}
    orden: [],           // claves en el orden del plan, para listar el catálogo
    cursadas: new Set(),
    deseadas: new Set(),
    filtro: '',
  };

  const cajas = {
    catalogo: {
      el: document.querySelector('.caja-catalogo'),
      lista: document.getElementById('lista-catalogo'),
      vacio: document.getElementById('vacio-catalogo'),
      contador: document.getElementById('cont-catalogo'),
    },
    cursadas: {
      el: document.querySelector('.caja-cursadas'),
      lista: document.getElementById('lista-cursadas'),
      vacio: document.getElementById('vacio-cursadas'),
      contador: document.getElementById('cont-cursadas'),
    },
    deseadas: {
      el: document.querySelector('.caja-deseadas'),
      lista: document.getElementById('lista-deseadas'),
      vacio: document.getElementById('vacio-deseadas'),
      contador: document.getElementById('cont-deseadas'),
    },
  };

  const limpiarEl = document.getElementById('limpiar');
  const busquedaEl = document.getElementById('busqueda');
  const revisarEl = document.getElementById('revisar');
  const veredictoEl = document.getElementById('veredicto');

  // panel del horario sugerido
  const generarEl = document.getElementById('generar');
  const preferenciaEl = document.getElementById('preferencia');
  const esperandoEl = document.getElementById('esperando-horario');
  const tiempoHorarioEl = document.getElementById('tiempo-horario');
  const notaEsperaEl = document.getElementById('nota-espera');
  const resumenHorarioEl = document.getElementById('resumen-horario');
  const semanaEl = document.getElementById('semana');
  const errorHorarioEl = document.getElementById('error-horario');
  const vacioHorarioEl = document.getElementById('vacio-horario');

  // navegacion entre las sugerencias del motor
  const navegadorEl = document.getElementById('navegador');
  const opcionIndiceEl = document.getElementById('opcion-indice');
  const opcionAnteriorEl = document.getElementById('opcion-anterior');
  const opcionSiguienteEl = document.getElementById('opcion-siguiente');

  let arrastrando = null;   // clave que se está arrastrando ahora mismo
  let cargandoHorario = false; // hay una peticion de horario en el aire
  let relojEspera = null;      // contador de segundos del spinner
  let sugerencias = [];        // [{horario, resumen}, ...] del prolog
  let opcionActual = 0;        // cual de esas se esta viendo (0 = mejor)

  // ---------------------------------------------------------------- carga

  async function cargar() {
    try {
      const resp = await fetch('/materias');
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const datos = await resp.json();
      if (!datos.ok || !Array.isArray(datos.materias)) {
        throw new Error(datos.mensaje || 'el servidor no mandó el catálogo');
      }
      const materias = datos.materias.slice().sort(
        (a, b) => a.semestre - b.semestre || a.nombre.localeCompare(b.nombre, 'es')
      );
      for (const m of materias) {
        estado.materias.set(m.clave, m);
        estado.orden.push(m.clave);
      }
      restaurar();
      pintar();
    } catch (e) {
      cajas.catalogo.vacio.hidden = false;
      cajas.catalogo.vacio.textContent = 'No pude cargar el catálogo: ' + e.message;
      cajas.catalogo.contador.textContent = 'error';
    }
  }

  // ------------------------------------------------------- selección

  // mueve la materia a la caja indicada (sacándola de cualquier otra)
  function mover(clave, destino) {
    if (!estado.materias.has(clave)) return;
    estado.cursadas.delete(clave);
    estado.deseadas.delete(clave);
    if (destino === 'cursadas') estado.cursadas.add(clave);
    else if (destino === 'deseadas') estado.deseadas.add(clave);
    guardar();
    pintar();
  }

  // ciclo del clic: catálogo → deseadas → cursadas → catálogo
  function ciclar(clave) {
    if (estado.deseadas.has(clave)) mover(clave, 'cursadas');
    else if (estado.cursadas.has(clave)) mover(clave, 'catalogo');
    else mover(clave, 'deseadas');
  }

  function dondeEsta(clave) {
    if (estado.cursadas.has(clave)) return 'cursadas';
    if (estado.deseadas.has(clave)) return 'deseadas';
    return 'catalogo';
  }

  function nombreDe(clave) {
    const m = estado.materias.get(clave);
    return m ? m.nombre : clave;
  }

  // ------------------------------------------------- persistencia local

  function guardar() {
    try {
      localStorage.setItem(LLAVE, JSON.stringify({
        cursadas: [...estado.cursadas],
        deseadas: [...estado.deseadas],
      }));
    } catch (_) { /* modo privado: se vive sin recuerdo */ }
  }

  function restaurar() {
    try {
      const crudo = JSON.parse(localStorage.getItem(LLAVE) || 'null');
      if (!crudo) return;
      for (const c of crudo.cursadas || []) {
        if (estado.materias.has(c)) estado.cursadas.add(c);
      }
      for (const c of crudo.deseadas || []) {
        // una materia no puede estar en las dos cajas: manda "cursadas"
        if (estado.materias.has(c) && !estado.cursadas.has(c)) estado.deseadas.add(c);
      }
    } catch (_) { /* lo que haya guardado no sirve, se empieza limpio */ }
  }

  // ------------------------------------------------------------ pintar

  function pintar() {
    pintarCatalogo();
    pintarCaja('cursadas');
    pintarCaja('deseadas');
    limpiarEl.hidden = estado.cursadas.size + estado.deseadas.size === 0;
    revisarEl.disabled = estado.deseadas.size === 0;
    generarEl.disabled = cargandoHorario || estado.deseadas.size === 0;
    // el prolog es el unico que opina sobre prerrequisitos y horarios: si
    // la seleccion cambio, lo que el dijo antes ya no describe las cajas
    veredictoEl.hidden = true;
    if (!cargandoHorario) reposoHorario();
  }

  function clavesVisibles() {
    const texto = normaliza(estado.filtro);
    return estado.orden.filter((clave) => {
      if (dondeEsta(clave) !== 'catalogo') return false;
      if (!texto) return true;
      const m = estado.materias.get(clave);
      return normaliza(m.nombre).includes(texto) || clave.includes(texto);
    });
  }

  function pintarCatalogo() {
    const claves = clavesVisibles();
    llenar(cajas.catalogo, claves);
    const total = estado.orden.length;
    cajas.catalogo.contador.textContent = claves.length === total
      ? `${total} materias`
      : `${claves.length} / ${total}`;
    if (claves.length === 0) {
      cajas.catalogo.vacio.textContent = estado.filtro
        ? `Ninguna materia coincide con «${estado.filtro}»`
        : 'Todas las materias están en otra caja';
    }
  }

  function pintarCaja(nombre) {
    const enCaja = nombre === 'cursadas' ? estado.cursadas : estado.deseadas;
    const claves = estado.orden.filter((c) => enCaja.has(c));
    llenar(cajas[nombre], claves);
    let creditos = 0;
    for (const c of claves) creditos += estado.materias.get(c).creditos;
    cajas[nombre].contador.textContent =
      `${claves.length} ${claves.length === 1 ? 'materia' : 'materias'} · ${fmt(creditos)} cr`;
    if (claves.length === 0) {
      cajas[nombre].vacio.textContent = nombre === 'cursadas'
        ? 'Arrastra aquí las materias que ya aprobaste'
        : 'Arrastra aquí las materias de este periodo';
    }
  }

  // llena una caja con sus fichas y muestra/esconde el mensaje vacío
  function llenar(caja, claves) {
    const fragmento = document.createDocumentFragment();
    for (const clave of claves) fragmento.appendChild(ficha(clave));
    caja.lista.replaceChildren(fragmento);
    caja.vacio.hidden = claves.length > 0;
  }

  function ficha(clave) {
    const m = estado.materias.get(clave);
    const li = document.createElement('li');
    li.className = 'materia';
    li.dataset.clave = clave;
    li.draggable = true;
    li.tabIndex = 0;
    li.title = 'Arrástrala a otra caja, o haz clic para moverla';

    const renglon = document.createElement('div');
    renglon.className = 'materia-renglon';

    const nombre = document.createElement('span');
    nombre.className = 'materia-nombre';
    nombre.textContent = m.nombre;

    const datos = document.createElement('span');
    datos.className = 'materia-datos';
    datos.appendChild(badge(`${fmt(m.creditos)} cr`));
    datos.appendChild(badge(`S${m.semestre}`, 'badge-semestre'));
    if (m.tipo === 'optativa') datos.appendChild(badge('optativa', 'badge-optativa'));

    renglon.append(nombre, datos);
    li.appendChild(renglon);
    return li;
  }

  function badge(texto, clase) {
    const b = document.createElement('span');
    b.className = 'badge' + (clase ? ' ' + clase : '');
    b.textContent = texto;
    return b;
  }

  // circulito de espera, el mismo para el boton de revisar y el panel
  function spinnerEl() {
    const s = document.createElement('span');
    s.className = 'spinner';
    s.setAttribute('aria-hidden', 'true');
    return s;
  }

  // ------------------------------------------------- panel del horario

  // el panel vuelve a su estado reposo: mensaje vacio si no hay deseadas,
  // invitacion a generar si las hay. el horario viejo se apaga aqui, ya
  // no describe la seleccion actual
  function reposoHorario() {
    sugerencias = [];
    opcionActual = 0;
    navegadorEl.hidden = true;
    resumenHorarioEl.hidden = true;
    semanaEl.hidden = true;
    errorHorarioEl.hidden = true;
    vacioHorarioEl.hidden = false;
    vacioHorarioEl.textContent = estado.deseadas.size === 0
      ? 'Primero pon materias en “Quieres cursar”'
      : 'Elige turno y da clic en “Generar horario”';
    if (!cargandoHorario) {
      generarEl.disabled = estado.deseadas.size === 0;
      preferenciaEl.disabled = false;
    }
  }

  function iniciaEsperaHorario() {
    cargandoHorario = true;
    generarEl.disabled = true;
    preferenciaEl.disabled = true;
    navegadorEl.hidden = true;
    vacioHorarioEl.hidden = true;
    resumenHorarioEl.hidden = true;
    semanaEl.hidden = true;
    errorHorarioEl.hidden = true;

    // el aviso de mixto sale solo ahi, porque es el caso que tarda
    notaEsperaEl.hidden = preferenciaEl.value !== 'mixto';
    tiempoHorarioEl.textContent = '0 s';
    esperandoEl.hidden = false;
    const t0 = Date.now();
    relojEspera = setInterval(() => {
      tiempoHorarioEl.textContent = Math.round((Date.now() - t0) / 1000) + ' s';
    }, 1000);
  }

  function terminaEsperaHorario() {
    cargandoHorario = false;
    clearInterval(relojEspera);
    relojEspera = null;
    esperandoEl.hidden = true;
    preferenciaEl.disabled = false;
    generarEl.disabled = estado.deseadas.size === 0;
  }

  // pinta la semana que devolvio el prolog: una columna por dia y un
  // bloque por clase, posicionado segun sus minutos
  function pintaSemana(datos) {
    const horario = datos.horario || [];
    if (horario.length === 0) return false;

    // rango de horas: de la primera clase a la ultima, redondeado afuera
    let ini = 24 * 60;
    let fin = 0;
    for (const m of horario) {
      for (const b of m.bloques) {
        ini = Math.min(ini, aMinutos(b.inicio));
        fin = Math.max(fin, aMinutos(b.fin));
      }
    }
    ini = Math.floor(ini / 60) * 60;
    fin = Math.ceil(fin / 60) * 60;
    const PPM = 1.15; // px por minuto, igual que --ppm en estilos.css
    const alto = (fin - ini) * PPM;

    semanaEl.replaceChildren();

    // cabecera: casillon vacio + los cinco dias
    const esquina = document.createElement('div');
    esquina.className = 'esquina';
    semanaEl.appendChild(esquina);
    for (const d of DIAS) {
      const cab = document.createElement('div');
      cab.className = 'dia-cab';
      cab.textContent = d[0].toUpperCase() + d.slice(1);
      semanaEl.appendChild(cab);
    }

    // columna de las horas
    const horas = document.createElement('div');
    horas.className = 'horas';
    horas.style.height = alto + 'px';
    for (let m = ini; m <= fin; m += 60) {
      const lab = document.createElement('span');
      lab.className = 'hora-etiqueta';
      lab.style.top = ((m - ini) * PPM) + 'px';
      lab.textContent = Math.floor(m / 60) + ':00';
      horas.appendChild(lab);
    }
    semanaEl.appendChild(horas);

    // cinco columnas con los bloques de cada dia
    const porDia = new Map(DIAS.map((d) => [d, []]));
    for (const m of horario) {
      for (const b of m.bloques) {
        if (porDia.has(b.dia)) porDia.get(b.dia).push({ m, b });
      }
    }
    for (const d of DIAS) {
      const col = document.createElement('div');
      col.className = 'col';
      col.style.height = alto + 'px';
      for (const { m, b } of porDia.get(d)) {
        col.appendChild(bloqueEl(m, b, ini, PPM));
      }
      semanaEl.appendChild(col);
    }

    pintaResumenHorario(datos.resumen);
    semanaEl.hidden = false;
    return true;
  }

  // guarda las sugerencias del motor y muestra la primera (la mejor).
  // regresa false si no hay con que armar la semana
  function recibeSugerencias(datos) {
    sugerencias = Array.isArray(datos.sugerencias) && datos.sugerencias.length
      ? datos.sugerencias
      : [{ horario: datos.horario, resumen: datos.resumen }];
    opcionActual = 0;
    const opcion = sugerencias[0];
    if (!opcion || !pintaSemana({ ...opcion })) {
      sugerencias = [];
      return false;
    }
    navegadorEl.hidden = sugerencias.length <= 1;
    opcionIndiceEl.textContent = `1 / ${sugerencias.length}`;
    opcionAnteriorEl.disabled = true;
    opcionSiguienteEl.disabled = sugerencias.length <= 1;
    return true;
  }

  // repinta la rejilla con la sugerencia seleccionada y actualiza las
  // flechitas del navegador
  function pintaOpcionActual() {
    const opcion = sugerencias[opcionActual];
    if (!opcion || !pintaSemana({ ...opcion })) return;
    navegadorEl.hidden = sugerencias.length <= 1;
    opcionIndiceEl.textContent = `${opcionActual + 1} / ${sugerencias.length}`;
    opcionAnteriorEl.disabled = opcionActual === 0;
    opcionSiguienteEl.disabled = opcionActual === sugerencias.length - 1;
  }

  function cambiaOpcion(paso) {
    const destino = opcionActual + paso;
    if (destino < 0 || destino >= sugerencias.length) return;
    opcionActual = destino;
    pintaOpcionActual();
  }

  function bloqueEl(m, b, ini, PPM) {
    const el = document.createElement('div');
    el.className = 'bloque';
    // un color por materia, para que las dos clases de la misma se vean
    el.style.setProperty('--c', colorDe(m.materia));
    el.style.top = ((aMinutos(b.inicio) - ini) * PPM) + 'px';
    el.style.height = ((aMinutos(b.fin) - aMinutos(b.inicio)) * PPM - 2) + 'px';

    const nombre = document.createElement('strong');
    nombre.textContent = m.nombre;
    const meta = document.createElement('span');
    meta.className = 'bloque-meta';
    meta.textContent = `${b.inicio}–${b.fin} · ${m.grupo}`;
    el.append(nombre, meta);
    el.title = `${m.nombre} — grupo ${m.grupo} (${m.turno})`;
    return el;
  }

  function pintaResumenHorario(r) {
    resumenHorarioEl.replaceChildren();
    if (!r) return;
    const items = [
      ['Materias', r.materias],
      ['Huecos', r.huecos_minutos + ' min'],
      ['Termina', r.termina],
      ['Matutinas', r.matutinas],
      ['Vespertinas', r.vespertinas],
    ];
    for (const [texto, valor] of items) {
      const chip = document.createElement('span');
      chip.className = 'chip-resumen';
      chip.append(texto + ' ');
      const b = document.createElement('b');
      b.textContent = valor;
      chip.appendChild(b);
      if (texto === 'Huecos' && r.huecos_minutos === 0) {
        chip.classList.add('chip-ok');
      }
      resumenHorarioEl.appendChild(chip);
    }
    resumenHorarioEl.hidden = false;
  }

  function aMinutos(hhmm) {
    const [h, m] = hhmm.split(':').map(Number);
    return h * 60 + m;
  }

  // color estable por materia: el mismo siempre, salga en la rejilla o
  // en la lista de bloques
  function colorDe(clave) {
    let h = 0;
    for (let i = 0; i < clave.length; i++) h = (h * 31 + clave.charCodeAt(i)) >>> 0;
    return `hsl(${h % 360} 55% 42%)`;
  }

  function normaliza(s) {
    return s.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  }

  function fmt(n) {
    return String(n);
  }

  // ------------------------------------------------------- arrastrar

  function iniciarArrastre(e) {
    const ficha = e.target.closest('.materia');
    if (!ficha) return;
    arrastrando = ficha.dataset.clave;
    e.dataTransfer.setData('text/plain', arrastrando);
    e.dataTransfer.effectAllowed = 'move';
    ficha.classList.add('arrastrando');
    document.body.classList.add('arrastrando');
  }

  function terminarArrastre() {
    arrastrando = null;
    document.body.classList.remove('arrastrando');
    document.querySelectorAll('.arrastrando').forEach((el) => el.classList.remove('arrastrando'));
    document.querySelectorAll('.sobre').forEach((el) => el.classList.remove('sobre'));
  }

  function soltar(e, caja) {
    e.preventDefault();
    const clave = e.dataTransfer.getData('text/plain') || arrastrando;
    if (clave) mover(clave, caja);
    terminarArrastre();
  }

  // ------------------------------------------------------------ eventos

  for (const [nombre, caja] of Object.entries(cajas)) {
    // arrastre: sale de cualquier ficha de cualquier caja
    caja.lista.addEventListener('dragstart', iniciarArrastre);
    caja.lista.addEventListener('dragend', terminarArrastre);

    // clic y teclado: rotan la materia de caja
    caja.lista.addEventListener('click', (e) => {
      const ficha = e.target.closest('.materia');
      if (ficha) ciclar(ficha.dataset.clave);
    });
    caja.lista.addEventListener('keydown', (e) => {
      if (e.key !== 'Enter' && e.key !== ' ') return;
      const ficha = e.target.closest('.materia');
      if (ficha) {
        e.preventDefault();
        ciclar(ficha.dataset.clave);
      }
    });

    // zona de suelta
    caja.el.addEventListener('dragover', (e) => {
      if (!arrastrando) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      caja.el.classList.add('sobre');
    });
    caja.el.addEventListener('dragleave', (e) => {
      if (!caja.el.contains(e.relatedTarget)) caja.el.classList.remove('sobre');
    });
    caja.el.addEventListener('drop', (e) => soltar(e, nombre));
  }

  document.addEventListener('dragend', terminarArrastre);

  busquedaEl.addEventListener('input', () => {
    estado.filtro = busquedaEl.value.trim();
    pintarCatalogo();
  });

  limpiarEl.addEventListener('click', () => {
    estado.cursadas.clear();
    estado.deseadas.clear();
    guardar();
    pintar();
  });

  // ------------------------------------------------ revisar con prolog

  // la seleccion actual en texto, para saber despues si cambio mientras
  // esperabamos la respuesta del motor
  function seleccionActual() {
    return JSON.stringify([
      estado.orden.filter((c) => estado.cursadas.has(c)),
      estado.orden.filter((c) => estado.deseadas.has(c)),
    ]);
  }

  // manda la seleccion a POST /revisar y pinta lo que contesta el motor.
  // aqui NO se calcula nada: prerrequisitos, carga y visto bueno los
  // decide el prolog, la interfaz solo los muestra
  revisarEl.addEventListener('click', async () => {
    const deseadas = estado.orden.filter((c) => estado.deseadas.has(c));
    if (deseadas.length === 0) return;

    const cursadas = estado.orden.filter((c) => estado.cursadas.has(c));
    const pedida = seleccionActual();
    revisarEl.disabled = true;
    const textoPrevio = revisarEl.textContent;
    revisarEl.replaceChildren(spinnerEl(),
                              document.createTextNode(' Prolog pensando…'));
    veredictoEl.hidden = true;

    try {
      const resp = await fetch('/revisar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cursadas, deseadas }),
      });
      const datos = await resp.json().catch(() => null);
      // si mientras esperaba movieron materias, este veredicto ya no
      // corresponde a lo que hay en las cajas: se bota sin pintar
      if (seleccionActual() !== pedida) return;
      if (!datos) {
        pintarVeredicto(veredictoEl, false, 'El servidor contestó algo que no es JSON (HTTP ' + resp.status + ')');
      } else if (resp.ok && datos.ok) {
        pintarVeredicto(veredictoEl, datos.puede_inscribir, null, datos);
      } else {
        // errores del motor (422: repetidas, ...) y de Go
        pintarVeredicto(veredictoEl, false, datos.mensaje || datos.error || 'HTTP ' + resp.status, datos);
      }
    } catch (e) {
      if (seleccionActual() === pedida) {
        pintarVeredicto(veredictoEl, false, 'No pude hablar con el servidor: ' + e.message);
      }
    } finally {
      revisarEl.textContent = textoPrevio;
      revisarEl.disabled = estado.deseadas.size === 0;
    }
  });

  function pintarVeredicto(destino, puede, mensaje, datos) {
    destino.replaceChildren();
    destino.classList.toggle('veredicto-ok', !!puede);
    destino.classList.toggle('veredicto-mal', !puede);

    const titulo = document.createElement('p');
    titulo.className = 'veredicto-titulo';
    if (puede) {
      titulo.textContent = '✓ Sí puedes inscribir';
    } else {
      titulo.textContent = mensaje ? '✗ ' + mensaje : '✗ No puedes inscribir';
    }
    destino.appendChild(titulo);

    // el reporte por materia solo viene cuando el motor contestó bien
    if (datos && Array.isArray(datos.reporte)) {
      const conFallos = datos.reporte.filter((f) => f.estado !== 'ok');
      if (conFallos.length > 0) {
        const ul = document.createElement('ul');
        for (const fila of conFallos.slice(0, 5)) {
          const li = document.createElement('li');
          li.textContent = fila.estado === 'desconocida'
            ? `${fila.nombre} no existe en el plan`
            : `Falta ${fila.faltantes.map(nombreDe).join(', ')} para ${fila.nombre}`;
          ul.appendChild(li);
        }
        if (conFallos.length > 5) {
          const li = document.createElement('li');
          li.textContent = `…y ${conFallos.length - 5} materias más`;
          ul.appendChild(li);
        }
        destino.appendChild(ul);
      } else if (puede && datos.carga) {
        const detalle = document.createElement('p');
        detalle.textContent = `${datos.carga.cantidad} materias, carga ${datos.carga.clase}`;
        destino.appendChild(detalle);
      }
    }
    destino.hidden = false;
  }

  // ------------------------------------------- generar horario con prolog

  // manda la seleccion a POST /horario y pinta la semana que arma el
  // motor. puede tardar (mixto con muchas materias recorre mucho arbol),
  // por eso el spinner con contador y por eso se descarta la respuesta
  // si la seleccion cambio mientras esperabamos
  generarEl.addEventListener('click', async () => {
    const deseadas = estado.orden.filter((c) => estado.deseadas.has(c));
    if (deseadas.length === 0) return;

    const cursadas = estado.orden.filter((c) => estado.cursadas.has(c));
    const pedida = seleccionActual();
    iniciaEsperaHorario();

    try {
      const resp = await fetch('/horario', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          cursadas,
          deseadas,
          preferencia: preferenciaEl.value,
        }),
      });
      const datos = await resp.json().catch(() => null);
      if (seleccionActual() !== pedida) return;
      if (!datos) {
        pintaErrorHorario('El servidor contestó algo que no es JSON (HTTP ' + resp.status + ')');
      } else if (resp.ok && datos.ok) {
        if (recibeSugerencias(datos)) return;
        pintaErrorHorario('El prolog no devolvió bloques para armar la semana');
      } else {
        // prerrequisitos, carga_maxima, sin_solucion, preferencia_invalida...
        pintaErrorHorario(datos.mensaje || datos.error || 'HTTP ' + resp.status,
                          datos);
      }
    } catch (e) {
      if (seleccionActual() === pedida) {
        pintaErrorHorario('No pude hablar con el servidor: ' + e.message);
      }
    } finally {
      terminaEsperaHorario();
      // si la respuesta se descarto (la seleccion cambio), el panel vuelve
      // a su mensaje de reposo; si se pinto, esto no le hace nada
      if (semanaEl.hidden && errorHorarioEl.hidden && !cargandoHorario) {
        reposoHorario();
      }
    }
  });

  function pintaErrorHorario(mensaje, datos) {
    sugerencias = [];
    opcionActual = 0;
    navegadorEl.hidden = true;
    vacioHorarioEl.hidden = true;
    resumenHorarioEl.hidden = true;
    semanaEl.hidden = true;
    pintarVeredicto(errorHorarioEl, false, mensaje, datos);
  }

  opcionAnteriorEl.addEventListener('click', () => cambiaOpcion(-1));
  opcionSiguienteEl.addEventListener('click', () => cambiaOpcion(1));

  cargar();
})();
