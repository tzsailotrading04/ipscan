#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <signal.h>
#include <poll.h>
#include <time.h>
#include <sys/time.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <linux/netfilter_ipv4.h>
#include <pthread.h>

#ifndef SO_ORIGINAL_DST
#define SO_ORIGINAL_DST 80
#endif

static char proxy_ip_str[64] = "104.168.19.113";
static int proxy_port = 443;
static int listen_port = 12345;
static char log_file_path[256] = "";

static void write_log(const char *msg) {
    if (log_file_path[0] == '\0') return;
    FILE *f = fopen(log_file_path, "a");
    if (!f) return;
    time_t now = time(NULL);
    char buf[32];
    ctime_r(&now, buf);
    buf[strlen(buf)-1] = '\0';
    fprintf(f, "[%s] %s\n", buf, msg);
    fclose(f);
}

struct relay_args {
    int client_fd;
    struct sockaddr_in orig_dst;
};

static void* handle_client(void* arg) {
    struct relay_args *args = (struct relay_args*)arg;
    int client_fd = args->client_fd;
    struct sockaddr_in orig_dst = args->orig_dst;
    free(args);

    char dest_ip[64];
    inet_ntop(AF_INET, &orig_dst.sin_addr, dest_ip, sizeof(dest_ip));
    int dest_port = ntohs(orig_dst.sin_port);

    // Connect to proxy
    int proxy_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (proxy_fd < 0) {
        close(client_fd);
        return NULL;
    }

    struct sockaddr_in paddr;
    memset(&paddr, 0, sizeof(paddr));
    paddr.sin_family = AF_INET;
    paddr.sin_port = htons(proxy_port);
    inet_pton(AF_INET, proxy_ip_str, &paddr.sin_addr);

    struct timeval tv;
    tv.tv_sec = 8;
    tv.tv_usec = 0;
    setsockopt(proxy_fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
    setsockopt(proxy_fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));

    if (connect(proxy_fd, (struct sockaddr*)&paddr, sizeof(paddr)) != 0) {
        close(client_fd);
        close(proxy_fd);
        return NULL;
    }

    // Send HTTP CONNECT
    char req[512];
    int req_len = snprintf(req, sizeof(req), "CONNECT %s:%d HTTP/1.1\r\nHost: %s:%d\r\n\r\n", dest_ip, dest_port, dest_ip, dest_port);
    if (write(proxy_fd, req, req_len) != req_len) {
        close(client_fd);
        close(proxy_fd);
        return NULL;
    }

    // Read response until \r\n\r\n (1 byte at a time to not consume any tunnel payload)
    char resp[1024];
    size_t n = 0;
    while (n < sizeof(resp) - 1) {
        ssize_t r = read(proxy_fd, resp + n, 1);
        if (r <= 0) break;
        n += (size_t)r;
        resp[n] = '\0';
        if (strstr(resp, "\r\n\r\n")) break;
    }

    if (!strstr(resp, " 200") && !strstr(resp, " 2")) {
        close(client_fd);
        close(proxy_fd);
        return NULL;
    }

    // Reset timeouts for streaming
    tv.tv_sec = 180;
    tv.tv_usec = 0;
    setsockopt(proxy_fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
    setsockopt(proxy_fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));
    setsockopt(client_fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
    setsockopt(client_fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));

    // Bidirectional relay
    struct pollfd fds[2];
    fds[0].fd = client_fd;
    fds[0].events = POLLIN;
    fds[1].fd = proxy_fd;
    fds[1].events = POLLIN;

    char buf[16384];
    while (1) {
        int ret = poll(fds, 2, 60000);
        if (ret <= 0) break;

        if (fds[0].revents & (POLLIN | POLLHUP | POLLERR)) {
            ssize_t bytes = read(client_fd, buf, sizeof(buf));
            if (bytes <= 0) break;
            ssize_t written = 0;
            while (written < bytes) {
                ssize_t w = write(proxy_fd, buf + written, bytes - written);
                if (w <= 0) goto done;
                written += w;
            }
        }

        if (fds[1].revents & (POLLIN | POLLHUP | POLLERR)) {
            ssize_t bytes = read(proxy_fd, buf, sizeof(buf));
            if (bytes <= 0) break;
            ssize_t written = 0;
            while (written < bytes) {
                ssize_t w = write(client_fd, buf + written, bytes - written);
                if (w <= 0) goto done;
                written += w;
            }
        }
    }

done:
    close(client_fd);
    close(proxy_fd);
    return NULL;
}

int main(int argc, char **argv) {
    signal(SIGPIPE, SIG_IGN);

    char *conf_file = NULL;
    char *pid_file = NULL;

    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "-c") == 0 && i + 1 < argc) {
            conf_file = argv[++i];
        } else if (strcmp(argv[i], "-p") == 0 && i + 1 < argc) {
            pid_file = argv[++i];
        }
    }

    if (conf_file) {
        FILE *f = fopen(conf_file, "r");
        if (f) {
            char line[256];
            while (fgets(line, sizeof(line), f)) {
                char *p = line;
                while (*p == ' ' || *p == '\t') p++;
                if (strncmp(p, "log =", 5) == 0) {
                    char *val = p + 5;
                    while (*val == ' ' || *val == '\t' || *val == '"') val++;
                    if (strncmp(val, "file:", 5) == 0) val += 5;
                    char *end = val;
                    while (*end && *end != ';' && *end != '"' && *end != '\r' && *end != '\n') end++;
                    *end = '\0';
                    strncpy(log_file_path, val, sizeof(log_file_path) - 1);
                } else if (strncmp(p, "local_port", 10) == 0) {
                    char *eq = strchr(p, '=');
                    if (eq) listen_port = atoi(eq + 1);
                } else if (strncmp(p, "port", 4) == 0 && (p[4] == ' ' || p[4] == '=')) {
                    char *eq = strchr(p, '=');
                    if (eq) proxy_port = atoi(eq + 1);
                } else if (strncmp(p, "ip", 2) == 0 && (p[2] == ' ' || p[2] == '=')) {
                    char *eq = strchr(p, '=');
                    if (eq) {
                        char *val = eq + 1;
                        while (*val == ' ' || *val == '\t' || *val == '"') val++;
                        char *end = val;
                        while (*end && *end != ';' && *end != ' ' && *end != '\t' && *end != '\r' && *end != '\n' && *end != '"') end++;
                        *end = '\0';
                        strncpy(proxy_ip_str, val, sizeof(proxy_ip_str) - 1);
                    }
                }
            }
            fclose(f);
        }
    }

    // Daemonize
    pid_t pid = fork();
    if (pid < 0) exit(1);
    if (pid > 0) {
        if (pid_file) {
            FILE *pf = fopen(pid_file, "w");
            if (pf) {
                fprintf(pf, "%d\n", pid);
                fclose(pf);
            }
        }
        exit(0);
    }

    setsid();

    // Redirect standard fds to /dev/null so parent subprocess doesn't block on inherited pipes
    int devnull = open("/dev/null", O_RDWR);
    if (devnull >= 0) {
        dup2(devnull, 0);
        dup2(devnull, 1);
        dup2(devnull, 2);
        if (devnull > 2) close(devnull);
    }

    int listen_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (listen_fd < 0) exit(1);

    int opt = 1;
    setsockopt(listen_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    struct sockaddr_in laddr;
    memset(&laddr, 0, sizeof(laddr));
    laddr.sin_family = AF_INET;
    laddr.sin_port = htons(listen_port);
    laddr.sin_addr.s_addr = htonl(INADDR_ANY);

    if (bind(listen_fd, (struct sockaddr*)&laddr, sizeof(laddr)) != 0) {
        exit(1);
    }

    if (listen(listen_fd, 512) != 0) {
        exit(1);
    }

    while (1) {
        struct sockaddr_in caddr;
        socklen_t clen = sizeof(caddr);
        int cfd = accept(listen_fd, (struct sockaddr*)&caddr, &clen);
        if (cfd < 0) continue;

        struct sockaddr_in orig_dst;
        socklen_t dlen = sizeof(orig_dst);
        if (getsockopt(cfd, SOL_IP, SO_ORIGINAL_DST, &orig_dst, &dlen) != 0) {
            close(cfd);
            continue;
        }

        struct relay_args *args = malloc(sizeof(struct relay_args));
        if (!args) {
            close(cfd);
            continue;
        }
        args->client_fd = cfd;
        args->orig_dst = orig_dst;

        pthread_t th;
        pthread_attr_t attr;
        pthread_attr_init(&attr);
        pthread_attr_setdetachstate(&attr, PTHREAD_CREATE_DETACHED);
        pthread_create(&th, &attr, handle_client, args);
        pthread_attr_destroy(&attr);
    }

    return 0;
}
