package main

import (
	"context"
	"embed"
	"encoding/json"
	"errors"
	"io/fs"
	"log"
	"net/http"
	"os"
	"time"

	inscripcion "sistema-experto-prolog/goprolog"
)

//go:embed web
var staticFiles embed.FS

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	pubFS, err := fs.Sub(staticFiles, "web")
	if err != nil { log.Fatal(err) }

	log.Printf("Servidor escuchando en :%s\n", port)

	prolog := inscripcion.Nuevo("src/interfaz.pl")
	defer prolog.Cerrar()

	mux := http.NewServeMux()

	fileServer := http.FileServer(http.FS(pubFS))

	mux.Handle("/static/", http.StripPrefix("/static/", fileServer))
	mux.HandleFunc("GET /{$}", func(w http.ResponseWriter, r *http.Request) {
		http.ServeFileFS(w, r, pubFS, "index.html")
	})

	mux.HandleFunc("GET /materias", func(w http.ResponseWriter, r *http.Request) {
		ctx, cancel := context.WithTimeout(r.Context(), 10*time.Second)
		defer cancel()

		cat, err := prolog.Materias(ctx)
		if err != nil {
			log.Printf("consulta a prolog: %v", err)
			writeError(w, http.StatusInternalServerError, "prolog", err.Error())
			return
		}

		writeJSON(w, http.StatusOK, cat)
	})

	type revisarRequest struct {
		Cursadas []string `json:"cursadas"`
		Deseadas []string `json:"deseadas"`
	}

	mux.HandleFunc("POST /revisar", func(w http.ResponseWriter, r *http.Request) {
		defer r.Body.Close()

		var req revisarRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			writeError(w, http.StatusBadRequest, "json_invalido", err.Error())
			return
		}

		if len(req.Cursadas) == 0 && len(req.Deseadas) == 0 {
			writeError(w, http.StatusBadRequest, "sin_materias",
				   "debes enviar al menos una materia en 'cursadas' o 'deseadas'")
			return
		}

		ctx, cancel := context.WithTimeout(r.Context(), 10*time.Second)
		defer cancel()

		rev, err := prolog.Revisar(ctx, req.Cursadas, req.Deseadas)
		if err != nil {
			var apiErr *inscripcion.APIError
			if errors.As(err, &apiErr) {
				writeJSON(w, http.StatusUnprocessableEntity, apiErr)
				return
			}
			if errors.Is(err, context.DeadlineExceeded) {
				log.Printf("revisar: timeout")
				writeError(w, http.StatusGatewayTimeout, "prolog_timeout", "Prolog tardó demasiado")
				return
			}
			log.Printf("revisar: %v", err)
			writeError(w, http.StatusBadGateway, "prolog", err.Error())
			return
		}

		writeJSON(w, http.StatusOK, rev)
	})

	type horarioRequest struct {
		Cursadas    []string                `json:"cursadas"`
		Deseadas    []string                `json:"deseadas"`
		Preferencia inscripcion.Preferencia `json:"preferencia,omitempty"`
		Cantidad    int                     `json:"cantidad,omitempty"`
	}

	mux.HandleFunc("POST /horario", func(w http.ResponseWriter, r *http.Request) {
		defer r.Body.Close()

		var req horarioRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			writeError(w, http.StatusBadRequest, "json_invalido", err.Error())
			return
		}

		if len(req.Cursadas) == 0 && len(req.Deseadas) == 0 {
			writeError(w, http.StatusBadRequest, "sin_materias",
				   "debes enviar al menos una materia en 'cursadas' o 'deseadas'")
			return
		}

		if !preferenciaValida(req.Preferencia) {
			writeError(w, http.StatusBadRequest, "preferencia_invalida",
				   "preferencia debe ser '', 'matutino', 'vespertino' o 'mixto'")
			return
		}

		ctx, cancel := context.WithTimeout(r.Context(), 100*time.Second)
		defer cancel()

		sug, err := prolog.Horario(ctx, req.Cursadas, req.Deseadas, req.Preferencia, req.Cantidad)
		if err != nil {
			var apiErr *inscripcion.APIError
			if errors.As(err, &apiErr) {
				writeJSON(w, http.StatusUnprocessableEntity, apiErr)
				return
			}
			if errors.Is(err, context.DeadlineExceeded) {
				log.Printf("horario: timeout")
				writeError(w, http.StatusGatewayTimeout, "prolog_timeout", "Prolog tardó demasiado")
				return
			}
			log.Printf("horario: %v", err)
			writeError(w, http.StatusBadGateway, "prolog", err.Error())
			return
		}

		writeJSON(w, http.StatusOK, sug)
	})

	srv := &http.Server{
		Addr:              ":" + port,
		Handler:           mux,
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       10 * time.Second,
		WriteTimeout:      120 * time.Second,
		IdleTimeout:       120 * time.Second,
		MaxHeaderBytes:    1 << 20,
	}
	log.Fatal(srv.ListenAndServe())
}


func preferenciaValida(p inscripcion.Preferencia) bool {
	switch p {
		case inscripcion.SinPreferencia, // ""
		inscripcion.Matutino,        // "matutino"
		inscripcion.Vespertino,      // "vespertino"
		inscripcion.Mixto:           // "mixto"
		return true
	}
	return false
}

/* ---------------- funciones de utilidad -----------------------*/

// writeJSON escribe v como JSON con el status HTTP indicado.
func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	if err := json.NewEncoder(w).Encode(v); err != nil {
		log.Printf("writeJSON: %v", err)
	}
}

type errorResponse struct {
	OK    bool   `json:"ok"`
	Error string `json:"error"`
	Mensaje string `json:"mensaje,omitempty"`
}

// writeError escribe un JSON de error simple: {"ok":false,"error":"..."}.
func writeError(w http.ResponseWriter, status int, code, msg string) {
	writeJSON(w, status, errorResponse{OK: false, Error: code, Mensaje: msg})
}

