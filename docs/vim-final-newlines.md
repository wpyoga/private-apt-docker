# Vim and the final newline

This preserves the editor tangent from the GIMP packaging conversation. No Vim
configuration or repository newline policy was changed.

## A final newline and an empty final line are different

A typical text file ends its last nonempty line with a newline. For example,
these escaped byte representations describe different contents:

```text
hello       no terminating newline
hello\n     one terminated line
hello\n\n   a terminated line followed by an empty terminated line
```

Some editors display a cursor position on an empty visual line after the final
newline in the second case. Vim normally represents that newline as the end of
the existing line rather than another editable empty buffer line. Consequently,
the different display does not by itself mean that a file lacks a final newline.
Adding an actual empty line changes the file's contents.

In Vim, G moves to the last buffer line. G0 moves to its first column. Go opens
a new line below it and enters Insert mode; that edits the buffer rather than
revealing a hidden line already in the file. :set list makes line endings and
other configured invisible characters visible, but it does not create an extra
buffer line. The exact markers depend on listchars.

## Can Vim behave like editors that expose the trailing position?

There is no ordinary built-in option that makes the file's final line terminator
appear as an additional editable empty buffer line with exactly that behavior.
Custom scripting or a plugin would be needed to emulate it. No particular plugin
was researched or recommended in this conversation.

The related setting is:

```vim
set virtualedit=onemore
```

It lets a Normal-mode cursor occupy one position just beyond the last character
of a line. It concerns horizontal movement; it does not create a virtual line
below the end of the buffer. If desired, put it in ~/.vimrc, understanding that
it does not implement the exact behavior requested.

The endofline and fixendofline options govern the final newline when reading and
writing, rather than adding a displayed buffer line. Changing them to imitate
another editor's display can change saved bytes without solving that display
difference. In ordinary text editing, Vim normally writes a terminating newline.
Binary mode and explicit option changes can affect that behavior.

References consulted during the explanation were Vim's
[virtualedit](https://vimhelp.org/options.txt.html#%27virtualedit%27),
[endofline](https://vimhelp.org/options.txt.html#%27endofline%27) and
[fixendofline](https://vimhelp.org/options.txt.html#%27fixendofline%27)
documentation. Local :help virtualedit, :help endofline and :help fixendofline
describe the installed Vim version. These links were not fetched again for the
documentation handoff.
