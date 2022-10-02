from html import entities
import socket
import ssl


def request(url):
    """
    Get request to url and return headers and body
    """
    if url[: len("view-source:")] == "view-source:":
        show_source = True
        url = url[len("view-source:") :]

    if url[: len("data:text/html,")] == "data:text/html,":
        return {}, url[len("data:text/html,") :], show_source

    # get scheme
    scheme, url = url.split("://", 1)
    assert scheme in ["http", "https", "file"], f"Unknown scheme {scheme}"

    if scheme == "file":
        return {}, open(url).read(), show_source

    port = 80 if scheme == "http" else 443

    # Split host part from path
    host, path = url.split("/", 2)
    path = "/" + path

    # Init socket
    s = socket.socket(
        family=socket.AF_INET,
        type=socket.SOCK_STREAM,
        proto=socket.IPPROTO_TCP,
    )

    if scheme == "https":
        ctx = ssl.create_default_context()
        s = ctx.wrap_socket(s, server_hostname=host)

    if ":" in host:
        host, port = host.split(":", 1)
        port = int(port)

    # Connect to host using socket
    s.connect((host, port))

    headers = {
        "Host": host,
        "Connection": "close",
        "User-Agent": "Best fucking browser",
    }

    headerString = ""

    for header in headers:
        headerString += f"{header}: {headers[header]}\r\n"

    s.send(
        f"GET {path} HTTP/1.1\r\n".encode("utf8") + f"{headerString}\r\n".encode("utf8")
    )

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
    return headers, body, show_source


def show(body):
    in_angle = False
    in_body = False
    in_entitie = False
    current_tag = ""
    current_entitie = ""
    for c in body:
        if c == "<":
            current_tag = ""
            in_angle = True
        elif c == ">":
            if current_tag[:4] == "body":
                in_body = True
            elif current_tag[:5] == "/body":
                in_body = False
            in_angle = False
        elif c == "&":
            in_entitie = True
            current_entitie = ""
        elif c == ";" and in_entitie:
            current_entitie += c
            in_entitie = False
            if current_entitie in entities.html5:
                print(entities.html5[current_entitie], end="")
            else:
                print(f"&{current_entitie};", end="")
        elif in_entitie:
            current_entitie += c
        elif in_angle:
            current_tag += c
        elif not in_angle and in_body:
            print(c, end="")


def source_show(body):
    print(body)


def load(url):
    headers, body, show_source = request(url)
    source_show(body) if show_source else show(body)


if __name__ == "__main__":
    import sys

    load(sys.argv[1])
