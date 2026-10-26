// Speak Sound's user-mode USB audio cable. Kernel transport is installed separately.
package main

import (
	"context"
	"fmt"
	"io"
	"log"
	"os"
	"os/signal"
	"virtualcables/internal/uac1"
	"virtualcables/internal/usbip"
)

func main() {
	device, err := uac1.NewDevice(1, 80)
	if err != nil {
		log.Fatal(err)
	}
	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt)
	defer cancel()
	// EOF closes the cable when the owning Python app exits, including crashes.
	go func() { _, _ = io.Copy(io.Discard, os.Stdin); cancel() }()
	server := usbip.NewServer("127.0.0.1:32401", []*uac1.Device{device}, log.New(os.Stderr, "virtual-mic: ", log.LstdFlags))
	result := make(chan error, 1)
	go func() { result <- server.Serve(ctx) }()
	select {
	case <-server.Ready():
		fmt.Println(`{"ready":true,"address":"127.0.0.1:32401","busid":"1-1"}`)
	case err := <-result:
		log.Fatal(err)
	}
	select {
	case <-ctx.Done():
	case err := <-result:
		if err != nil { log.Fatal(err) }
	}
}
