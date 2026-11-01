// StreamDockLite-Setup.exe
//
// Instalador de Stream Dock Lite que NO necesita Python instalado:
// trae dentro un Python portátil (con tkinter), la app y el lanzador.
// Instala en %LOCALAPPDATA%\Programs\StreamDockLite sin permisos de administrador.
package main

import (
	"archive/tar"
	"archive/zip"
	"bytes"
	"compress/gzip"
	_ "embed"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

//go:embed payload/python.tar.gz
var pythonTarGz []byte

//go:embed payload/app.zip
var appZip []byte

//go:embed launcher.exe
var launcherExe []byte

//go:embed payload/version.txt
var payloadVersion string

const pythonVersion = "3.12.16+20261026"

func step(n int, text string) { fmt.Printf("\n[%d/6] %s\n", n, text) }

func fail(err error, what string) {
	fmt.Printf("\nERROR: %s\n%v\n", what, err)
	msgBox("No se pudo instalar Stream Dock Lite.\n\n"+what+"\n\n"+err.Error(), true)
	waitEnter()
	os.Exit(1)
}

func waitEnter() {
	fmt.Println("\nPulsa Enter para cerrar…")
	buf := make([]byte, 1)
	os.Stdin.Read(buf)
}

func safeJoin(base, rel string) (string, bool) {
	p := filepath.Join(base, filepath.FromSlash(rel))
	if p != base && !strings.HasPrefix(p, base+string(os.PathSeparator)) {
		return "", false // ruta peligrosa (../)
	}
	return p, true
}

func extractPython(dest string) error {
	gz, err := gzip.NewReader(bytes.NewReader(pythonTarGz))
	if err != nil {
		return err
	}
	tr := tar.NewReader(gz)
	n := 0
	for {
		h, err := tr.Next()
		if err == io.EOF {
			break
		}
		if err != nil {
			return err
		}
		name := strings.TrimPrefix(h.Name, "python/")
		if name == "" || name == h.Name {
			continue
		}
		target, ok := safeJoin(dest, name)
		if !ok {
			continue
		}
		switch h.Typeflag {
		case tar.TypeDir:
			os.MkdirAll(target, 0o755)
		case tar.TypeReg:
			os.MkdirAll(filepath.Dir(target), 0o755)
			f, err := os.Create(target)
			if err != nil {
				return err
			}
			if _, err := io.Copy(f, tr); err != nil {
				f.Close()
				return err
			}
			f.Close()
			n++
			if n%400 == 0 {
				fmt.Printf("   %d archivos…\n", n)
			}
		}
	}
	return os.WriteFile(filepath.Join(dest, ".version"), []byte(pythonVersion), 0o644)
}

func extractApp(dest string) error {
	zr, err := zip.NewReader(bytes.NewReader(appZip), int64(len(appZip)))
	if err != nil {
		return err
	}
	for _, f := range zr.File {
		name := strings.TrimPrefix(f.Name, "StreamDockLite/")
		if name == "" || strings.HasSuffix(name, "/") || strings.Contains(name, "__pycache__") {
			continue
		}
		target, ok := safeJoin(dest, name)
		if !ok {
			continue
		}
		os.MkdirAll(filepath.Dir(target), 0o755)
		rc, err := f.Open()
		if err != nil {
			return err
		}
		out, err := os.Create(target)
		if err != nil {
			rc.Close()
			return err
		}
		_, err = io.Copy(out, rc)
		out.Close()
		rc.Close()
		if err != nil {
			return err
		}
	}
	return nil
}

func run(name string, args ...string) error {
	cmd := exec.Command(name, args...)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	return cmd.Run()
}

func powershell(script string) error {
	return run("powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script)
}

func psq(s string) string { return "'" + strings.ReplaceAll(s, "'", "''") + "'" }

func main() {
	version := strings.TrimSpace(payloadVersion)
	setTitle("Instalador de Stream Dock Lite " + version)
	fmt.Println()
	fmt.Println("  Stream Dock Lite " + version + "  ·  Stream Dock N3E + Spotify")
	fmt.Println("  No necesita Python ni permisos de administrador.")

	local := os.Getenv("LOCALAPPDATA")
	if local == "" {
		fail(fmt.Errorf("LOCALAPPDATA vacío"), "No se encontró tu carpeta de usuario.")
	}
	dest := filepath.Join(local, "Programs", "StreamDockLite")
	pyDir := filepath.Join(dest, "python")
	appDir := filepath.Join(dest, "app")
	fmt.Println("  Carpeta: " + dest)

	// 1) cerrar la app si está abierta
	step(1, "Cerrando Stream Dock Lite si estaba abierto")
	powershell(`Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" -ErrorAction SilentlyContinue | ` +
		`Where-Object { $_.CommandLine -like '*StreamDockLite*app.py*' } | ` +
		`ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }`)
	time.Sleep(700 * time.Millisecond)

	// 2) Python portátil
	step(2, "Preparando Python interno")
	if b, err := os.ReadFile(filepath.Join(pyDir, ".version")); err == nil && strings.TrimSpace(string(b)) == pythonVersion {
		fmt.Println("   Ya está instalado.")
	} else {
		os.RemoveAll(pyDir)
		if err := os.MkdirAll(pyDir, 0o755); err != nil {
			fail(err, "No se pudo crear la carpeta del programa.")
		}
		if err := extractPython(pyDir); err != nil {
			fail(err, "No se pudo extraer Python.")
		}
	}
	os.RemoveAll(filepath.Join(dest, "venv")) // restos de la versión anterior (instalador .cmd)

	// 3) la app
	step(3, "Copiando la aplicación")
	if err := extractApp(appDir); err != nil {
		fail(err, "No se pudieron copiar los archivos de la app.")
	}
	if err := os.WriteFile(filepath.Join(dest, "StreamDockLite.exe"), launcherExe, 0o755); err != nil {
		fail(err, "No se pudo crear StreamDockLite.exe (¿está abierto?).")
	}

	// 4) componentes (USB, Spotify, volumen, bandeja)
	step(4, "Instalando componentes (necesita internet, solo esta vez)")
	py := filepath.Join(pyDir, "python.exe")
	req := filepath.Join(appDir, "requirements.txt")
	var err error
	for intento := 1; intento <= 3; intento++ {
		err = run(py, "-m", "pip", "install", "--disable-pip-version-check", "--no-warn-script-location",
			"-q", "--upgrade", "-r", req)
		if err == nil {
			break
		}
		fmt.Printf("   Reintentando (%d/3)…\n", intento)
		time.Sleep(3 * time.Second)
	}
	if err != nil {
		fail(err, "No se pudieron descargar los componentes. Revisa tu conexión a internet y vuelve a abrir el instalador.")
	}

	// 5) accesos directos + Aplicaciones instaladas
	step(5, "Creando accesos directos")
	ps := `
$ErrorActionPreference = 'SilentlyContinue'
$Dest = ` + psq(dest) + `
$App = Join-Path $Dest 'app'
$Exe = Join-Path $Dest 'StreamDockLite.exe'
$Ico = Join-Path $App 'app.ico'
$sh = New-Object -ComObject WScript.Shell
function Acceso($ruta, $target, $argumentos, $desc) {
  $l = $sh.CreateShortcut($ruta); $l.TargetPath = $target; $l.Arguments = $argumentos
  $l.WorkingDirectory = $App; $l.IconLocation = $Ico; $l.Description = $desc; $l.Save()
}
$menu = Join-Path ([Environment]::GetFolderPath('Programs')) 'Stream Dock Lite'
New-Item -ItemType Directory -Force -Path $menu | Out-Null
Acceso (Join-Path $menu 'Stream Dock Lite.lnk') $Exe '' 'Controlador del Stream Dock N3E'
Acceso (Join-Path $menu 'Diagnostico del N3E.lnk') (Join-Path $Dest 'python\python.exe') ('"' + (Join-Path $App 'detectar.py') + '"') 'Prueba la conexion con el N3E'
Acceso (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Stream Dock Lite.lnk') $Exe '' 'Controlador del Stream Dock N3E'
$startup = Join-Path ([Environment]::GetFolderPath('Startup')) 'StreamDockLite.cmd'
if (Test-Path $startup) { Set-Content -Path $startup -Encoding ASCII -Value ('@start "" "' + $Exe + '" --min') }
$key = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\StreamDockLite'
New-Item -Path $key -Force | Out-Null
$un = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $App 'instalador\desinstalar.ps1') + '"'
$size = [int]((Get-ChildItem $Dest -Recurse -File | Measure-Object Length -Sum).Sum / 1KB)
Set-ItemProperty -Path $key -Name DisplayName -Value 'Stream Dock Lite'
Set-ItemProperty -Path $key -Name DisplayVersion -Value ` + psq(version) + `
Set-ItemProperty -Path $key -Name Publisher -Value 'Stream Dock Lite'
Set-ItemProperty -Path $key -Name InstallLocation -Value $Dest
Set-ItemProperty -Path $key -Name DisplayIcon -Value $Ico
Set-ItemProperty -Path $key -Name UninstallString -Value $un
Set-ItemProperty -Path $key -Name NoModify -Value 1 -Type DWord
Set-ItemProperty -Path $key -Name NoRepair -Value 1 -Type DWord
Set-ItemProperty -Path $key -Name EstimatedSize -Value $size -Type DWord
`
	if err := powershell(ps); err != nil {
		fmt.Println("   Aviso: no se pudieron crear todos los accesos directos:", err)
	}

	// 6) abrir
	step(6, "Listo")
	fmt.Println("   Stream Dock Lite " + version + " instalado.")
	fmt.Println("   Recuerda cerrar el software oficial Stream Dock antes de usarlo.")
	cmd := exec.Command(filepath.Join(dest, "StreamDockLite.exe"))
	cmd.Dir = appDir
	cmd.Start()
	time.Sleep(4 * time.Second)
}
