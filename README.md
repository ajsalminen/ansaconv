ansaconv (ANSI art converter)
==========

Description
------------

ansaconv (ANSI art converter) converts ANSI art so that it displays properly
in a terminal emulator with a character set other than cp437.

It's still a work in progress that doesn't display everything properly and lacks
some of the planned features. The main benefit currently is that the art pieces
display correctly in a terminal wider than 80 characters.

Example uses
--------------

You could download a copy of the [Sixteen Colors ANSI and ASCII Artwork
Archive](http://sixteencolors.net/) from their
[artpack repository](https://github.com/sixteencolors/sixteencolors-archive) and
add something like this to your shell startup files:
   ansaconv  ~/sixteencolors/$(shuf -n 1 ~/sixteencolors/list.txt)

License
-------

MIT

See also
--------

* [artcat](https://github.com/tehmaze/artcat)
* [ansilove](https://github.com/ansilove/ansilove) converts ANSI art into PNG
