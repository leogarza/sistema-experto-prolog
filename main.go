package main

import (
	"embed"
	"encoding/json"
	"fmt"
	"io"
	"io/fs"
	"log"
	"net/http"
	"os"
	"os/exec"
	"strings"
	"time"
)

//go:embed web
var webFS embed.FS

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	sub, err := fs.Sub(webFS, "web")
	if err != nil {
		log.Fatal(err)
	}

	mux := http.NewServeMux()
	mux.Handle("/", http.FileServer(http.FS(sub)))
	mux.HandleFunc("/ping", pong)
	mux.HandleFunc("/status", status)
	mux.HandleFunc("/api/datos", handleDatos)
	mux.HandleFunc("/api/consultar", handleConsultar)

	srv := &http.Server{
		Addr:              ":" + port,
		Handler:           mux,
		ReadHeaderTimeout: 5 * time.Second,
	}

	log.Printf("escuchando en :%s", port)
	log.Fatal(srv.ListenAndServe())
}

func pong(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "text/plain")
	fmt.Fprintf(w, "PONG!")
}

func status(w http.ResponseWriter, r *http.Request) {
	out, err := exec.Command("swipl", "--version").CombinedOutput()
	w.Header().Set("Content-Type", "application/json")
	if err != nil {
		w.WriteHeader(http.StatusInternalServerError)
		fmt.Fprintf(w, `{"ok": false, "details":%q}`+"\n", err.Error())
		return
	}
	fmt.Fprintf(w, `{"ok": true, "swipl": %q}`+"\n", strings.TrimSpace(string(out)))
}

// GET /api/datos -> alumnos y materias, para llenar los selectores.
func handleDatos(w http.ResponseWriter, r *http.Request) {
	resp, err := ejecutarProlog(r.Context(), metaDatos, nil)
	responderJSON(w, resp, err)
}

// POST /api/consultar -> pasa el JSON del navegador al motor de Prolog.
func handleConsultar(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "usa POST", http.StatusMethodNotAllowed)
		return
	}
	cuerpo, err := io.ReadAll(io.LimitReader(r.Body, 1<<20))
	if err != nil {
		http.Error(w, "no se pudo leer el cuerpo", http.StatusBadRequest)
		return
	}
	resp, err := ejecutarProlog(r.Context(), metaConsultar, cuerpo)
	responderJSON(w, resp, err)
}

func responderJSON(w http.ResponseWriter, resp map[string]any, err error) {
	w.Header().Set("Content-Type", "application/json")
	if err != nil {
		w.WriteHeader(http.StatusBadRequest)
		fmt.Fprintf(w, `{"resultado": "error", "detalle": %q}`+"\n", err.Error())
		return
	}
	b, _ := json.Marshal(resp)
	w.Write(append(b, '\n'))
}
