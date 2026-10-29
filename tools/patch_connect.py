with open("/tmp/redsocks/utils.c", "r") as f:
    text = f.read()

target = """struct bufferevent* red_connect_relay(struct sockaddr_in *addr, evbuffercb writecb, everrorcb errorcb, void *cbarg)
{
	struct bufferevent *retval = NULL;
	int relay_fd = -1;
	int error;

	relay_fd = red_socket_client(SOCK_STREAM);

	error = connect(relay_fd, (struct sockaddr*)addr, sizeof(*addr));
	if (error && errno != EINPROGRESS) {
		log_errno(LOG_NOTICE, "connect");
		goto fail;
	}

	retval = bufferevent_new(relay_fd, NULL, writecb, errorcb, cbarg);
	if (!retval) {
		log_errno(LOG_ERR, "bufferevent_new");
		goto fail;
	}

	relay_fd = -1;

	error = bufferevent_enable(retval, EV_WRITE); // we wait for connection...
	if (error) {
		log_errno(LOG_ERR, "bufferevent_enable");
		goto fail;
	}

	return retval;

fail:
	if (relay_fd != -1)
		redsocks_close(relay_fd);
	if (retval)
		redsocks_bufferevent_free(retval);
	return NULL;
}"""

replacement = """struct bufferevent* red_connect_relay(struct sockaddr_in *addr, evbuffercb writecb, everrorcb errorcb, void *cbarg)
{
	int relay_fd = red_socket_client(SOCK_STREAM);
	if (relay_fd == -1) return NULL;

	struct bufferevent *retval = bufferevent_socket_new(NULL, relay_fd, 0);
	if (!retval) {
		redsocks_close(relay_fd);
		return NULL;
	}

	bufferevent_setcb(retval, NULL, writecb, errorcb, cbarg);

	if (bufferevent_socket_connect(retval, (struct sockaddr*)addr, sizeof(*addr)) < 0) {
		bufferevent_free(retval);
		return NULL;
	}

	return retval;
}"""

assert target in text, "target not found in utils.c"
text = text.replace(target, replacement, 1)

with open("/tmp/redsocks/utils.c", "w") as f:
    f.write(text)

print("Patched utils.c with bufferevent_socket_connect!")
