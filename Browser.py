import gzip
import socket
import ssl
import time
import tkinter
import tkinter.font
from html import entities

cache_safe = {}

WIDTH, HEIGHT = 800, 600
HSTEP, VSTEP = 13, 18
SCROLL_STEP = 100
MOUSE_SCROLL_STEP = 10


def lex_entities(text):
    in_entity = False
    current_entity = ""
    out = ""
    for c in text:
        if c == "&":
            in_entity = True
        elif c == ";":
            in_entity = False
            current_entity += c
            if current_entity in entities.html5:
                out += entities.html5[current_entity]
            else:
                out += "&" + current_entity
            current_entity = ""
        elif in_entity and c == " ":
            in_entity = False
            out += "&" + current_entity
            current_entity = ""
        elif in_entity:
            current_entity += c
        else:
            out += c
    if current_entity:
        out += "&" + current_entity
    return out


def request(url):
    """
    Get request to url and return headers and body
    """
    show_source = False
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

    if url in cache_safe and cache_safe[url].max_age < time.time():
        return cache_safe[url].headers, cache_safe[url].body, show_source

    # Split host part from path
    host, path = url.split("/", 1)
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
        "Accept-Encoding": "gzip, chunked",
        "User-Agent": "Best fucking browser",
    }

    headerString = ""

    for header in headers:
        headerString += f"{header}: {headers[header]}\r\n"

    s.send(
        f"GET {path} HTTP/1.1\r\n".encode("utf8") + f"{headerString}\r\n".encode("utf8")
    )

    response = s.makefile("rb", newline="\r\n")

    statusline = response.readline().decode(encoding="utf8")
    version, status, explanation = statusline.split(" ", 2)

    assert status == "200" or status[:1] == "3", f"{status}: {explanation}"

    # Read all headers and save normalized to lowercase and w/o whitespace
    headers = {}
    while True:
        line = response.readline().decode(encoding="utf8")
        if line == "\r\n":
            break
        header, value = line.split(":", 1)
        headers[header.lower()] = value.strip()

    if status[:1] == "3":
        print("Redirecting to " + headers["location"])
        return request(headers["location"])

    # We can't handle encoded content

    if "transfer-encoding" in headers and headers["transfer-encoding"] == "chunked":
        data = bytearray()
        while True:
            line = response.readline()
            size = int(line, 16)
            if size == 0:
                break
            chunk = response.read(size)
            data += chunk
            response.readline()  # throw away line? idk
    else:
        data = response.read()

    # assert "transfer-encoding" not in headers

    if "content-encoding" in headers and headers["content-encoding"] == "gzip":
        body = gzip.decompress(data).decode(encoding="utf8")
        if show_source:
            body = tranform_source(body)
        cache(headers, body, url)
        return headers, body, show_source

    assert "content-encoding" not in headers

    body = data.decode(encoding="utf8")
    if show_source:
        body = tranform_source(body)
    cache(headers, body, url)
    return headers, body, show_source


def cache(headers, body, url):
    if "cache-control" in headers:
        cache_control = headers["cache-control"].split(",")
        for value in cache_control:
            if value.split("=")[0] != "max-age":
                return
            else:
                max_age = int(value.split("=")[1])
        if max_age:
            cache_safe[url] = {
                "body": body,
                "max_age": max_age + time.time(),
            }


def tranform_source(body):
    out = "<body>"
    replace = {"<": "&lt;", ">": "&gt;", "&": "&amp;"}
    for c in body:
        if c in replace:
            out += replace[c]
        else:
            out += c

    out += "</body>"
    return out


class Browser:
    def lex(self, body):
        out = []
        text = ""
        in_tag = False
        for c in body:
            if c == "<":
                in_tag = True
                if text:
                    out.append(Text(text))
                text = ""
            elif c == ">":
                in_tag = False
                out.append(Tag(text))
                text = ""
            else:
                text += c
        if not in_tag and text:
            out.append(Text(text))
        return out

    def load(self, url):
        headers, body, show_source = request(url)
        self.tokens = self.lex(body)
        self.display_list = Layout(self.tokens).display_list
        self.draw()

    def draw(self):
        self.canvas.delete("all")
        for x, y, word, font in self.display_list:
            if y > self.scroll + self.height:
                continue
            if y + VSTEP < self.scroll:
                continue
            self.canvas.create_text(
                x, y - self.scroll, text=word, font=font, anchor="nw"
            )

    def __init__(self) -> None:
        self.window = tkinter.Tk()
        self.canvas = tkinter.Canvas(
            self.window,
            width=WIDTH,
            height=HEIGHT,
        )
        self.canvas.pack(expand=True, fill=tkinter.BOTH)
        self.scroll = 0
        self.width, self.height = WIDTH, HEIGHT
        self.window.bind("<Up>", self.scrollup)
        self.window.bind("<Down>", self.scrolldown)
        self.window.bind("<MouseWheel>", self.scroll_mouse)
        self.window.bind("<Configure>", self.configure)

    def configure(self, e):
        self.width, self.height = e.width, e.height
        self.display_list = Layout(
            self.tokens, width=e.width, height=e.height
        ).display_list
        self.draw()

    def scroll_mouse(self, e):
        self.scroll -= e.delta * MOUSE_SCROLL_STEP
        if self.scroll < 0:
            self.scroll = 0
        self.draw()

    def scrollup(self, e):
        self.scroll -= SCROLL_STEP
        if self.scroll < 0:
            self.scroll = 0
        self.draw()

    def scrolldown(self, e):
        self.scroll += SCROLL_STEP
        self.draw()


class Layout:
    def __init__(self, tokens, width=WIDTH, height=HEIGHT) -> None:
        self.display_list = []
        self.cursor_x = HSTEP
        self.cursor_y = VSTEP
        self.width, self.height = width, height
        self.weight = "normal"
        self.style = "roman"
        self.size = 16
        for tok in tokens:
            self.token(tok)

    def token(self, tok):
        if isinstance(tok, Text):
            self.text(tok)
        elif tok.tag == "i":
            style = "italic"
        elif tok.tag == "/i":
            style = "roman"
        elif tok.tag == "b":
            weight = "bold"
        elif tok.tag == "/b":
            weight = "normal"
        elif tok.tag == "br":
            self.cursor_y += (
                tkinter.font.Font(size=self.size).metrics("linespace") * 1.25
            )
            self.cursor_x = HSTEP

    def text(self, tok):
        font = tkinter.font.Font(
            size=self.size,
            weight=self.weight,
            slant=self.style,
        )
        for word in tok.text.split():
            w = font.measure(word)
            if self.cursor_x + w > self.width - HSTEP:
                self.cursor_y += font.metrics("linespace") * 1.25
                self.cursor_x = HSTEP
            self.display_list.append((self.cursor_x, self.cursor_y, word, font))
            self.cursor_x += w + font.measure(" ")


class Text:
    def __init__(self, text) -> None:
        self.text = lex_entities(text)


class Tag:
    def __init__(self, tag) -> None:
        self.tag = tag


if __name__ == "__main__":
    import sys

    Browser().load(sys.argv[1])
    tkinter.mainloop()
