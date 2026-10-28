package inscripcion

// tipos de las respuestas, aqui lo importante es que los tags json
// coincidan palabra por palabra con lo que manda interfaz.pl

// Preferencia es el turno que se le pide al horario. vacio = mixto
type Preferencia string

const (
	SinPreferencia Preferencia = ""
	Matutino       Preferencia = "matutino"
	Vespertino     Preferencia = "vespertino"
	Mixto          Preferencia = "mixto"
)

// Carga es cuantas materias va a llevar el alumno en el periodo
type Carga struct {
	Cantidad int    `json:"cantidad"`
	Clase    string `json:"clase"` // minima | media | maxima
}

// Fila es como le fue a una materia en la revision de prerrequisitos
type Fila struct {
	Materia   string   `json:"materia"`
	Nombre    string   `json:"nombre"`
	Estado    string   `json:"estado"` // ok | faltante | desconocida
	Faltantes []string `json:"faltantes"`
}

// Revision es la respuesta de la accion revisar
type Revision struct {
	OK             bool   `json:"ok"`
	Accion         string `json:"accion"`
	Carga          Carga  `json:"carga"`
	Reporte        []Fila `json:"reporte"`
	PuedeInscribir bool   `json:"puede_inscribir"`
}

// Bloque es un horario de una materia en un dia ("8:30" - "10:00")
type Bloque struct {
	Dia    string `json:"dia"`
	Inicio string `json:"inicio"`
	Fin    string `json:"fin"`
}

// MateriaHorario es una materia ya con su grupo elegido
type MateriaHorario struct {
	Materia string   `json:"materia"`
	Nombre  string   `json:"nombre"`
	Grupo   string   `json:"grupo"`
	Turno   string   `json:"turno"` // matutino | vespertino
	Bloques []Bloque `json:"bloques"`
}

// Resumen del horario armado
type Resumen struct {
	Materias      int    `json:"materias"`
	HuecosMinutos int    `json:"huecos_minutos"`
	Termina       string `json:"termina"`
	Matutinas     int    `json:"matutinas"`
	Vespertinas   int    `json:"vespertinas"`
}

// Opcion de horario: una combinacion completa de grupos con su resumen.
// la primera que llega en "sugerencias" es siempre la mejor; las demas
// son alternativas igual de validas (sin traslapes) ordenadas de mejor
// a peor
type OpcionHorario struct {
	Horario []MateriaHorario `json:"horario"`
	Resumen Resumen          `json:"resumen"`
}

// Sugerencia es la respuesta de la accion horario
type Sugerencia struct {
	OK               bool             `json:"ok"`
	Accion           string           `json:"accion"`
	Preferencia      string           `json:"preferencia"`
	Carga            Carga            `json:"carga"`
	PuedeInscribir   bool             `json:"puede_inscribir"`
	Reporte          []Fila           `json:"reporte"`
	Horario          []MateriaHorario `json:"horario"`
	Resumen          Resumen          `json:"resumen"`
	Sugerencias      []OpcionHorario  `json:"sugerencias"`
	TotalSugerencias int              `json:"total_sugerencias"`
}

// MateriaCatalogo es una materia del plan con su seriacion y grupos
type MateriaCatalogo struct {
	Clave          string   `json:"clave"`
	Nombre         string   `json:"nombre"`
	Creditos       float64  `json:"creditos"`
	Semestre       int      `json:"semestre"`
	Tipo           string   `json:"tipo"` // obligatoria | optativa
	Prerrequisitos []string `json:"prerrequisitos"`
	Grupos         []string `json:"grupos"`
}

// Catalogo es la respuesta de la accion materias
type Catalogo struct {
	OK       bool              `json:"ok"`
	Accion   string            `json:"accion"`
	Total    int               `json:"total"`
	Materias []MateriaCatalogo `json:"materias"`
}

// APIError es lo que regresa el prolog cuando "ok" viene en false.
// todos los metodos lo devuelven como error, se recupera con errors.As
type APIError struct {
	Codigo      string `json:"error"`
	Materia     string `json:"materia,omitempty"`
	Preferencia string `json:"preferencia,omitempty"`
	Cantidad    int    `json:"cantidad,omitempty"`
	Mensaje     string `json:"mensaje"`
	Reporte     []Fila `json:"reporte,omitempty"`
}

func (e *APIError) Error() string {
	if e.Mensaje == "" {
		return e.Codigo
	}
	return e.Codigo + ": " + e.Mensaje
}
