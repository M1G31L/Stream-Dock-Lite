package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestExtract(t *testing.T) {
	d := t.TempDir()
	py, app := filepath.Join(d, "python"), filepath.Join(d, "app")
	if err := extractPython(py); err != nil {
		t.Fatal(err)
	}
	if err := extractApp(app); err != nil {
		t.Fatal(err)
	}
	for _, f := range []string{"python/pythonw.exe", "python/python.exe", "python/Lib/tkinter/__init__.py",
		"python/DLLs/_tkinter.pyd", "python/Lib/site-packages/pip/__init__.py", "python/.version",
		"app/app.py", "app/tray.py", "app/playlists.py", "app/requirements.txt", "app/instalador/desinstalar.ps1", "app/app.ico"} {
		if _, err := os.Stat(filepath.Join(d, f)); err != nil {
			t.Errorf("falta %s", f)
		}
	}
	if _, ok := safeJoin(d, "../evil"); ok {
		t.Error("ruta peligrosa aceptada")
	}
	if len(launcherExe) < 100000 {
		t.Error("lanzador vacío")
	}
	t.Logf("version=%q", payloadVersion)
}
