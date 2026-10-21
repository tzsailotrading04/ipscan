package main

import (
	"bufio"
	"crypto/tls"
	"fmt"
	"io"
	"net"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"
)

var (
	dialTO   = 8 * time.Second
	deadline = 20 * time.Second
	fastTTFB = 1000 * time.Millisecond
	fastKB   = 300.0
)

type bufConn struct {
	net.Conn
	r *bufio.Reader
}

func (b *bufConn) Read(p []byte) (int, error) { return b.r.Read(p) }

func main() {
	if len(os.Args) < 3 { return }
	in, out := os.Args[1], os.Args[2]
	f, err := os.Open(in)
	if err != nil { return }
	defer f.Close()
	o, err := os.Create(out)
	if err != nil { return }
	defer o.Close()

	var lines []string
	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 1<<20), 1<<20)
	for sc.Scan() {
		if s := strings.TrimSpace(sc.Text()); s != "" { lines = append(lines, s) }
	}

	var mu sync.Mutex
	var wg sync.WaitGroup
	sem := make(chan struct{}, 250)
	for _, l := range lines {
		wg.Add(1)
		sem <- struct{}{}
		go func(line string) {
			defer wg.Done()
			defer func() { <-sem }()
			proto, addr := parse(line)
			if addr == "" { return }
			exit, ttfb, kbps, err := probe(proto, addr)
			if err != nil || exit == "" { return }
			mu.Lock()
			fmt.Fprintf(o, "%s %s %d %.0f\n", addr, exit, ttfb.Milliseconds(), kbps)
			mu.Unlock()
		}(l)
	}
	wg.Wait()
}

func parse(line string) (string, string) {
	proto, s := "http", line
	if i := strings.Index(s, "://"); i >= 0 {
		proto, s = strings.ToLower(s[:i]), s[i+3:]
	}
	if proto == "https" { proto = "http" }
	if proto == "socks" || proto == "socks5" { proto = "socks5" }
	if proto != "http" && proto != "socks5" { proto = "http" }
	if i := strings.IndexAny(s, "/ "); i >= 0 { s = s[:i] }
	if !strings.Contains(s, ":") { return proto, "" }
	return proto, s
}

func dial(proto, addr, host string) (net.Conn, error) {
	raw, err := net.DialTimeout("tcp", addr, dialTO)
	if err != nil { return nil, err }
	raw.SetDeadline(time.Now().Add(deadline))
	if proto == "socks5" {
		if err := socks5(raw, host); err != nil { raw.Close(); return nil, err }
		return raw, nil
	}
	fmt.Fprintf(raw, "CONNECT %s HTTP/1.1\r\nHost: %s\r\n\r\n", host, host)
	br := bufio.NewReader(raw)
	line, err := br.ReadString('\n')
	if err != nil { raw.Close(); return nil, err }
	if !strings.Contains(line, " 200") { raw.Close(); return nil, fmt.Errorf("connect") }
	for {
		l, err := br.ReadString('\n')
		if err != nil { raw.Close(); return nil, err }
		if l == "\r\n" || l == "\n" { break }
	}
	return &bufConn{raw, br}, nil
}

func socks5(c net.Conn, host string) error {
	if _, err := c.Write([]byte{5, 1, 0}); err != nil { return err }
	h := make([]byte, 2)
	if _, err := io.ReadFull(c, h); err != nil { return err }
	if h[0] != 5 || h[1] != 0 { return fmt.Errorf("auth") }
	sh, sp, err := net.SplitHostPort(host)
	if err != nil { return err }
	p, _ := strconv.Atoi(sp)
	req := append([]byte{5, 1, 0, 3, byte(len(sh))}, []byte(sh)...)
	req = append(req, byte(p>>8), byte(p))
	if _, err := c.Write(req); err != nil { return err }
	head := make([]byte, 4)
	if _, err := io.ReadFull(c, head); err != nil { return err }
	if head[1] != 0 { return fmt.Errorf("socks") }
	n := 0
	switch head[3] {
	case 1: n = 4
	case 3: l := make([]byte, 1); io.ReadFull(c, l); n = int(l[0])
	case 4: n = 16
	}
	_, err = io.ReadFull(c, make([]byte, n+2))
	return err
}

func tlsOver(proto, addr, host string) (*tls.Conn, error) {
	c, err := dial(proto, addr, host)
	if err != nil { return nil, err }
	tc := tls.Client(c, &tls.Config{ServerName: strings.Split(host, ":")[0], InsecureSkipVerify: true})
	if err := tc.Handshake(); err != nil { c.Close(); return nil, err }
	return tc, nil
}

func probe(proto, addr string) (string, time.Duration, float64, error) {
	c1, err := tlsOver(proto, addr, "api.ipify.org:443")
	if err != nil { return "", 0, 0, err }
	t0 := time.Now()
	fmt.Fprint(c1, "GET / HTTP/1.1\r\nHost: api.ipify.org\r\nConnection: close\r\n\r\n")
	b, err := io.ReadAll(c1)
	c1.Close()
	ttfb := time.Since(t0)
	if err != nil { return "", 0, 0, err }
	body := string(b)
	if i := strings.Index(body, "\r\n\r\n"); i >= 0 { body = body[i+4:] }
	body = strings.TrimSpace(body)
	if net.ParseIP(body) == nil { return "", 0, 0, fmt.Errorf("bad exit") }

	var kbps float64
	if c2, err := tlsOver(proto, addr, "speed.cloudflare.com:443"); err == nil {
		t1 := time.Now()
		fmt.Fprint(c2, "GET /__down?bytes=1000000 HTTP/1.1\r\nHost: speed.cloudflare.com\r\nConnection: close\r\n\r\n")
		br := bufio.NewReader(c2)
		for {
			l, e := br.ReadString('\n')
			if e != nil { break }
			if l == "\r\n" { break }
		}
		n, _ := io.Copy(io.Discard, br)
		if d := time.Since(t1); d > 0 { kbps = float64(n) / 1024 / d.Seconds() }
		c2.Close()
	}
	return body, ttfb, kbps, nil
}
