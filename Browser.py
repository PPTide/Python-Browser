import socket
import ssl


def request(url):
    """
        Get request to url and return headers and body
    """
    # Expect use of a http:// domain
    assert url.startswith("http://")
    url = url[len("http://"):]

    # Split host part from path
    host, path = url.split("/", 2)
    path = "/" + path

    # Init socket
    s = socket.socket(
        family=socket.AF_INET,
        type=socket.SOCK_STREAM,
        proto=socket.IPPROTO_TCP,
    )

    # Connect to host using socket
    s.connect((host, 80))

    s.send(f"GET {path} HTTP/1.0\r\n".encode("utf8") +
           f"Host: {host}\r\n\r\n".encode("utf8"))

    response = s.makefile("r", encoding="utf8", newline="\r\n")

    statusline = response.readline()
    version, status, explanation = statusline.split(" ", 2)
    assert status == "200", f"{status}: {explanation}"

    # Read all headers and save normalized to lowercase and w/o whitespace
    headers = {}
    while True:
        line = response.readline()
        if line == "\r\n":
            break
        header, value = line.split(":", 1)
        headers[header.lower()] = value.strip()

    # We can't handle encoded content
    assert "transfer-encoding" not in headers
    assert "content-encoding" not in headers

    body = response.read()
    return headers, body


def show(body):
    in_angle = False
    for c in body:
        if c == "<":
            in_angle = True
        elif c == ">":
            in_angle = False
        elif not in_angle:
            print(c, end="")


def load(url):
    headers, body = request(url)
    show(body)


if __name__ == "__main__":
    import sys
    load(sys.argv[1])
