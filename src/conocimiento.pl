%Practica: Inscripcion en Prolog

%Paso 1: Hechos de Alumnos y Materias

%Alumnos  relacion(objetos).
% alumno(Nombre, Semestre).

alumno(ana, 3).
alumno(carlos, 5).
alumno(laura, 4).

%Materias

% materia(Clave, Creditos).
materia(programacion, 8).
materia(estructuras, 8).
materia(inteligencia_artificial, 8).
materia(vision_artificial, 8).


%Paso 2: Requisitos y Aprobaciones

%requisitos para cursar una materia
% prerrequisito(Materia, Requerida).

prerrequisito(estructuras, programacion).
prerrequisito(inteligencia_artificial, estructuras).
prerrequisito(vision_artificial, inteligencia_artificial).


%Aprobaciones

%aprobada(Alumno,Materia, Calificacion)
aprobada(ana, programacion, 8).
aprobada(carlos, programacion, 9).
aprobada(carlos, estructuras, 7).
aprobada(laura, programacion, 10).
aprobada(laura, estructuras, 9).
aprobada(laura, inteligencia_artificial, 8).


%Paso 3: Horarios y restricciones

%Horarios

% horario(Materia, Dia, Inicio, Fin).
horario(programacion, lunes, 12, 14).
horario(estructuras, martes, 10, 12).
horario(inteligencia_artificial, lunes, 13, 15).
horario(vision_artificial, miercoles, 12, 14).


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
