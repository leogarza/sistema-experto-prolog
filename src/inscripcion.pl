% ------------------------------------------------------------------------
% inscripcion y horarios en prolog, rapido y sucio pero jala
%
% lo que hace: checa si una lista de materias que el alumno quiere inscribir
% cumple con la seriacion (comparandola contra las que ya curso) y luego
% arma un horario sin traslapes, preferiendo turno matutino o vespertino.
%
% uso basico desde swipl (parado en esta carpeta):
%   ?- [inscripcion].
%   ?- demo.                                   % prueba con ejemplo adentro
%   ?- revisar(Cursadas, Deseadas).            % reporte de prerequisitos
%   ?- puede_inscribir(Cursadas, Deseadas).    % solo true/false
%   ?- sugerir_horario(Cursadas, Deseadas, matutino, Sel).
%       preferencia: matutino | vespertino | mixto
%
% cargas: minima (4 o menos), media (7 o menos), maxima (mas de 7, fea)
%
% nota: uso findall + sort en vez de setof, porque en mi swipl el setof
% esta enfermo y con variables libres en la meta devuelve un desastre
% ------------------------------------------------------------------------

% cargo los datos usando la ruta de este archivo, asi no depende de desde
% donde lo corras
:- prolog_load_context(directory, Dir),
   atom_concat(Dir, '/datos/hechos.pl', Hechos),
   atom_concat(Dir, '/datos/horarios.pl', Horarios),
   load_files([Hechos, Horarios]).


% ------------------------------------------------------------------------
% utilidades bien basicas, todo simple
% ------------------------------------------------------------------------

% 1030 -> 630 minutos de verdad, pa que las restas de huecos no salgan
% raras (1330 a 1500 no son "170 minutos", son 90)
a_minutos(HHMM, Min) :- Min is (HHMM // 100) * 60 + (HHMM mod 100).

% minutos de vuelta a hhmm, solo para imprimir
min_a_hhmm(Min, HHMM) :- HHMM is (Min // 60) * 100 + (Min mod 60).

% nombre bonito de una materia, si no lo tiene pues el atomo y ya
nom(M, N) :- ( nombre(M, N) -> true ; N = M ).

% dias de la semana en orden normal, el findall los saca como se le antoja
dias([lun, mar, mie, jue, vie]).


% ------------------------------------------------------------------------
% carga del semestre
% ------------------------------------------------------------------------

% la maxima no es recomendable pero la dejo para poder avisar
carga_de(N, minima) :- N =< 4, !.
carga_de(N, media)  :- N > 4, N =< 7, !.
carga_de(N, maxima) :- N > 7.


% ------------------------------------------------------------------------
% revision de prerequisitos (serialización del plan osea que es serio o algo asi)
% ------------------------------------------------------------------------

% ojo con el orden: prerrequisito(Curso, Prereq) significa que para
% cursar Curso primero hay que tener Prereq (esto ya viene en hechos.pl)

% las materias que le faltan a M segun lo que ya curso el alumno
faltantes(Cursadas, M, Falt) :-
    findall(P, (prerrequisito(M, P), \+ member(P, Cursadas)), Falt).

% una materia se puede inscribir si existe y no le falta nada
inscribible(Cursadas, M) :-
    materia(M, _),
    faltantes(Cursadas, M, []).

% estado de UNA materia, esto sirve pa imprimir que paso con cada una
estado_materia(Cursadas, M, E) :-
    (   \+ materia(M, _)           -> E = desconocida(M)
    ;   faltantes(Cursadas, M, []) -> E = ok(M)
    ;   faltantes(Cursadas, M, F)  -> E = falta_algo(M, F)
    ).

% la respuesta corta: toda la lista se puede inscribir o no
puede_inscribir(Cursadas, Deseadas) :-
    Deseadas \== [],
    forall(member(M, Deseadas), inscribible(Cursadas, M)).

% materias repetidas en la lista, eso siempre es error del alumno
repetidas(Deseadas, Rep) :-
    msort(Deseadas, S),
    quita_repetidas(S, Rep).

quita_repetidas([], []).
quita_repetidas([_], []).
quita_repetidas([X, X | R], [X | Rep]) :- !, quita_repetidas([X | R], Rep).
quita_repetidas([_, Y | R], Rep)       :- quita_repetidas([Y | R], Rep).

% nombres legibles de una lista de materias, pa los mensajes
noms([], []).
noms([M | Ms], [N | Ns]) :- nom(M, N), noms(Ms, Ns).

% imprime como le fue a cada materia de la lista deseada
reporta_una(Cursadas, M) :-
    estado_materia(Cursadas, M, E),
    (   E = ok(_)
        -> ( nom(M, N), format('  [ok    ] ~w~n', [N]) )
        ;   E = falta_algo(_, F)
        -> ( nom(M, N), noms(F, NF),
             format('  [falta ] ~w le faltan: ~w~n', [N, NF]) )
        ;   format('  [???   ] ~w no existe en el plan~n', [M])
    ).

% reporte de la lista deseada. falla si la lista no se puede inscribir,
% asi lo puedes usar directo en una regla: revisar(C, D), sugerir_horario(...)
revisar(Cursadas, Deseadas) :-
    (   repetidas(Deseadas, [R | _])
        -> ( nom(R, Nr), format('materia repetida en la lista: ~w~n', [Nr]), fail )
        ;  true ),
    length(Deseadas, N),
    carga_de(N, Carga),
    format('lista de ~d materias -> carga ~w~n', [N, Carga]),
    ( Carga == maxima -> writeln('  ojo: carga maxima, no es recomendable') ; true ),
    forall(member(M, Deseadas), reporta_una(Cursadas, M)),
    (   puede_inscribir(Cursadas, Deseadas)
        -> writeln('resultado: si se puede inscribir toda la lista')
        ;  ( writeln('resultado: no se puede, checa lo de arriba'), fail )
    ).


% ------------------------------------------------------------------------
% horarios
% ------------------------------------------------------------------------

% el turno viene codificado en el grupo: (semestre)(carrera)(turno)(numero)
% 7CM1 es matutino, 7CV2 es vespertino
% si el numero trae 2 digitos el codigo crece a 5 caracteres pero el turno
% sigue en la posicion 3
turno_grupo(Grupo, Turno) :-
    atom_chars(Grupo, Chars),
    nth1(3, Chars, T),
    (   T = 'M' -> Turno = matutino
    ;   T = 'V' -> Turno = vespertino
    ;   Turno = desconocido
    ).

% cache de bloques: los horarios de un grupo ya convertidos a minutos,
% cacheados con assert para no estar haciendo findall y divisiones en cada
% nodo del arbol de busqueda (aqui esta buena parte de la velocidad)
:- dynamic cache_bg/3.

bloques_de(M, G, Bs) :-
    (   cache_bg(M, G, Bs)
        -> true
        ;   findall(bloque(D, MI, MF),
                    ( horario(M, G, D, I, F),
                      a_minutos(I, MI),
                      a_minutos(F, MF) ),
                    Bs0),
            assertz(cache_bg(M, G, Bs0)),
            Bs = Bs0
    ).

% todos los bloques de una seleccion (lista de sel(Materia, Grupo)),
% en minutos tambien para poder medir huecos y fin de dia
bloques_sel(Sel, Bloques) :-
    findall(bloque(D, MI, MF),
            ( member(sel(M, G), Sel),
              bloques_de(M, G, Bs),
              member(bloque(D, MI, MF), Bs) ),
            Bloques).

% dos bloques se traslapan si es el mismo dia y los rangos se cruzan
% (van ya en minutos, asi es una simple comparacion)
% que se toquen en el borde no cuenta: 10:00-11:30 y 11:30-13:00 si van
traslapan(bloque(D, I1, F1), bloque(D, I2, F2)) :-
    I1 < F2,
    I2 < F1.

% huecos muertos entre clase y clase, en minutos
huecos_total(Bloques, Total) :-
    findall(D, member(bloque(D, _, _), Bloques), Dias0),
    sort(Dias0, Dias),
    findall(H, ( member(D, Dias),
                 findall(I-F, member(bloque(D, I, F), Bloques), P0),
                 sort(P0, P),
                 huecos_dia(P, H) ),
            Hs),
    sumlist(Hs, Total).

huecos_dia([], 0).
huecos_dia([_], 0).
huecos_dia([P1, P2 | Rs], H) :-
    hueco_entre(P1, P2, G),
    huecos_dia([P2 | Rs], H2),
    H is G + H2.

hueco_entre(_-F1, I2-_, G) :-
    ( I2 > F1 -> G is I2 - F1 ; G = 0 ).

% la ultima clase del dia que termine mas tarde, en minutos, para desempatar
% horarios que empaten en todo lo demas (el que acabe antes me late mas)
fin_tarde(Bloques, Max) :-
    findall(F, member(bloque(_, _, F), Bloques), Fs),
    ( Fs = [] -> Max = 0 ; max_list(Fs, Max) ).

% pongo primero los grupos del turno que pidio el alumno, asi el primer
% camino que se ensarta es el del turno completo y de ahi ya puedo recortar
ordena_pref(Pref, Grupos, Orden) :-
    findall(G, (member(G, Grupos), turno_grupo(G, Pref)), PrefPrimero),
    findall(G, (member(G, Grupos), \+ turno_grupo(G, Pref)), Resto),
    append(PrefPrimero, Resto, Orden).

% materias de la lista que no tienen ningun grupo este periodo, si hay una
% asi no hay que andar buscando combinaciones porque no sale
sin_grupo(Ms, Sin) :-
    findall(M, (member(M, Ms), \+ horario(M, _, _, _, _)), Sin).

% acomodo primero las materias con menos grupos, asi las ramas malas se
% cortan antes y no me muero esperando (afecta el orden interno nomas)
orden_por_grupos(Ms, Orden) :-
    findall(N-M,
            ( member(M, Ms),
              findall(G, horario(M, G, _, _, _), Gs0),
              sort(Gs0, Gs),          % si no tiene grupos queda [] y N = 0
              length(Gs, N) ),
            Pares),
    keysort(Pares, Sorted),
    findall(M, member(_-M, Sorted), Orden).

% ------------------------------------------------------------------------
% la busqueda: un grupo por materia sin traslapes, recorriendo el arbol
% una sola vez y guardando las K mejores combinaciones ahi en una
% variable global botada (nb_setval), porque armar 300 mil
% combinaciones pa ver cual sirve tarda una eternidad. el recorte: si lo
% que le falta al camino actual ni siquiera le alcanza para empatar al
% peor de los K guardados en el turno pedido, ya ni para que. con K=1
% esto es exactamente el viejo mejor_horario/3: el corte es el turno
% del mejor y solo entra uno.
% ------------------------------------------------------------------------

mejor_horario(Deseadas, Pref, Mejor) :-
    mejores_horarios(Deseadas, Pref, 1, [Mejor]).

% hasta K selecciones sin traslapes, de mejor a peor segun gana/2.
% falla si no hay ninguna (misma condicion que mejor_horario/3)
mejores_horarios(Deseadas, Pref, K, Sels) :-
    orden_por_grupos(Deseadas, Orden),
    % los grupos de cada materia ya ordenaditos con el turno preferido
    % primero, esto se hace una sola vez y no en cada nodo del arbol
    findall(M-GruposO,
            ( member(M, Orden),
              findall(G, horario(M, G, _, _, _), Gs0),
              sort(Gs0, Grupos),
              ordena_pref(Pref, Grupos, GruposO) ),
            Pares),
    KA is max(K, 1),
    nb_setval(top_k, []),
    nb_setval(top_k_max, KA),
    % forall es el que recorre TODAS las hojas, si no directo me quedo
    % con la primera combinacion que aparezca y "el mejor" no seria nada
    forall(busca(Pares, 0, [], [], Pref), true),
    nb_getval(top_k, Top),
    Top \== [],
    findall(S, member(cand(_, _, _, S), Top), Sels).

busca([], T, Sel0, Blqs, _) :-
    reverse(Sel0, Sel),
    huecos_total(Blqs, H),
    fin_tarde(Blqs, Fin),
    guarda_top(cand(T, H, Fin, Sel)).
busca([M-Grupos | Ms], T, Sel0, Blqs0, Pref) :-
    length(Ms, Rem),
    corte_turno(Corte),                     % si ya no alcanza ni a empatar
    T + Rem >= Corte,
    member(G, Grupos),
    bloques_de(M, G, Bg),
    \+ (member(B, Bg), member(P, Blqs0), traslapan(B, P)),
    ( turno_grupo(G, Pref) -> T1 is T + 1 ; T1 = T ),
    append(Blqs0, Bg, Blqs1),
    busca(Ms, T1, [sel(M, G) | Sel0], Blqs1, Pref).

% el minimo turno que todavia vale la pena alcanzar: el del peor de los
% K guardados (la lista viene de mejor a peor, el ultimo es el peor).
% si el cupo no esta lleno todavia es 0, o sea no se poda por turno
% hasta tener completas las K opciones
corte_turno(Corte) :-
    nb_getval(top_k, Top),
    nb_getval(top_k_max, K),
    (   length(Top, N), N >= K,
        last(Top, cand(Corte, _, _, _))
        ->  true
        ;   Corte = 0
    ).

% guarda la combinacion en su lugar y recorta a lo maximo K: solo entra
% si le gana (o empata) al peor que esta guardado
guarda_top(C) :-
    nb_getval(top_k, Top0),
    inserta_top(C, Top0, Top1),
    nb_getval(top_k_max, K),
    recorta(K, Top1, Top),
    nb_setval(top_k, Top).

inserta_top(C, [], [C]).
inserta_top(C, [B | Bs], [C, B | Bs]) :- gana(C, B), !.
inserta_top(C, [B | Bs], [B | Xs]) :-
    inserta_top(C, Bs, Xs).

recorta(K, L, R) :-                          % los primeros K de la lista
    length(P, K),
    append(P, _, L), !,
    R = P.
recorta(_, L, L).

% la comparacion del "mejor": primero gana el que mas le pegue al turno
% pedido, si empata el que tenga menos huecos y si aun asi empata el que
% acabe mas temprano
gana(cand(T1, H1, F1, _), cand(T2, H2, F2, _)) :-
    (   T1 > T2 -> true
    ;   T1 < T2 -> false
    ;   H1 < H2 -> true
    ;   H1 > H2 -> false
    ;   F1 =< F2
    ).


% ------------------------------------------------------------------------
% lo que probablemente quieras correr:
%   sugerir_horario(Cursadas, Deseadas, Preferencia, MejorSeleccion)
% con Preferencia = matutino | vespertino | mixto
% regresa la mejor seleccion de grupos que encontro (sel/2 por materia)
%
% pedir_horario/4 es lo mismo pero sin imprimir nada: regresa ok(Sel) o
% error(Codigo), eso es lo que se usa desde la interfaz json (interfaz.pl)
% y de ahi sale la consola de aca abajo
% ------------------------------------------------------------------------

pedir_horario(Cursadas, Deseadas, Pref, R) :-
    pedir_horarios(Cursadas, Deseadas, Pref, 1, R1),
    (   R1 = ok([Sel | _]) -> R = ok(Sel)
    ;   R1 = error(Cod)     -> R = error(Cod)
    ).

% igual que pedir_horario/4 pero pidiendo hasta K sugerencias: regresa
% ok([Sel1, Sel2, ...]) con las combinaciones de mejor a peor (Sel1 es
% la mejor, que es lo que regresaria pedir_horario/4). sirve pa sugerir
% alternativas cuando la primera no le gusta al alumno
pedir_horarios(Cursadas, Deseadas, Pref, K, R) :-
    (   \+ memberchk(Pref, [matutino, vespertino, mixto])
        -> R = error(preferencia_invalida(Pref))
    ;   Deseadas == []
        -> R = error(lista_vacia)
    ;   repetidas(Deseadas, [X | _])
        -> R = error(materia_repetida(X))
    ;   length(Deseadas, N), carga_de(N, maxima)
        -> R = error(carga_maxima(N))
    ;   \+ puede_inscribir(Cursadas, Deseadas)
        -> R = error(prerrequisitos)
    ;   sin_grupo(Deseadas, [M | _])
        -> R = error(sin_grupo(M))
    ;   mejores_horarios(Deseadas, Pref, K, Sels)
        -> R = ok(Sels)
    ;   R = error(sin_solucion)
    ).

sugerir_horario(Cursadas, Deseadas, Pref, Mejor) :-
    pedir_horario(Cursadas, Deseadas, Pref, R),
    (   R = error(Cod)
        -> ( imprime_error(Cod), fail )
        ;  R = ok(Sel),
           imprime_seleccion(Sel),
           Mejor = Sel
    ).

% los mensajes de consola, uno por codigo de error, pa no tener que
% leerlos en el json si solo estas probando aca en swipl
imprime_error(preferencia_invalida(Pref)) :-
    format('preferencia invalida: ~w (usa matutino, vespertino o mixto)~n', [Pref]).
imprime_error(lista_vacia) :-
    writeln('lista vacia, dame materias').
imprime_error(materia_repetida(M)) :-
    nom(M, N), format('materia repetida: ~w~n', [N]).
imprime_error(carga_maxima(N)) :-
    format('carga maxima con ~d materias, no es recomendable, no sugiero horario~n', [N]).
imprime_error(prerrequisitos) :-
    writeln('la lista no pasa la revision de prerequisitos, checa revisar/2').
imprime_error(sin_grupo(M)) :-
    nom(M, N), format('~w no tiene grupo este periodo~n', [N]).
imprime_error(sin_solucion) :-
    writeln('no hay forma de acomodar esa lista sin traslapes').

% imprimo el resultado lo mas presentable que se pudo
imprime_seleccion(Sel) :-
    nl,
    writeln('horario sugerido:'),
    forall( member(sel(M, G), Sel),
            ( nom(M, N), turno_grupo(G, T),
              format('  ~w  (grupo ~w, ~w)~n', [N, G, T]),
              imprime_dias(M, G) ) ),
    bloques_sel(Sel, Bs),
    length(Sel, N),
    huecos_total(Bs, H),
    fin_tarde(Bs, Fin),
    min_a_hhmm(Fin, FinH),
    format('  total: ~d materias, ~d min de huecos, termina a las ', [N, H]),
    imprime_hora(FinH),
    nl.

imprime_dias(M, G) :-
    dias(Ds),
    forall( (member(D, Ds), horario(M, G, D, I, F)),
            ( format('      ~w ', [D]), imprime_hora(I),
              write(' - '), imprime_hora(F), nl ) ).

% 700 -> 7:00 y 1030 -> 10:30, si no quedan todos chuecos los numeros
imprime_hora(HHMM) :-
    H is HHMM // 100,
    M is HHMM mod 100,
    ( M < 10 -> format('~w:0~w', [H, M]) ; format('~w:~w', [H, M]) ).


% ------------------------------------------------------------------------
% pruebas rapidas para saber si jala todo bien
% ------------------------------------------------------------------------

% alumno que ya curso el 1er semestre y quiere 6 materias del 2do,
% en turno matutino
demo :-
    Cursadas = [fundamentos_de_programacion, matematicas_discretas, calculo,
                analisis_vectorial, comunicacion_oral_y_escrita],
    Deseadas = [algoritmos_y_estructura_de_datos, algebra_lineal,
                calculo_aplicado, mecanica_y_electromagnetismo,
                ingenieria_etica_y_sociedad, fundamentos_economicos],
    revisar(Cursadas, Deseadas),
    sugerir_horario(Cursadas, Deseadas, matutino, Sel),
    nl,
    format('mejor seleccion: ~w~n', [Sel]).

% lo mismo pero sin haber cursado nada, aqui debe mentir sobre cada
% materia y revisar debe fallar (fallar es lo esperado, no es bug)
demo_mal :-
    revisar([], [algoritmos_y_estructura_de_datos, bases_de_datos]).
