with open("/tmp/redsocks/http-connect.c", "r") as f:
    text = f.read()

target = "redsocks_touch_client(client);"
replacement = """redsocks_touch_client(client);
\tredsocks_log_error(client, LOG_NOTICE, "DEBUG httpc_read_cb: state=%d len=%zu", client->state, evbuffer_get_length(buffev->input));"""

if target in text:
    text = text.replace(target, replacement, 1)
    with open("/tmp/redsocks/http-connect.c", "w") as f:
        f.write(text)
    print("Patched http-connect.c successfully")
else:
    print("Target not found in http-connect.c")
