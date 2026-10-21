import shlex

def sessions(text):
    """The step list of each session: words split as a shell would, sessions at `;` or a line break."""
    found = [[]]
    for line in text.splitlines():
        lexer = shlex.shlex(line, posix=True, punctuation_chars=";")
        lexer.whitespace_split = True
        lexer.commenters = ""
        for word in lexer:
            if word.strip(";"):
                found[-1].append(word)
            else:
                found.append([])
        found.append([])
    return [steps for steps in found if steps]
