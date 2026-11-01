package main

import (
	"syscall"
	"unsafe"
)

func setTitle(t string) {
	k := syscall.NewLazyDLL("kernel32.dll").NewProc("SetConsoleTitleW")
	p, _ := syscall.UTF16PtrFromString(t)
	k.Call(uintptr(unsafe.Pointer(p)))
	// consola en UTF-8 para que se vean bien las tildes
	syscall.NewLazyDLL("kernel32.dll").NewProc("SetConsoleOutputCP").Call(65001)
}

func msgBox(text string, isError bool) {
	box := syscall.NewLazyDLL("user32.dll").NewProc("MessageBoxW")
	t, _ := syscall.UTF16PtrFromString(text)
	c, _ := syscall.UTF16PtrFromString("Stream Dock Lite")
	flags := uintptr(0x40)
	if isError {
		flags = 0x10
	}
	box.Call(0, uintptr(unsafe.Pointer(t)), uintptr(unsafe.Pointer(c)), flags)
}
