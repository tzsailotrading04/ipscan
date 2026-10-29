with open("/tmp/redsocks/redsocks.c", "r") as f:
    text = f.read()

target = "assert(buffev == client->relay);"
replacement = """assert(buffev == client->relay);
\tredsocks_log_error(client, LOG_NOTICE, "DEBUG redsocks_relay_connected called!");"""

text = text.replace(target, replacement, 1)

with open("/tmp/redsocks/redsocks.c", "w") as f:
    f.write(text)

with open("/tmp/redsocks/http-connect.c", "r") as f:
    text2 = f.read()

target2 = "static void httpc_write_cb(struct bufferevent *buffev, void *_arg)\n{\n\tredsocks_client *client = _arg;"
replacement2 = """static void httpc_write_cb(struct bufferevent *buffev, void *_arg)
{
\tredsocks_client *client = _arg;
\tredsocks_log_error(client, LOG_NOTICE, "DEBUG httpc_write_cb called state=%d", client->state);"""

text2 = text2.replace(target2, replacement2, 1)

with open("/tmp/redsocks/http-connect.c", "w") as f:
    f.write(text2)

print("Patch applied")
