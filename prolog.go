package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"os/exec"
	"time"
)

// La meta de Prolog se arma aquí, con texto fijo. Los datos del usuario
// viajan por stdin como JSON, nunca concatenados dentro de la meta.
const preludio = "consult('src/conocimiento.pl'), consult('src/api.pl'), "

const metaConsultar = preludio +
	"json_read_dict(user_input, Req), consultar(Req, Resp), " +
	"json_write_dict(user_output, Resp), nl, halt."

const metaDatos = preludio +
	"datos(Resp), json_write_dict(user_output, Resp), nl, halt."

func ejecutarProlog(ctx context.Context, meta string, entrada []byte) (map[string]any, error) {
	ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()

	var out, errb bytes.Buffer
	cmd := exec.CommandContext(ctx, "swipl", "-q", "-f", "none", "-g", meta, "-t", "halt(1)")
	if entrada != nil {
		cmd.Stdin = bytes.NewReader(entrada)
	}
	cmd.Stdout = &out
	cmd.Stderr = &errb

	if err := cmd.Run(); err != nil {
		if ctx.Err() == context.DeadlineExceeded {
			return nil, fmt.Errorf("la consulta tardó más de 5 s")
		}
		return nil, fmt.Errorf("swipl: %v — %s", err, errb.String())
	}

	var resp map[string]any
	if err := json.Unmarshal(out.Bytes(), &resp); err != nil {
		return nil, fmt.Errorf("la salida no fue JSON: %q", out.String())
	}
	return resp, nil
}
