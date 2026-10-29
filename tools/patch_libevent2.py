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

with open("/tmp/redsocks/redsocks.c", "r") as f:
    text = f.read()

# 1. Forward decl
text = text.replace(
    "static int redsocks_start_bufferpump(redsocks_client *client);",
    "static int redsocks_start_bufferpump(redsocks_client *client);\nstatic void redsocks_event_error(struct bufferevent *buffev, short what, void *_arg);\nstatic void redsocks_relay_connected(struct bufferevent *buffev, void *_arg);"
)

# 2. BEV_EVENT_CONNECTED in redsocks_event_error
target_err = """	redsocks_touch_client(client);

	if (what == (EVBUFFER_READ|EVBUFFER_EOF)) {"""

replacement_err = """	redsocks_touch_client(client);

	if (what & BEV_EVENT_CONNECTED) {
		if (buffev == client->relay) {
			redsocks_relay_connected(buffev, client);
			return;
		}
	}

	if (what == (EVBUFFER_READ|EVBUFFER_EOF)) {"""

assert target_err in text, "target_err not found"
text = text.replace(target_err, replacement_err, 1)

# 3. bufferevent_setcb in redsocks_relay_connected
target_conn = """	client->relay->readcb = client->instance->relay_ss->readcb;
	client->relay->writecb = client->instance->relay_ss->writecb;"""

replacement_conn = """	bufferevent_setcb(client->relay, client->instance->relay_ss->readcb, client->instance->relay_ss->writecb, redsocks_event_error, client);"""

assert target_conn in text, "target_conn not found"
text = text.replace(target_conn, replacement_conn, 1)

# 4. bufferevent_setcb and flush in redsocks_start_bufferpump
target_pump = """	client->client->readcb = redsocks_relay_clientreadcb;
	client->client->writecb = redsocks_relay_clientwritecb;
	client->relay->readcb = redsocks_relay_relayreadcb;
	client->relay->writecb = redsocks_relay_relaywritecb;

	int error = bufferevent_enable(client->client, (EV_READ|EV_WRITE) & ~(client->client_evshut));
	if (!error)
		error = bufferevent_enable(client->relay, (EV_READ|EV_WRITE) & ~(client->relay_evshut));
	if (error)
		redsocks_log_errno(client, LOG_ERR, "bufferevent_enable");
	return error;"""

replacement_pump = """	bufferevent_setcb(client->client, redsocks_relay_clientreadcb, redsocks_relay_clientwritecb, redsocks_event_error, client);
	bufferevent_setcb(client->relay, redsocks_relay_relayreadcb, redsocks_relay_relaywritecb, redsocks_event_error, client);

	int error = bufferevent_enable(client->client, (EV_READ|EV_WRITE) & ~(client->client_evshut));
	if (!error)
		error = bufferevent_enable(client->relay, (EV_READ|EV_WRITE) & ~(client->relay_evshut));
	if (!error && evbuffer_get_length(client->client->input) > 0) {
		redsocks_relay_clientreadcb(client->client, client);
	}
	if (error)
		redsocks_log_errno(client, LOG_ERR, "bufferevent_enable");
	return error;"""

assert target_pump in text, "target_pump not found"
text = text.replace(target_pump, replacement_pump, 1)

with open("/tmp/redsocks/redsocks.c", "w") as f:
    f.write(text)

print("Successfully applied full Libevent 2.1 compatibility patch to redsocks!")
