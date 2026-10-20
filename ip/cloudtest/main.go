package main

import (
	"bufio"
	"bytes"
	"context"
	"crypto/tls"
	"encoding/binary"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httptrace"
	"os"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

const (
	conc           = 2000
	connectTimeout = 3 * time.Second
	totalTimeout   = 12 * time.Second
)

var ipv4Re = regexp.MustCompile(`^\d+\.\d+\.\d+\.\d+$`)
var ipifyIPs []net.IP

func initDNS() {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	ips, _ := net.DefaultResolver.LookupIP(ctx, "ip4", "api.ipify.org")
	for _, ip := range ips {
		if ip4 := ip.To4(); ip4 != nil {
			ipifyIPs = append(ipifyIPs, ip4)
		}
	}
}

type zeroLingerConn struct {
	net.Conn
}

func (c *zeroLingerConn) Close() error {
	if tc, ok := c.Conn.(*net.TCPConn); ok {
		_ = tc.SetLinger(0)
	}
	return c.Conn.Close()
}

type prefixConn struct {
	net.Conn
	r io.Reader
}

func (c *prefixConn) Read(p []byte) (int, error) {
	return c.r.Read(p)
}

var errTCPDialFailed = errors.New("tcp dial failed")

func dialTCP(ctx context.Context, addr string) (net.Conn, error) {
	for attempt := 0; attempt < 3; attempt++ {
		d := net.Dialer{Timeout: connectTimeout}
		c, err := d.DialContext(ctx, "tcp", addr)
		if err != nil {
			msg := err.Error()
			if strings.Contains(msg, "Only one usage") || strings.Contains(msg, "sufficient buffer space") || strings.Contains(msg, "cannot assign requested address") {
				time.Sleep(200 * time.Millisecond)
				continue
			}
			return nil, fmt.Errorf("%w: %v", errTCPDialFailed, err)
		}
		return &zeroLingerConn{Conn: c}, nil
	}
	return nil, errTCPDialFailed
}

func dialHTTPConnect(ctx context.Context, proxyAddr, targetAddr string) (net.Conn, error) {
	conn, err := dialTCP(ctx, proxyAddr)
	if err != nil {
		return nil, err
	}
	conn.SetDeadline(time.Now().Add(8 * time.Second))

	req := "CONNECT " + targetAddr + " HTTP/1.1\r\nHost: " + targetAddr + "\r\nUser-Agent: Mozilla/5.0\r\nProxy-Connection: keep-alive\r\n\r\n"
	if _, err := conn.Write([]byte(req)); err != nil {
		conn.Close()
		return nil, err
	}

	br := bufio.NewReader(conn)
	status, err := br.ReadString('\n')
	if err != nil {
		conn.Close()
		return nil, err
	}
	for {
		line, err := br.ReadString('\n')
		if err != nil {
			conn.Close()
			return nil, err
		}
		if line == "\r\n" || line == "\n" {
			break
		}
	}
	if !strings.Contains(status, " 200") {
		conn.Close()
		return nil, fmt.Errorf("http connect status: %s", strings.TrimSpace(status))
	}
	var out net.Conn = conn
	if br.Buffered() > 0 {
		out = &prefixConn{Conn: conn, r: io.MultiReader(br, conn)}
	}
	out.SetDeadline(time.Time{})
	return out, nil
}

func dialSocks5(ctx context.Context, proxyAddr, targetAddr string) (net.Conn, error) {
	host, portStr, err := net.SplitHostPort(targetAddr)
	if err != nil {
		return nil, err
	}
	port, err := strconv.Atoi(portStr)
	if err != nil {
		return nil, err
	}

	conn, err := dialTCP(ctx, proxyAddr)
	if err != nil {
		return nil, err
	}
	conn.SetDeadline(time.Now().Add(8 * time.Second))

	// Greeting: VER=5, NMETHODS=1, METHOD=0 (no auth)
	if _, err := conn.Write([]byte{0x05, 0x01, 0x00}); err != nil {
		conn.Close()
		return nil, err
	}
	var greetResp [2]byte
	if _, err := io.ReadFull(conn, greetResp[:]); err != nil {
		conn.Close()
		return nil, err
	}
	if greetResp[0] != 0x05 || greetResp[1] != 0x00 {
		conn.Close()
		return nil, fmt.Errorf("socks5 auth rejected: %x", greetResp)
	}

	// CONNECT request with domain name (ATYP=0x03)
	hb := []byte(host)
	req := make([]byte, 0, 7+len(hb))
	req = append(req, 0x05, 0x01, 0x00, 0x03, byte(len(hb)))
	req = append(req, hb...)
	req = append(req, byte(port>>8), byte(port&0xff))
	if _, err := conn.Write(req); err != nil {
		conn.Close()
		return nil, err
	}

	var hdr [4]byte
	if _, err := io.ReadFull(conn, hdr[:]); err != nil {
		conn.Close()
		return nil, err
	}
	if hdr[0] != 0x05 || hdr[1] != 0x00 {
		conn.Close()
		return nil, fmt.Errorf("socks5 connect rejected: 0x%02x", hdr[1])
	}

	var skip int
	switch hdr[3] {
	case 0x01:
		skip = 4 + 2
	case 0x03:
		var dlen [1]byte
		if _, err := io.ReadFull(conn, dlen[:]); err != nil {
			conn.Close()
			return nil, err
		}
		skip = int(dlen[0]) + 2
	case 0x04:
		skip = 16 + 2
	default:
		conn.Close()
		return nil, fmt.Errorf("socks5 unknown atyp: 0x%02x", hdr[3])
	}
	if skip > 0 {
		buf := make([]byte, skip)
		if _, err := io.ReadFull(conn, buf); err != nil {
			conn.Close()
			return nil, err
		}
	}
	conn.SetDeadline(time.Time{})
	return conn, nil
}

func dialSocks4(ctx context.Context, proxyAddr, targetAddr string) (net.Conn, error) {
	host, portStr, err := net.SplitHostPort(targetAddr)
	if err != nil {
		return nil, err
	}
	port, err := strconv.Atoi(portStr)
	if err != nil {
		return nil, err
	}
	var ip4 net.IP
	if host == "api.ipify.org" && len(ipifyIPs) > 0 {
		ip4 = ipifyIPs[0]
	} else {
		ips, err := net.DefaultResolver.LookupIP(ctx, "ip4", host)
		if err != nil || len(ips) == 0 {
			return nil, err
		}
		ip4 = ips[0].To4()
	}

	conn, err := dialTCP(ctx, proxyAddr)
	if err != nil {
		return nil, err
	}
	conn.SetDeadline(time.Now().Add(8 * time.Second))

	var req [9]byte
	req[0] = 0x04
	req[1] = 0x01
	binary.BigEndian.PutUint16(req[2:4], uint16(port))
	copy(req[4:8], ip4)
	req[8] = 0x00

	if _, err := conn.Write(req[:]); err != nil {
		conn.Close()
		return nil, err
	}
	var resp [8]byte
	if _, err := io.ReadFull(conn, resp[:]); err != nil {
		conn.Close()
		return nil, err
	}
	if resp[1] != 0x5a {
		conn.Close()
		return nil, fmt.Errorf("socks4 rejected: 0x%02x", resp[1])
	}
	conn.SetDeadline(time.Time{})
	return conn, nil
}

type probeResult struct {
	alive  bool
	exitIP string
	ttfbMs int64
}

func testOneScheme(scheme, addr string) (probeResult, bool) {
	tr := &http.Transport{
		DisableKeepAlives:   true,
		TLSHandshakeTimeout: 6 * time.Second,
		TLSClientConfig:     &tls.Config{InsecureSkipVerify: false},
		DialContext: func(ctx context.Context, network, targetAddr string) (net.Conn, error) {
			switch scheme {
			case "http":
				return dialHTTPConnect(ctx, addr, targetAddr)
			case "socks5":
				return dialSocks5(ctx, addr, targetAddr)
			case "socks4":
				return dialSocks4(ctx, addr, targetAddr)
			default:
				return nil, fmt.Errorf("unknown scheme: %s", scheme)
			}
		},
	}
	defer tr.CloseIdleConnections()

	ctx, cancel := context.WithTimeout(context.Background(), totalTimeout)
	defer cancel()

	var wroteAt, firstByteAt time.Time
	trace := &httptrace.ClientTrace{
		WroteRequest: func(info httptrace.WroteRequestInfo) {
			if wroteAt.IsZero() {
				wroteAt = time.Now()
			}
		},
		GotFirstResponseByte: func() {
			if firstByteAt.IsZero() {
				firstByteAt = time.Now()
			}
		},
	}

	req, _ := http.NewRequestWithContext(httptrace.WithClientTrace(ctx, trace), "GET", "https://api.ipify.org", nil)
	cl := &http.Client{Transport: tr, Timeout: totalTimeout}
	tStart := time.Now()
	resp, err := cl.Do(req)
	if err != nil {
		return probeResult{}, errors.Is(err, errTCPDialFailed)
	}
	b, _ := io.ReadAll(io.LimitReader(resp.Body, 64))
	resp.Body.Close()

	ipStr := strings.TrimSpace(string(b))
	if !ipv4Re.MatchString(ipStr) {
		return probeResult{}, false
	}
	parsedIP := net.ParseIP(ipStr)
	if parsedIP == nil || parsedIP.To4() == nil {
		return probeResult{}, false
	}

	var ttfb time.Duration
	if !wroteAt.IsZero() && !firstByteAt.IsZero() && firstByteAt.After(wroteAt) {
		ttfb = firstByteAt.Sub(wroteAt)
	} else {
		ttfb = time.Since(tStart)
	}

	return probeResult{
		alive:  true,
		exitIP: parsedIP.To4().String(),
		ttfbMs: ttfb.Milliseconds(),
	}, false
}

func probeAuto(addr string) probeResult {
	for _, sc := range []string{"http", "socks5", "socks4"} {
		res, tcpFailed := testOneScheme(sc, addr)
		if res.alive {
			return res
		}
		if tcpFailed {
			break
		}
	}
	return probeResult{}
}

func parseAddr(s string) string {
	s = strings.TrimSpace(s)
	if s == "" || strings.HasPrefix(s, "#") {
		return ""
	}
	if i := strings.Index(s, "://"); i >= 0 {
		s = s[i+3:]
	}
	parts := strings.Split(s, ":")
	if len(parts) < 2 {
		return ""
	}
	ip := net.ParseIP(strings.TrimSpace(parts[0]))
	if ip == nil || ip.To4() == nil {
		return ""
	}
	port, err := strconv.Atoi(strings.TrimSpace(parts[1]))
	if err != nil || port < 1 || port > 65535 {
		return ""
	}
	return fmt.Sprintf("%s:%d", ip.To4().String(), port)
}

func main() {
	if len(os.Args) < 3 {
		fmt.Fprintln(os.Stderr, "usage: cloudtest <infile> <outfile>")
		os.Exit(1)
	}
	inPath, outPath := os.Args[1], os.Args[2]
	initDNS()

	rawBytes, err := os.ReadFile(inPath)
	if err != nil {
		fmt.Fprintln(os.Stderr, "open:", err)
		os.Exit(1)
	}
	// Strip UTF-8 BOM if present
	rawBytes = bytes.TrimPrefix(rawBytes, []byte{0xef, 0xbb, 0xbf})

	var addrs []string
	sc := bufio.NewScanner(bytes.NewReader(rawBytes))
	sc.Buffer(make([]byte, 1<<20), 1<<20)
	for sc.Scan() {
		if a := parseAddr(sc.Text()); a != "" {
			addrs = append(addrs, a)
		}
	}

	outFile, err := os.Create(outPath)
	if err != nil {
		fmt.Fprintln(os.Stderr, "create:", err)
		os.Exit(1)
	}
	w := bufio.NewWriter(outFile)

	var mu sync.Mutex
	var done, live int64
	sem := make(chan struct{}, conc)
	var wg sync.WaitGroup

	for _, addr := range addrs {
		wg.Add(1)
		sem <- struct{}{}
		go func(a string) {
			defer wg.Done()
			defer func() { <-sem }()
			r := probeAuto(a)
			d := atomic.AddInt64(&done, 1)
			if r.alive {
				atomic.AddInt64(&live, 1)
				mu.Lock()
				fmt.Fprintf(w, "%s %s %d\n", a, r.exitIP, r.ttfbMs)
				w.Flush()
				mu.Unlock()
			}
			if d%10000 == 0 {
				fmt.Printf("  %d/%d  live=%d\n", d, len(addrs), atomic.LoadInt64(&live))
			}
		}(addr)
	}
	wg.Wait()
	w.Flush()
	outFile.Close()
	fmt.Printf("DONE checked=%d live=%d\n", done, live)
}
