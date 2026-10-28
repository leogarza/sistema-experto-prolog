% ------------------------------------------------------------------------
% interfaz json para conectar el sistema de inscripcion a otro programa
%
% como se corre:
%   swipl -q -s interfaz.pl -g principal -t halt
%
% como se funciona:
%   - le llega una peticion json por el stdin, un objeto por linea
%     (si el otro programa lo manda formateado en varios renglones
%     tambien se aguanta, aqui voy juntando hasta que deje de tronar)
%   - le contesto con UNA linea de json compacto por el stdout y la
%     vuelvo a leer, asi hasta que cierren el stdin ahi ya me salgo
%   - en el stdout nomas cabe el json: los avisos feos del prolog van
%     al stderr, si no el otro programa se asusta al parsear
%
% peticiones (accion + listas de claves, ej "calculo"):
%   {"accion":"revisar", "cursadas":["calculo"], "deseadas":["bases_de_datos"]}
%   {"accion":"horario", "cursadas":[...], "deseadas":[...], "preferencia":"matutino"}
%   {"accion":"materias"}
%
% preferencia: matutino | vespertino | mixto (si no viene, mixto)
% toda respuesta trae "ok": true/false y si es false el "error" dice
% cual fue el pedo ("prerrequisitos", "carga_maxima", "sin_grupo", ...)
% ------------------------------------------------------------------------

% cargo el prolog de ahi al lado, inscripcion.pl ya trae los datos.
% encoding(utf8) explicito: con locale C (contenedores) swipl leeria el
% archivo como ascii y romperia todo lo que traiga acentos
:- prolog_load_context(directory, Dir),
   atom_concat(Dir, '/inscripcion.pl', Base),
   load_files(Base, [encoding(utf8)]).

:- use_module(library(http/json)).
:- use_module(library(readutil)).


% ------------------------------------------------------------------------
% el ciclo de vida: leo, contesto una linea, repito
% ------------------------------------------------------------------------

principal :-
    atencion.

atencion :-
    read_line_to_string(user_input, Linea),
    (   Linea == end_of_file
        -> true
        ;   linea_vacia(Linea)
        -> atencion                      % renglones en blanco nomas me estorban
        ;   procesa(Linea),
            atencion
    ).

% si la peticion viene en varios renglones la voy juntando hasta que
% parsea, o hasta que se vea completa (llaves sin cerrar) y si ya esta
% rota pues eso se responde y que el otro se preocupe
junta(Acum, Texto) :-
    (   parse_json(Acum, _)
        -> Texto = Acum
        ;   saldo_abierto(Acum)
        -> (   read_line_to_string(user_input, Sig),
               Sig \== end_of_file
               -> ( string_concat(Acum, "\n", A1),
                    string_concat(A1, Sig, Nuevo),
                    junta(Nuevo, Texto) )
               ;  Texto = Acum
            )
        ;   Texto = Acum
    ).

procesa(Linea) :-
    junta(Linea, Texto),
    (   parse_json(Texto, D), is_dict(D)
        -> (   catch(respuesta(D, Out), E, error_de_excepcion(E, Out))
            ->  true
            ;   Out = _{ok: false, error: "error_interno",
                        mensaje: "no pude armar la respuesta"}
            ),
            manda(Out)
        ;   manda(_{ok: false, error: "json_invalido",
                    mensaje: "no entendi lo que llego por el stdin"})
    ).

parse_json(Texto, D) :-
    setup_call_cleanup(
        open_string(Texto, S),
        catch(json_read_dict(S, D), _, fail),
        close(S)).

% el saldo de llaves y corchetes que llevo sin cerrar, contando solo lo
% que esta afuera de comillas: si sigue en positivo el json viene a
% medias y vale la pena esperar otros renglones
saldo_abierto(Texto) :-
    string_chars(Texto, Chs),
    saldo(Chs, false, 0, N),
    N > 0.

saldo([], _, N, N).
saldo([C | Cs], true, N0, N) :-
    !,
    ( C == '"' -> saldo(Cs, false, N0, N) ; saldo(Cs, true, N0, N) ).
saldo([C | Cs], false, N0, N) :-
    (   C == '"'                  -> EC = true,  N1 = N0
    ;   memberchk(C, ['{', '['])  -> EC = false, N1 is N0 + 1
    ;   memberchk(C, ['}', ']'])  -> EC = false, N1 is N0 - 1
    ;                               EC = false, N1 = N0
    ),
    saldo(Cs, EC, N1, N).

linea_vacia(L) :-
    split_string(L, "", " \t\r\n", [S]),
    S == "".

manda(Out) :-
    % width(0) es el que me da una sola linea: con ancho normal este json
    % saca saltos de linea cada que se le antoja y el otro programa truena
    json_write_dict(user_output, Out, [width(0)]),
    nl(user_output),
    flush_output(user_output).

error_de_excepcion(E, Out) :-
    (   catch(message_to_string(E, M), _, fail)
        -> true
        ;  term_string(E, M)
    ),
    Out = _{ok: false, error: "excepcion", mensaje: M}.


% ------------------------------------------------------------------------
% a que responde cada accion
% ------------------------------------------------------------------------

respuesta(D, Out) :-
    (   accion_de(D, Acc)
        -> (   listas_de(D, Curs, Des)
            ->  despacha(Acc, Curs, Des, D, Out)
            ;   Out = _{ok: false, error: "parametros",
                        mensaje: "cursadas y deseadas tienen que ser listas"}
            )
        ;   Out = _{ok: false, error: "accion_invalida",
                    mensaje: "usa accion revisar, horario o materias",
                    acciones: ["revisar", "horario", "materias"]}
    ).

accion_de(D, Acc) :-
    get_dict(accion, D, V),
    a_atom(V, Acc).

listas_de(D, Curs, Des) :-
    ( get_dict(cursadas, D, C0) -> true ; C0 = [] ),
    ( get_dict(deseadas, D, D0)  -> true ; D0 = [] ),
    is_list(C0),
    is_list(D0),
    a_atomos(C0, Curs),
    a_atomos(D0, Des).

% lo que llega del json puede venir como string o como atomo, aqui lo
% uniformizo pa no batallar en cada lado
a_atom(X, A) :-
    (   atom(X)   -> A = X
    ;   string(X) -> atom_string(A, X)
    ;   fail
    ).

a_atomos(L, As) :- maplist(a_atom, L, As).

% solo la revision de prerequisitos, sin tocar horarios
despacha(revisar, Curs, Des, _, Out) :-
    (   Des == []
        -> falla_json(lista_vacia, Out)
        ;   repetidas(Des, [R | _])
        -> falla_json(materia_repetida(R), Out)
        ;   reporte_json(Curs, Des, Rep),
            length(Des, N),
            carga_de(N, Clase),
            ( puede_inscribir(Curs, Des) -> Puede = true ; Puede = false ),
            Out = _{ok: true, accion: "revisar",
                    carga: _{cantidad: N, clase: Clase},
                    reporte: Rep,
                    puede_inscribir: Puede}
    ).

% la revision mas el mejor horario sin traslapes
despacha(horario, Curs, Des, D, Out) :-
    (   ( get_dict(preferencia, D, P0) -> A0 = P0 ; A0 = mixto ),
        a_atom(A0, Pref)
        -> horario_con(Curs, Des, Pref, D, Out)
        ;   Out = _{ok: false, error: "parametros",
                    mensaje: "preferencia tiene que ser matutino, vespertino o mixto"}
    ).

% el catalogo completo: claves, nombres, creditos, seriacion y grupos,
% pa que el otro programa tenga de donde dibujar su lista
despacha(materias, _, _, _, Out) :-
    findall(F, catalogo_fila(F), Lista),
    length(Lista, N),
    Out = _{ok: true, accion: "materias", total: N, materias: Lista}.

despacha(_, _, _, _, Out) :-
    Out = _{ok: false, error: "accion_invalida",
            mensaje: "usa accion revisar, horario o materias",
            acciones: ["revisar", "horario", "materias"]}.

horario_con(Curs, Des, Pref, D, Out) :-
    % cuantas sugerencias quiere el que llama (default 5, tope 10):
    % la primera siempre es la mejor, las demas son alternativas
    (   get_dict(cantidad, D, C0), integer(C0), C0 >= 1
        -> K0 is min(C0, 10)
        ;   K0 = 5
    ),
    pedir_horarios(Curs, Des, Pref, K0, R),
    (   R = error(Cod)
        -> error_con_reporte(Cod, Curs, Des, Out)
        ;   R = ok(Sels),
            length(Des, N),
            carga_de(N, Clase),
            reporte_json(Curs, Des, Rep),
            findall(Opc,
                    ( member(Sel, Sels),
                      horario_json(Sel, H),
                      resumen_json(Sel, Rz),
                      Opc = _{horario: H, resumen: Rz} ),
                    Opciones),
            Opciones = [Primera | _],
            Primera = _{horario: H1, resumen: Rz1},
            length(Opciones, NOpc),
            Out = _{ok: true, accion: "horario", preferencia: Pref,
                    carga: _{cantidad: N, clase: Clase},
                    puede_inscribir: true,
                    reporte: Rep,
                    horario: H1,
                    resumen: Rz1,
                    sugerencias: Opciones,
                    total_sugerencias: NOpc}
    ).


% ------------------------------------------------------------------------
% armar los pedazos de la respuesta en json
% ------------------------------------------------------------------------

% el prerrequisitos trae el reporte incluido, pa que el otro programa
% sin mas le diga al alumno que es lo que le falta
error_con_reporte(prerrequisitos, Curs, Des, Out) :- !,
    reporte_json(Curs, Des, Rep),
    Out = _{ok: false, error: "prerrequisitos",
            mensaje: "faltan prerrequisitos o hay materia desconocida",
            reporte: Rep}.
error_con_reporte(Cod, _, _, Out) :-
    falla_json(Cod, Out).

falla_json(lista_vacia, _{ok: false, error: "lista_vacia",
    mensaje: "pone al menos una materia en deseadas"}).
falla_json(materia_repetida(M), _{ok: false, error: "materia_repetida",
    materia: M, mensaje: "la misma materia esta dos veces en deseadas"}).
falla_json(preferencia_invalida(P), _{ok: false, error: "preferencia_invalida",
    preferencia: P, mensaje: "usa matutino, vespertino o mixto"}).
falla_json(carga_maxima(N), _{ok: false, error: "carga_maxima",
    cantidad: N, mensaje: "mas de 7 materias es carga maxima y no es recomendable"}).
falla_json(sin_grupo(M), _{ok: false, error: "sin_grupo",
    materia: M, mensaje: "esta materia no tiene grupo este periodo"}).
falla_json(sin_solucion, _{ok: false, error: "sin_solucion",
    mensaje: "no hay combinacion de grupos sin traslapes"}).

reporte_json(Curs, Des, Rep) :-
    findall(F, (member(M, Des), estado_materia(Curs, M, E), fila_json(M, E, F)), Rep).

fila_json(M, E, F) :-
    nom(M, Nombre),
    (   E = ok(_)
        -> F = _{materia: M, nombre: Nombre, estado: "ok", faltantes: []}
        ;   E = falta_algo(_, Fal)
        -> F = _{materia: M, nombre: Nombre, estado: "faltante", faltantes: Fal}
        ;   F = _{materia: M, nombre: Nombre, estado: "desconocida", faltantes: []}
    ).

horario_json(Sel, H) :-
    findall(F, (member(sel(M, G), Sel), sel_json(M, G, F)), H).

sel_json(M, G, F) :-
    nom(M, Nombre),
    turno_grupo(G, T),
    dias(Orden),
    findall(_{dia: D, inicio: HI, fin: HF},
            ( member(D, Orden),
              horario(M, G, D, I, F2),
              hora_texto(I, HI),
              hora_texto(F2, HF) ),
            Bloques),
    F = _{materia: M, nombre: Nombre, grupo: G, turno: T, bloques: Bloques}.

resumen_json(Sel, Rz) :-
    bloques_sel(Sel, Bs),
    length(Sel, N),
    huecos_total(Bs, H),
    fin_tarde(Bs, Fin),
    min_a_hhmm(Fin, FinH),
    hora_texto(FinH, TextoFin),
    findall(1, (member(sel(_, G), Sel), turno_grupo(G, matutino)), Lm),
    length(Lm, Nm),
    findall(1, (member(sel(_, G), Sel), turno_grupo(G, vespertino)), Lv),
    length(Lv, Nv),
    Rz = _{materias: N, huecos_minutos: H, termina: TextoFin,
           matutinas: Nm, vespertinas: Nv}.

catalogo_fila(F) :-
    materia(M, Cred),
    nom(M, Nombre),
    semestre(M, Sem),
    tipo(M, Tipo),
    findall(P, prerrequisito(M, P), Ps),
    findall(G, horario(M, G, _, _, _), Gs0),
    sort(Gs0, Gs),
    F = _{clave: M, nombre: Nombre, creditos: Cred, semestre: Sem,
          tipo: Tipo, prerrequisitos: Ps, grupos: Gs}.

% 700 -> "7:00" y 1030 -> "10:30", sin estos ceros los numeros quedan feos
hora_texto(HHMM, Texto) :-
    H is HHMM // 100,
    M is HHMM mod 100,
    (   M < 10 -> format(string(Texto), '~w:0~w', [H, M])
    ;            format(string(Texto), '~w:~w', [H, M])
    ).
