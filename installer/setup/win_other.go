//go:build !windows

package main

import "fmt"

// Solo para probar la extracción fuera de Windows.
func setTitle(t string)                { fmt.Println("== " + t) }
func msgBox(text string, isError bool) { fmt.Println("[MSG] " + text) }
