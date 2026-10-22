package main

import (
	"bufio"
	"errors"
	"flag"
	"fmt"
	"net"
	"os"
	"sort"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"syscall"
	"time"
)

var (
	endpointsPath = flag.String("endpoints", "", "Path to endpoints file")
	target        = flag.Int("target", 200000, "Target number of held connections")
	mode          = flag.String("mode", "many", "Dial mode: single | many")
	workers       = flag.Int("workers", 2000, "Number of concurrent dialers")
	holdSec       = flag.Int("hold", 60, "Hold duration in seconds after dialing completes")
	timeoutMs     = flag.Int("timeout", 2500, "Dial timeout in milliseconds")
)

func getSockstatTCPInuse() string {
	b, err := os.ReadFile("/proc/net/sockstat")
	if err != nil {
		return "n/a"
	}
	s := string(b)
	idx := strings.Index(s, "TCP: inuse ")
	if idx >= 0 {
		var inuse int
		if _, err := fmt.Sscanf(s[idx+11:], "%d", &inuse); err == nil {
			return strconv.Itoa(inuse)
		}
	}
	return "n/a"
}

func getConntrack() string {
	b, err := os.ReadFile("/proc/sys/net/netfilter/nf_conntrack_count")
	if err != nil {
		b2, err2 := os.ReadFile("/proc/net/nf_conntrack")
		if err2 == nil {
			lines := strings.Count(string(b2), "\n")
			return strconv.Itoa(lines)
		}
		return "n/a"
	}
	return strings.TrimSpace(string(b))
}

func getFDCount() string {
	entries, err := os.ReadDir("/proc/self/fd")
	if err != nil {
		return "n/a"
	}
	return strconv.Itoa(len(entries))
}

func getRSSMB() string {
	b, err := os.ReadFile("/proc/self/statm")
	if err != nil {
		return "0"
	}
	parts := strings.Fields(string(b))
	if len(parts) >= 2 {
		pages, err := strconv.ParseInt(parts[1], 10, 64)
		if err == nil {
			pageSize := int64(os.Getpagesize())
			if pageSize <= 0 {
				pageSize = 4096
			}
			return strconv.FormatInt((pages*pageSize)/(1024*1024), 10)
		}
	}
	return "0"
}

func normalizeErr(err error) string {
	if err == nil {
		return "NONE"
	}
	var sysErr *os.SyscallError
	if errors.As(err, &sysErr) {
		if errno, ok := sysErr.Err.(syscall.Errno); ok {
			return fmt.Sprintf("errno_%d(%s)", int(errno), errno.Error())
		}
		return sysErr.Err.Error()
	}
	var opErr *net.OpError
	if errors.As(err, &opErr) {
		if opErr.Timeout() {
			return "ETIMEDOUT"
		}
		if errno, ok := opErr.Err.(syscall.Errno); ok {
			return fmt.Sprintf("errno_%d(%s)", int(errno), errno.Error())
		}
		return opErr.Err.Error()
	}
	s := err.Error()
	if strings.Contains(s, "cannot assign requested address") {
		return "EADDRNOTAVAIL"
	}
	if strings.Contains(s, "too many open files") {
		return "EMFILE"
	}
	if strings.Contains(s, "connection refused") {
		return "ECONNREFUSED"
	}
	if strings.Contains(s, "connection reset by peer") {
		return "ECONNRESET"
	}
	if strings.Contains(s, "i/o timeout") || strings.Contains(s, "timed out") {
		return "ETIMEDOUT"
	}
	return s
}

func formatTopErrors(errMap map[string]int) string {
	type kv struct {
		k string
		v int
	}
	var ss []kv
	for k, v := range errMap {
		ss = append(ss, kv{k, v})
	}
	sort.Slice(ss, func(i, j int) bool {
		return ss[i].v > ss[j].v
	})
	var out []string
	for i := 0; i < len(ss) && i < 3; i++ {
		out = append(out, fmt.Sprintf("%s:%d", ss[i].k, ss[i].v))
	}
	if len(out) == 0 {
		return "none"
	}
	return strings.Join(out, ",")
}

func countStillHeld(conns []net.Conn) int {
	alive := 0
	buf := make([]byte, 1)
	for _, c := range conns {
		if c == nil {
			continue
		}
		_ = c.SetReadDeadline(time.Now().Add(5 * time.Millisecond))
		n, err := c.Read(buf)
		if n > 0 {
			alive++
			continue
		}
		if err != nil {
			if netErr, ok := err.(net.Error); ok && netErr.Timeout() {
				alive++
				continue
			}
			// Connection was closed by peer (EOF, ECONNRESET, etc)
		} else {
			alive++
		}
	}
	return alive
}

func main() {
	flag.Parse()

	if *endpointsPath == "" {
		fmt.Println("Error: -endpoints required")
		os.Exit(1)
	}

	file, err := os.Open(*endpointsPath)
	if err != nil {
		fmt.Printf("Error opening endpoints file: %v\n", err)
		os.Exit(1)
	}
	defer file.Close()

	var endpoints []string
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line != "" {
			endpoints = append(endpoints, line)
		}
	}
	if len(endpoints) == 0 {
		fmt.Println("Error: endpoints file is empty")
		os.Exit(1)
	}

	isSingle := strings.ToLower(*mode) == "single"
	firstEndpoint := endpoints[0]

	dialTimeout := time.Duration(*timeoutMs) * time.Millisecond

	var held int64
	var attempted int64
	var failed int64
	var consecutiveFails int64

	var wallReason string = "NONE"
	var wallMutex sync.Mutex

	var errMap = make(map[string]int)
	var errMutex sync.Mutex

	var heldConns []net.Conn
	var connMutex sync.Mutex

	lastMilestone := int64(0)
	var printMutex sync.Mutex

	stopChan := make(chan struct{})
	var stopOnce sync.Once
	triggerStop := func() {
		stopOnce.Do(func() {
			close(stopChan)
		})
	}

	taskQueue := make(chan string, *workers*2)

	// Feeder goroutine
	go func() {
		defer close(taskQueue)
		if isSingle {
			for {
				select {
				case <-stopChan:
					return
				case taskQueue <- firstEndpoint:
				}
				if int(atomic.LoadInt64(&held)) >= *target {
					return
				}
			}
		} else {
			for _, ep := range endpoints {
				select {
				case <-stopChan:
					return
				case taskQueue <- ep:
				}
				if int(atomic.LoadInt64(&held)) >= *target {
					return
				}
			}
		}
	}()

	var wg sync.WaitGroup
	dialerPool := *workers
	if dialerPool <= 0 {
		dialerPool = 1000
	}

	for i := 0; i < dialerPool; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for addr := range taskQueue {
				if int(atomic.LoadInt64(&held)) >= *target {
					triggerStop()
					return
				}

				atomic.AddInt64(&attempted, 1)

				var conn net.Conn
				var dialErr error

				// Retry up to 3 times on failure
				for retry := 0; retry < 3; retry++ {
					d := net.Dialer{Timeout: dialTimeout}
					conn, dialErr = d.Dial("tcp", addr)
					if dialErr == nil {
						break
					}
					// Small backoff before retry
					time.Sleep(10 * time.Millisecond)
				}

				if dialErr == nil && conn != nil {
					// Success: record held connection
					currentHeld := atomic.AddInt64(&held, 1)
					atomic.StoreInt64(&consecutiveFails, 0)

					connMutex.Lock()
					heldConns = append(heldConns, conn)
					connMutex.Unlock()

					// Check milestone (every 5000 held)
					printMutex.Lock()
					if currentHeld >= lastMilestone+5000 {
						lastMilestone = (currentHeld / 5000) * 5000
						errMutex.Lock()
						topErrs := formatTopErrors(errMap)
						errMutex.Unlock()

						fmt.Printf("CEILING held=%d attempted=%d failed=%d err=%s tcp_inuse=%s conntrack=%s fds=%s rss_mb=%s\n",
							currentHeld,
							atomic.LoadInt64(&attempted),
							atomic.LoadInt64(&failed),
							topErrs,
							getSockstatTCPInuse(),
							getConntrack(),
							getFDCount(),
							getRSSMB(),
						)
					}
					printMutex.Unlock()

					if int(currentHeld) >= *target {
						triggerStop()
						return
					}
				} else {
					// Failure
					atomic.AddInt64(&failed, 1)
					streak := atomic.AddInt64(&consecutiveFails, 1)

					errStr := normalizeErr(dialErr)
					errMutex.Lock()
					errMap[errStr]++
					errMutex.Unlock()

					if streak == 20 || (streak > 20 && streak%50 == 0) {
						wallMutex.Lock()
						if wallReason == "NONE" {
							wallReason = errStr
						}
						wallMutex.Unlock()
						fmt.Printf("WALL_REASON %s (held=%d streak=%d)\n", errStr, atomic.LoadInt64(&held), streak)
					}

					// If single mode hits a wall and cannot reach 5,000 held
					if isSingle && streak >= 100 && atomic.LoadInt64(&held) < 5000 {
						fmt.Printf("WALL_EARLY (held=%d, streak=%d, err=%s)\n", atomic.LoadInt64(&held), streak, errStr)
						triggerStop()
						return
					}

					// If many mode hits severe consecutive wall (e.g. 500 fails)
					if streak >= 500 {
						triggerStop()
						return
					}
				}
			}
		}()
	}

	wg.Wait()

	finalHeld := atomic.LoadInt64(&held)
	finalAttempted := atomic.LoadInt64(&attempted)
	finalFailed := atomic.LoadInt64(&failed)

	wallMutex.Lock()
	finalWall := wallReason
	wallMutex.Unlock()

	fmt.Printf("CEILING_DONE held=%d attempted=%d failed=%d wall_reason=%s tcp_inuse=%s conntrack=%s fds=%s rss_mb=%s\n",
		finalHeld, finalAttempted, finalFailed, finalWall,
		getSockstatTCPInuse(), getConntrack(), getFDCount(), getRSSMB(),
	)

	// Hold connections for -hold seconds
	if *holdSec > 0 && finalHeld > 0 {
		fmt.Printf("Holding %d connections for %ds...\n", finalHeld, *holdSec)
		time.Sleep(time.Duration(*holdSec) * time.Second)

		connMutex.Lock()
		connsCopy := make([]net.Conn, len(heldConns))
		copy(connsCopy, heldConns)
		connMutex.Unlock()

		stillHeld := countStillHeld(connsCopy)
		if isSingle {
			fmt.Printf("PHASEA_HOLD_AFTER_60S %d\n", stillHeld)
		} else {
			fmt.Printf("PHASEB_HOLD_AFTER_60S %d\n", stillHeld)
		}
	} else {
		if isSingle {
			fmt.Printf("PHASEA_HOLD_AFTER_60S %d\n", finalHeld)
		} else {
			fmt.Printf("PHASEB_HOLD_AFTER_60S %d\n", finalHeld)
		}
	}

	// Clean up connections on exit
	connMutex.Lock()
	for _, c := range heldConns {
		if c != nil {
			_ = c.Close()
		}
	}
	connMutex.Unlock()
}
