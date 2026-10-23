:- use_module(library(http/json)).

%% ------------------------------------------------------------------
%% Capa de consulta: recibe el JSON del navegador y responde un dict.
%% La lógica vive en conocimiento.pl; aquí solo se despacha de forma
%% segura (lista blanca + call/N, nunca se construyen metas con texto
%% que venga del usuario).
%% ------------------------------------------------------------------

% Datos para llenar los selectores de la interfaz.
datos(Resp) :-
    findall(A, alumno(A, _), Alumnos),
    findall(M, materia(M, _), Materias),
    Resp = _{alumnos: Alumnos, materias: Materias}.

% consultar(+Dict, -Dict)
consultar(Req, Resp) :-
    (   get_dict(pred, Req, P0), get_dict(args, Req, A0)
    ->  despachar(P0, A0, Resp)
    ;   Resp = _{resultado: "error", detalle: "faltan los campos pred y args"}
    ).

despachar(P0, A0, Resp) :-
    atom_string(Pred, P0),
    maplist(atom_string, Args, A0),
    length(Args, N),
    (   permitido(Pred/N)
    ->  G =.. [Pred|Args],
        catch(contar(G, Resp), E,
              (format(string(M), "~w", [E]),
               Resp = _{resultado: "error", detalle: M}))
    ;   Resp = _{resultado: "error", detalle: "predicado no permitido"}
    ).

contar(G, Resp) :-
    findall(ok, call(G), Sols),
    length(Sols, N),
    (   N =:= 0
    ->  Resp = _{resultado: "sin_solucion", n: 0}
    ;   Resp = _{resultado: "ok", n: N}
    ).

%% ------------------- LISTA BLANCA -------------------
%% Solo lo que esté aquí se puede consultar desde la web.
permitido(puede_cursar/2).
permitido(recomendar/2).
permitido(materia_aprobada/2).
permitido(cumple_prerrequisito/2).
permitido(sin_prerrequisitos/1).
permitido(conflicto/2).
