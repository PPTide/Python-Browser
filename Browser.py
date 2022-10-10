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
SELF_CLOSING_TAGS = [
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
]
FONTS = {}


def get_font(size, weight, slant):
    key = (size, weight, slant)
    if key not in FONTS:
        font = tkinter.font.Font(
            size=size,
            weight=weight,
            slant=slant,
        )
        FONTS[key] = font
    return FONTS[key]


def lex_entities(text):
    in_entity = False
    current_entity = ""
    out = ""
    for c in text:
        if c == "&":
            in_entity = True
        elif c == ";" and in_entity:
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


def print_tree(node, indent=0):
    print(" " * indent, node)
    for child in node.children:
        print_tree(child, indent + 2)


class Browser:
    def load(self, url):
        headers, body, show_source = request(url)
        self.nodes = HTMLParser(body).parse()
        self.display_list = Layout(self.nodes).display_list
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
            self.nodes, width=e.width, height=e.height
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
    def __init__(self, nodes, width=WIDTH, height=HEIGHT) -> None:
        self.display_list = []
        self.line = []
        self.cursor_x = HSTEP
        self.cursor_y = VSTEP
        self.width, self.height = width, height
        self.weight = "normal"
        self.style = "roman"
        self.size = 16
        self.recurse(nodes)
        self.flush()

    def open_tag(self, tag):
        if tag == "i":
            self.style = "italic"
        elif tag == "b":
            self.weight = "bold"
        elif tag == "small":
            self.size -= 2
        elif tag == "big":
            self.size += 4
        elif tag == "br":
            self.flush()

    def close_tag(self, tag):
        if tag == "i":
            style = "roman"
        elif tag == "b":
            weight = "normal"
        elif tag == "small":
            self.size += 2
        elif tag == "big":
            self.size -= 4
        elif tag == "p":
            self.flush()
            self.cursor_y + VSTEP

    def recurse(self, tree):
        if isinstance(tree, Text):
            self.text(tree)
        else:
            self.open_tag(tree.tag)
            for child in tree.children:
                self.recurse(child)
            self.close_tag(tree.tag)

    def flush(self):
        if not self.line:
            return
        metrics = [font.metrics() for x, word, font in self.line]
        max_ascent = max([metric["ascent"] for metric in metrics])
        max_descent = max([metric["descent"] for metric in metrics])
        baseline = self.cursor_y + 1.25 * max_ascent
        for x, word, font in self.line:
            y = baseline - font.metrics("ascent")
            self.display_list.append((x, y, word, font))
        self.cursor_x = HSTEP
        self.cursor_y = baseline + 1.25 * max_descent
        self.line = []

    def text(self, tok):
        font = get_font(self.size, self.weight, self.style)
        for word in tok.text.split():
            w = font.measure(word)
            if self.cursor_x + w > self.width - HSTEP:
                self.flush()
            self.line.append((self.cursor_x, word, font))
            self.cursor_x += w + font.measure(" ")


class HTMLParser:
    HEAD_TAGS = [
        "base",
        "basefont",
        "bgsound",
        "noscript",
        "link",
        "meta",
        "title",
        "style",
        "script",
    ]

    def __init__(self, body) -> None:
        self.body = body
        self.unfinished = []

    def implicit_tags(self, tag):
        while True:
            open_tags = [node.tag for node in self.unfinished]
            if open_tags == [] and tag != "html":
                self.add_tag("html")
            elif open_tags == ["html"] and tag not in ["head", "body", "/html"]:
                if tag in self.HEAD_TAGS:
                    self.add_tag("head")
                else:
                    self.add_tag("body")
            elif (
                open_tags == ["html", "head"] and tag not in ["/head"] + self.HEAD_TAGS
            ):
                self.add_tag("/head")
            else:
                break

    def add_text(self, text):
        if text.isspace():
            return
        self.implicit_tags(None)
        parent = self.unfinished[-1]
        node = Text(text, parent)
        parent.children.append(node)

    def add_tag(self, tag):
        if tag.startswith("!"):
            return
        tag, attributes = self.get_attributes(tag)
        self.implicit_tags(tag)
        if tag.startswith("/"):
            if len(self.unfinished) == 1:
                return
            node = self.unfinished.pop()
            parent = self.unfinished[-1]
            parent.children.append(node)
        elif (tag in SELF_CLOSING_TAGS) or tag.endswith("/"):
            parent = self.unfinished[-1]
            node = Element(tag, attributes, parent)
            parent.children.append(node)
        else:
            parent = self.unfinished[-1] if self.unfinished else None
            node = Element(tag, attributes, parent)
            self.unfinished.append(node)

    def get_attributes(self, text):
        parts = text.split()
        tag = parts[0].lower()
        attributes = {}
        for attrpair in parts[1:]:
            if "=" in attrpair:
                key, value = attrpair.split("=", 1)
                if len(value) > 2 and value[0] in ["'", '"']:
                    value = value[1:-1]
                attributes[key.lower()] = value
            else:
                attributes[attrpair.lower()] = ""
        return tag, attributes

    def finish(self):
        if len(self.unfinished):
            self.add_tag("html")
        while len(self.unfinished) > 1:
            node = self.unfinished.pop()
            parent = self.unfinished[-1]
            parent.children.append(node)
        return self.unfinished.pop()

    def parse(self):
        text = ""
        in_tag = False
        comment = 0
        for c in self.body:
            if comment in [1, 2]:
                if c == "-":
                    comment += 1
                    continue
                else:
                    comment = 0
            if comment in [3, 4]:
                if c == "-":
                    comment += 1
                else:
                    comment = 3
            elif comment == 5:
                if c == ">":
                    comment = 0
                else:
                    comment = 3
            elif c == "<":
                in_tag = True
                if text:
                    self.add_text(text)
                text = ""
            elif c == "!" and in_tag and text == "":
                comment = 1
            elif c == ">":
                in_tag = False
                self.add_tag(text)
                text = ""
            else:
                text += c
        if not in_tag and text:
            self.add_text(text)
        return self.finish()


class Text:
    def __init__(self, text, parent) -> None:
        self.text = lex_entities(text)
        self.parent = parent
        self.children = []

    def __repr__(self) -> str:
        return repr(self.text)


class Element:
    def __init__(self, tag, attributes, parent) -> None:
        self.tag = tag
        self.attributes = attributes
        self.parent = parent
        self.children = []

    def __repr__(self) -> str:
        return f"<{self.tag}>"


if __name__ == "__main__":
    import sys

    # headers, body, _ = request(sys.argv[1])
    # nodes = HTMLParser(body).parse()
    # print_tree(nodes)

    Browser().load(sys.argv[1])
    tkinter.mainloop()
