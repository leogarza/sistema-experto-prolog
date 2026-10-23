package main

import (
	"embed"
	"fmt"
	"io/fs"
	"log"
	"net/http"
	"os"
	"os/exec"
	"time"
	"strings"
)

//go:embed web
var webFS embed.FS

type consult struct
{
	p string `json:"p"`
	args []string `json:"args"`
}

func main() {
	port := os.Getenv("PORT")
	if port == "" { port = "8080" }

	sub, err := fs.Sub(webFS, "web")
	if err != nil { log.Fatal(err) }

	mux := http.NewServeMux()
	mux.Handle("/", http.FileServer(http.FS(sub)))
	mux.HandleFunc("/ping", pong)
	mux.HandleFunc("/status", status)

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
