import subprocess

data = subprocess.run(["strings", "-a", "/tmp/traff_cli"], capture_output=True, text=True, errors="ignore").stdout
matches = []
for line in data.splitlines():
    l = line.strip().lower()
    if any(k in l for k in ["bincode", "prost", "protobuf", "serde", "postcard", "borsh", "flatbuffers", "capnp", "rmp", "msgpack"]):
        matches.append(line.strip())

print(f"Total serialization matches: {len(matches)}")
for m in matches[:30]:
    print(m)
