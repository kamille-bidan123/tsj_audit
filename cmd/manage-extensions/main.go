package main

import (
	"flag"
	"fmt"
	"net/http"
	"os"

	"tsj-audit/internal/extensions"
)

func main() {
	host := flag.String("host", "127.0.0.1", "host")
	port := flag.Int("port", 8765, "port")
	root := flag.String("root", ".", "project root")
	flag.Parse()

	address := fmt.Sprintf("%s:%d", *host, *port)
	server := extensions.NewServer(*root)
	fmt.Fprintf(os.Stderr, "[extension-ui] http://%s\n", address)
	if err := http.ListenAndServe(address, server.Handler()); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
