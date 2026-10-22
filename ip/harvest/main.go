package main

import (
	"bufio"
	"crypto/tls"
	"fmt"
	"io"
	"net"
	"os"
	"runtime"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

var (
	dialTO      = 500 * time.Millisecond
	deadline    = 15 * time.Second
	totalDialMs int64
	totalReadMs int64
	totalDials  int64
	totalReads  int64
)

type bufConn struct {
	net.Conn
	r *bufio.Reader
}

func (b *bufConn) Read(p []byte) (int, error) { return b.r.Read(p) }

func probe(addr string, dialTO, readTO time.Duration) (bool, string) {
	tDial0 := time.Now()
	d := net.Dialer{Timeout: dialTO}
	conn, err := d.Dial("tcp", addr)
	dialDuration := time.Since(tDial0)
	atomic.AddInt64(&totalDialMs, dialDuration.Milliseconds())
	atomic.AddInt64(&totalDials, 1)
	if err != nil {
		return false, ""
	}
	if tcp, ok := conn.(*net.TCPConn); ok {
		tcp.SetLinger(0)
	} else {
		fmt.Println("LINGER_FAIL: conn is not *net.TCPConn")
	}
	defer conn.Close()

	tRead0 := time.Now()
	defer func() {
		readDuration := time.Since(tRead0)
		atomic.AddInt64(&totalReadMs, readDuration.Milliseconds())
		atomic.AddInt64(&totalReads, 1)
	}()

	// --- stage 1: CONNECT, hard 8s cap ---
	conn.SetDeadline(time.Now().Add(8 * time.Second))

	br := bufio.NewReaderSize(conn, 512)
	if _, err := conn.Write([]byte(
		"CONNECT api.ipify.org:443 HTTP/1.1\r\nHost: api.ipify.org:443\r\n\r\n")); err != nil {
		return false, ""
	}

	line, err := br.ReadString('\n')
	if err != nil || (!strings.Contains(line, " 200") && !strings.Contains(line, " 2")) {
		return false, ""
	}
	for {
		l, err := br.ReadString('\n')
		if err != nil {
			return false, ""
		}
		if l == "\r\n" || l == "\n" {
			break
		}
	}

	// --- stage 2: only now extend for TLS + GET ---
	conn.SetDeadline(time.Now().Add(readTO))

	tlsConn := tls.Client(&bufConn{conn, br}, &tls.Config{ServerName: "api.ipify.org", InsecureSkipVerify: true})
	if err := tlsConn.Handshake(); err != nil {
		return false, ""
	}
	if _, err := tlsConn.Write([]byte(
		"GET / HTTP/1.1\r\nHost: api.ipify.org\r\nConnection: close\r\n\r\n")); err != nil {
		return false, ""
	}

	brTLS := bufio.NewReaderSize(tlsConn, 512)
	st, err := brTLS.ReadString('\n')
	if err != nil || (!strings.Contains(st, " 200") && !strings.Contains(st, " 2")) {
		return false, ""
	}
	for {
		l, err := brTLS.ReadString('\n')
		if err != nil {
			return false, ""
		}
		if l == "\r\n" || l == "\n" {
			break
		}
	}
	body, _ := io.ReadAll(io.LimitReader(brTLS, 64))
	s := strings.TrimSpace(string(body))
	if net.ParseIP(s) == nil {
		return false, ""
	}
	return true, s
}

func parse(line string) string {
	s := line
	if i := strings.Index(s, "://"); i >= 0 {
		s = s[i+3:]
	}
	if i := strings.IndexAny(s, "/ "); i >= 0 {
		s = s[:i]
	}
	if !strings.Contains(s, ":") {
		s = s + ":8080"
	}
	return s
}

func main() {
	if len(os.Args) < 3 {
		return
	}
	in, out := os.Args[1], os.Args[2]
	f, err := os.Open(in)
	if err != nil {
		return
	}
	defer f.Close()
	o, err := os.Create(out)
	if err != nil {
		return
	}
	defer o.Close()

	var lines []string
	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 1<<20), 1<<20)
	for sc.Scan() {
		if s := strings.TrimSpace(sc.Text()); s != "" {
			lines = append(lines, s)
		}
	}

	var mu sync.Mutex
	var wg sync.WaitGroup
	concurrency := 24000
	if c := os.Getenv("CONCURRENCY"); c != "" {
		if n, err := strconv.Atoi(c); err == nil && n > 0 {
			concurrency = n
		}
	}
	if len(os.Args) >= 4 {
		if n, err := strconv.Atoi(os.Args[3]); err == nil && n > 0 {
			concurrency = n
		}
	}
	if d := os.Getenv("DIAL_TIMEOUT_MS"); d != "" {
		if n, err := strconv.Atoi(d); err == nil && n > 0 {
			dialTO = time.Duration(n) * time.Millisecond
		}
	} else if d := os.Getenv("DIAL_TIMEOUT_SEC"); d != "" {
		if n, err := strconv.Atoi(d); err == nil && n > 0 {
			dialTO = time.Duration(n) * time.Second
		}
	}
	if len(os.Args) >= 5 {
		if n, err := strconv.Atoi(os.Args[4]); err == nil && n > 0 {
			dialTO = time.Duration(n) * time.Millisecond
		}
	}
	if r := os.Getenv("READ_TIMEOUT_MS"); r != "" {
		if n, err := strconv.Atoi(r); err == nil && n > 0 {
			deadline = time.Duration(n) * time.Millisecond
		}
	} else if r := os.Getenv("READ_TIMEOUT_SEC"); r != "" {
		if n, err := strconv.Atoi(r); err == nil && n > 0 {
			deadline = time.Duration(n) * time.Second
		}
	}
	if len(os.Args) >= 6 {
		if n, err := strconv.Atoi(os.Args[5]); err == nil && n > 0 {
			deadline = time.Duration(n) * time.Millisecond
		}
	}

	wArg, dArg, rArg := "24000", "500", "15000"
	if len(os.Args) >= 4 {
		wArg = os.Args[3]
	}
	if len(os.Args) >= 5 {
		dArg = os.Args[4]
	}
	if len(os.Args) >= 6 {
		rArg = os.Args[5]
	}
	fmt.Printf("ARGS workers=%s dial=%s read=%s\n", wArg, dArg, rArg)

	// Sample sockstat and goroutines concurrently during execution
	var maxInuse int
	var maxGoroutines int
	stopStats := make(chan struct{})
	go func() {
		ticker := time.NewTicker(200 * time.Millisecond)
		defer ticker.Stop()
		for {
			select {
			case <-ticker.C:
				g := runtime.NumGoroutine()
				if g > maxGoroutines {
					maxGoroutines = g
				}
				if b, err := os.ReadFile("/proc/net/sockstat"); err == nil {
					s := string(b)
					if idx := strings.Index(s, "TCP: inuse "); idx >= 0 {
						var inuse int
						fmt.Sscanf(s[idx+11:], "%d", &inuse)
						if inuse > maxInuse {
							maxInuse = inuse
						}
					}
				}
			case <-stopStats:
				return
			}
		}
	}()

	sem := make(chan struct{}, concurrency)
	for _, l := range lines {
		wg.Add(1)
		sem <- struct{}{}
		go func(line string) {
			defer wg.Done()
			defer func() { <-sem }()
			addr := parse(line)
			if addr == "" {
				return
			}
			t0 := time.Now()
			ok, exit := probe(addr, dialTO, deadline)
			if !ok || exit == "" {
				return
			}
			ttfb := time.Since(t0)
			mu.Lock()
			fmt.Fprintf(o, "%s %s %d 0\n", addr, exit, ttfb.Milliseconds())
			mu.Unlock()
		}(l)
	}
	wg.Wait()
	close(stopStats)

	var dialAvg, readAvg float64
	if td := atomic.LoadInt64(&totalDials); td > 0 {
		dialAvg = float64(atomic.LoadInt64(&totalDialMs)) / float64(td)
	}
	if tr := atomic.LoadInt64(&totalReads); tr > 0 {
		readAvg = float64(atomic.LoadInt64(&totalReadMs)) / float64(tr)
	}
	fmt.Printf("TIMING dial_avg_ms=%.1f read_avg_ms=%.1f\n", dialAvg, readAvg)

	var ss string
	if b, err := os.ReadFile("/proc/net/sockstat"); err == nil {
		ss = strings.ReplaceAll(strings.TrimSpace(string(b)), "\n", " | ")
	} else {
		ss = "n/a"
	}
	fmt.Printf("SOCKSTAT: %s (peak_tcp_inuse=%d peak_goroutines=%d)\n", ss, maxInuse, maxGoroutines)
	fmt.Printf("GOROUTINES: %d\n", runtime.NumGoroutine())
}
