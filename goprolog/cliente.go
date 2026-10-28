// paquete inscripcion: una libreria para hablar con interfaz.pl (prolog)
// sin estar pegando json a mano. atras se queda vivo un swipl con sus
// pipes de stdin/stdout, tu le avias structs y te los regresa structs.
//
// uso basico:
//
//	cli := inscripcion.Nuevo("interfaz.pl")
//	defer cli.Cerrar()
//	rev, err := cli.Revisar(ctx, cursadas, deseadas)
//	sug, err := cli.Horario(ctx, cursadas, deseadas, inscripcion.Matutino, 5)
//
// y si un dia quieres aviar json crudo nomas:
//
//	var crudo map[string]any
//	err := cli.Consultar(ctx, map[string]any{"accion": "materias"}, &crudo)
package inscripcion

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

// Opcion le cambia el arranque al cliente
type Opcion func(*Cliente)

// ConSwipl dice que binario de swipl hay que usar (default "swipl")
func ConSwipl(ruta string) Opcion {
	return func(c *Cliente) { c.swipl = ruta }
}

// Cliente mantiene vivo un swipl corriendo interfaz.pl. es seguro usarlo
// desde varios goroutines: las consultas se van en fila por un mutex,
// porque el prolog es uno solo y no sabe atender a dos a la vez
type Cliente struct {
	swipl    string
	interfaz string

	mu     sync.Mutex // cuida lo de abajo y serializa las consultas
	cmd    *exec.Cmd
	stdin  io.WriteCloser
	reader *bufio.Reader
	log    *bitacora
}

// Nuevo arma un cliente apuntando a la interfaz.pl (no arranca el swipl
// hasta la primera consulta, y si se muere lo vuelve a arrancar solo)
func Nuevo(interfazPl string, ops ...Opcion) *Cliente {
	c := &Cliente{swipl: "swipl", interfaz: interfazPl}
	for _, op := range ops {
		op(c)
	}
	return c
}

// Consultar es el metodo crudo: le avientas cualquier peticion (struct con
// tags json, map, lo que sea) y en respuesta le apuntas a donde quiere
// que le llegue el json de vuelta. si el prolog contesta "ok": false
// regresa un *APIError. sirve para las tres acciones y para lo que se
// invente despues sin tocar esta libreria
func (c *Cliente) Consultar(ctx context.Context, peticion, respuesta any) error {
	if err := ctx.Err(); err != nil {
		return err
	}
	linea, err := json.Marshal(peticion)
	if err != nil {
		return fmt.Errorf("no pude convertir la peticion a json: %w", err)
	}

	c.mu.Lock()
	defer c.mu.Unlock()

	// dos intentos: si el prolog se murio a mitad de la jugada lo
	// arranco otra vez y le repito la misma consulta una sola vez
	var fallo error
	for intento := 0; intento < 2; intento++ {
		if err := c.arrancar(); err != nil {
			return err
		}
		salida, err := c.turno(ctx, linea)
		if err != nil {
			c.matar()
			if ctx.Err() != nil {
				return ctx.Err()
			}
			fallo = err
			continue
		}
		return c.decodificar(salida, respuesta)
	}
	return fallo
}

// Revisar checa la seriacion de la lista deseada contra las materias ya
// cursadas y regresa el reporte por materia
func (c *Cliente) Revisar(ctx context.Context, cursadas, deseadas []string) (*Revision, error) {
	peticion := struct {
		Accion   string   `json:"accion"`
		Cursadas []string `json:"cursadas,omitempty"`
		Deseadas []string `json:"deseadas,omitempty"`
	}{"revisar", cursadas, deseadas}
	var out Revision
	if err := c.Consultar(ctx, peticion, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// Horario arma el mejor horario sin traslapes para las materias que si
// se pueden inscribir. pref vacio = mixto. cantidad = cuantas
// sugerencias quiere (1 = solo la mejor, tope 10; 0 = el default del
// prolog que son 5). si algo falla viene un *APIError con el codigo
// ("carga_maxima", "prerrequisitos", ...)
func (c *Cliente) Horario(ctx context.Context, cursadas, deseadas []string, pref Preferencia, cantidad int) (*Sugerencia, error) {
	peticion := struct {
		Accion      string      `json:"accion"`
		Cursadas    []string    `json:"cursadas,omitempty"`
		Deseadas    []string    `json:"deseadas,omitempty"`
		Preferencia Preferencia `json:"preferencia,omitempty"`
		Cantidad    int         `json:"cantidad,omitempty"`
	}{"horario", cursadas, deseadas, pref, cantidad}
	var out Sugerencia
	if err := c.Consultar(ctx, peticion, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// Materias regresa el catalogo completo del plan (claves, creditos,
// seriacion y grupos)
func (c *Cliente) Materias(ctx context.Context) (*Catalogo, error) {
	var out Catalogo
	if err := c.Consultar(ctx, map[string]any{"accion": "materias"}, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// Cerrar cierra el stdin, deja que el swipl termine solo y si en 3
// segundos no se va lo mata. se puede llamar mas de una vez y despues
// de cerrar la proxima consulta lo vuelve a arrancar
func (c *Cliente) Cerrar() {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.cmd == nil {
		return
	}
	c.stdin.Close()
	terminado := make(chan struct{})
	go func() {
		c.cmd.Wait()
		close(terminado)
	}()
	select {
	case <-terminado:
	case <-time.After(3 * time.Second):
		c.cmd.Process.Kill()
		<-terminado
	}
	c.cmd, c.stdin, c.reader = nil, nil, nil
}

// -------- de ahi pa abajo son los chismes del proceso --------

// arrancar prende el swipl si no esta prendido (el llamador trae el mu)
func (c *Cliente) arrancar() error {
	if c.cmd != nil {
		return nil
	}
	// antes de prender el swipl checo que el archivo si este ahi, si no
	// el error llega despues como un EOF todo misterioso y con la culpa
	// en la bitacora de otro
	info, err := os.Stat(c.interfaz)
	if err != nil {
		cwd, _ := os.Getwd()
		return fmt.Errorf("no encuentro la interfaz (lei %s, el proceso corre en %s): %w",
			enAbs(c.interfaz), cwd, err)
	}
	if info.IsDir() {
		return fmt.Errorf("esi es un directorio y no el interfaz.pl: %s", enAbs(c.interfaz))
	}
	cmd := exec.Command(c.swipl, "-q", "-s", c.interfaz, "-g", "principal", "-t", "halt")
	stdin, err := cmd.StdinPipe()
	if err != nil {
		return fmt.Errorf("no pude agarrar el stdin del prolog: %w", err)
	}
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return fmt.Errorf("no pude agarrar el stdout del prolog: %w", err)
	}
	log := &bitacora{}
	cmd.Stderr = log // lo feo del prolog a su propia bitacora
	if err := cmd.Start(); err != nil {
		return fmt.Errorf("no pude arrancar %s con %s: %w", c.swipl, c.interfaz, err)
	}
	c.cmd, c.stdin, c.reader, c.log = cmd, stdin, bufio.NewReader(stdout), log
	return nil
}

// matar apaga el proceso a la brava, ya sea porque se murio o porque se
// acabo el tiempo de la consulta (el llamador trae el mu)
func (c *Cliente) matar() {
	if c.cmd == nil {
		return
	}
	c.stdin.Close()
	c.cmd.Process.Kill()
	c.cmd.Wait()
	c.cmd, c.stdin, c.reader = nil, nil, nil
}

// turno manda una linea y traga la respuesta hasta encontrar el salto
// de renglon, con su limite por el contexto por si el prolog se atora
func (c *Cliente) turno(ctx context.Context, linea []byte) (string, error) {
	if _, err := c.stdin.Write(append(linea, '\n')); err != nil {
		return "", fmt.Errorf("no pude escribirle al prolog: %w", err)
	}
	// el json de respuesta puede venir largo (el catalogo es grandote)
	// por eso ReadString y no bufio.Scanner, ese trae tope de 64k
	lectura := make(chan struct {
		linea string
		err   error
	}, 1)
	go func() {
		for {
			l, err := c.reader.ReadString('\n')
			if err != nil {
				lectura <- struct {
					linea string
					err   error
				}{l, err}
				return
			}
			if strings.TrimSpace(l) == "" {
				continue // por si el prolog suelta renglones en blanco
			}
			lectura <- struct {
				linea string
				err   error
			}{strings.TrimRight(l, "\r\n"), nil}
			return
		}
	}()
	select {
	case r := <-lectura:
		if r.err != nil {
			bit := c.log.texto()
			// el error tipico de apuntarle a inscripcion.pl en vez de
			// interfaz.pl: el archivo abre padre pero sin principal/0
			if strings.Contains(bit, "Unknown procedure: principal/0") {
				return "", fmt.Errorf("el swipl abrio %s pero ahi no esta principal/0: "+
					"hay que apuntarle a interfaz.pl, no a inscripcion.pl ni a los datos. bitacora: %s",
					enAbs(c.interfaz), bit)
			}
			return "", fmt.Errorf("se corto con el prolog: %w. bitacora: %s", r.err, bit)
		}
		return r.linea, nil
	case <-ctx.Done():
		return "", ctx.Err()
	}
}

// enAbs solo pa que el mensaje muestre el camino completo y no andemos
// adivinando contra que cwd choco
func enAbs(ruta string) string {
	if abs, err := filepath.Abs(ruta); err == nil {
		return abs
	}
	return ruta
}

// decodificar parte la linea de vuelta: si "ok" esta en false la guarda
// como *APIError y si no la meta tal cual en lo que el llamador pidio
func (c *Cliente) decodificar(linea string, respuesta any) error {
	var base struct {
		OK     bool   `json:"ok"`
		Codigo string `json:"error"`
	}
	if err := json.Unmarshal([]byte(linea), &base); err != nil {
		return fmt.Errorf("el prolog mando algo que no es json (%w): %s", err, linea)
	}
	if !base.OK {
		var e APIError
		if err := json.Unmarshal([]byte(linea), &e); err != nil {
			return fmt.Errorf("el prolog mando un error que no entendi (%w): %s", err, linea)
		}
		if e.Codigo == "" {
			e.Codigo = "desconocido"
		}
		return &e
	}
	if respuesta == nil {
		return nil
	}
	return json.Unmarshal([]byte(linea), respuesta)
}

// bitacora junta lo que escriba el stderr del swipl, con su candado
// porque eso lo escribe otro hilo al mismo tiempo
type bitacora struct {
	mu sync.Mutex
	b  bytes.Buffer
}

func (l *bitacora) Write(p []byte) (int, error) {
	l.mu.Lock()
	defer l.mu.Unlock()
	return l.b.Write(p)
}

func (l *bitacora) texto() string {
	l.mu.Lock()
	defer l.mu.Unlock()
	s := strings.TrimSpace(l.b.String())
	const tope = 2000
	if len(s) > tope {
		s = "..." + s[len(s)-tope:]
	}
	return s
}
