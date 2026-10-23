%Practica: Inscripcion en Prolog

% NOTA: los hechos materia/2 y prerrequisito/2 viven ahora en src/hechos.pl
% (generados desde la retícula oficial). Aquí solo quedan los alumnos de
% prueba y las reglas.

%Paso 1: Hechos de Alumnos

%Alumnos  relacion(objetos).
% alumno(Nombre, Semestre).

alumno(ana, 3).
alumno(carlos, 5).
alumno(laura, 4).

%Materias

% materia(Clave, Creditos).
%Paso 2: Requisitos y Aprobaciones

%requisitos para cursar una materia
% prerrequisito(Materia, Requerida).

%Aprobaciones

%aprobada(Alumno,Materia, Calificacion)
aprobada(ana, fundamentos_de_programacion, 8).
aprobada(carlos, fundamentos_de_programacion, 9).
aprobada(carlos, algoritmos_y_estructura_de_datos, 7).
aprobada(laura, fundamentos_de_programacion, 10).
aprobada(laura, algoritmos_y_estructura_de_datos, 9).
aprobada(laura, inteligencia_artificial, 8).


%Paso 3: Horarios y restricciones

%Horarios

% horario(Materia, Dia, Inicio, Fin).
horario(fundamentos_de_programacion, lunes, 12, 14).
horario(algoritmos_y_estructura_de_datos, martes, 10, 12).
horario(inteligencia_artificial, lunes, 13, 15).
horario(vision_por_computadora_machine_learning, miercoles, 12, 14).


%Paso 4: Reglas y Aprobaciones

%Para aprobar una materia, la calificacion debe ser 6 o superior

materia_aprobada(Alumno, Materia) :-
    aprobada(Alumno, Materia, Calificacion),
    Calificacion >= 6.

%Paso 5: Casos de prerrequisitos

sin_prerrequisitos(Materia) :-
    materia(Materia, _),
    \+ prerrequisito(Materia, _).

cumple_prerrequisito(Alumno, Materia) :-
    prerrequisito(Materia, Requerida),
    materia_aprobada(Alumno, Requerida).

%Paso 6: Saber si un alumno puede cursar una materia

puede_cursar(Alumno, Materia) :-
    alumno(Alumno, _),
    materia(Materia, _),
    \+ materia_aprobada(Alumno, Materia),
    (
        sin_prerrequisitos(Materia)
        ;
        cumple_prerrequisito(Alumno, Materia)
    ).

%Paso 8: Conflictos de Horario

conflicto(Materia1, Materia2) :-
    Materia1 \= Materia2,
    horario(Materia1, Dia, Inicio1, Fin1),
    horario(Materia2, Dia, Inicio2, Fin2),
    Inicio1 < Fin2,
    Inicio2 < Fin1.

%Paso 9: Calculo de creditos aprobados (listas)

creditos_aprobados(Alumno, Total) :-
    findall(
        Creditos,
        (
            materia_aprobada(Alumno, Materia),
            materia(Materia, Creditos)
        ),
        Lista
    ),
    sum_list(Lista, Total).

%Paso 10: Recomendacion de materia

recomendar(Alumno, Materia) :-
    puede_cursar(Alumno, Materia),
    materia(Materia, 8).
