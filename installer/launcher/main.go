// StreamDockLite.exe: abre la app con el Python que trae el instalador.
// Sin ventana de consola (se compila con -H windowsgui).
package main

import (
	"os"
	"os/exec"
	"path/filepath"
	"syscall"
	"unsafe"
)

func msg(text string) {
	user32 := syscall.NewLazyDLL("user32.dll")
	box := user32.NewProc("MessageBoxW")
	t, _ := syscall.UTF16PtrFromString(text)
	c, _ := syscall.UTF16PtrFromString("Stream Dock Lite")
	box.Call(0, uintptr(unsafe.Pointer(t)), uintptr(unsafe.Pointer(c)), 0x10)
}

func main() {
	exe, err := os.Executable()
	if err != nil {
		msg("No se pudo ubicar la aplicación.")
		return
	}
	base := filepath.Dir(exe)
	py := filepath.Join(base, "python", "pythonw.exe")
	app := filepath.Join(base, "app", "app.py")
	if _, err := os.Stat(py); err != nil {
		msg("Falta Python de la aplicación. Vuelve a ejecutar el instalador StreamDockLite-Setup.exe.")
		return
	}
	args := append([]string{app}, os.Args[1:]...)
	cmd := exec.Command(py, args...)
	cmd.Dir = filepath.Join(base, "app")
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}
	if err := cmd.Start(); err != nil {
		msg("No se pudo abrir Stream Dock Lite:\n" + err.Error())
	}
}
