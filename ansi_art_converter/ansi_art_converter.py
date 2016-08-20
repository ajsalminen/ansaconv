#!/usr/bin/python
# -*- coding: utf-8 -*-
import re
import copy
import sys
import time
import logging
import io
import argparse
import os
import select
import tty
import curses

def main():
    logger = logging.getLogger(__name__)
    fh = logging.FileHandler('ansi_art_converter.log')
    logger.addHandler(fh)


    parser = argparse.ArgumentParser(description='Convert ANSI art for display.')
    parser.add_argument('infile', nargs='?', type=argparse.FileType('r'),
                        default=sys.stdin, help='the file that will be converted.')
    parser.add_argument('outfile', nargs='?', type=argparse.FileType('w'),
                        default=sys.stdout, help='optional file to write in.')
    parser.add_argument('-o', '--offset-column', type=int,
                        default=1, help='Column offset to print the art at.')
    parser.add_argument('-O', '--offset-row', type=int,
                        default=1, help='Row offset to print the art at.')
    parser.add_argument('-p', '--palette-offset', type=int,
                        default=64, help='Palette offset to use.')

    args = parser.parse_args()

    if not select.select([args.infile,],[],[],0.0)[0]:
        sys.stderr.write("Error: No input data.")
        return os.EX_DATAERR

    logger.warn("converting from: {}".format(args.infile.name))
    image_writer = TerminalCommands(args.palette_offset)
    screen = TerminalScreen(image_writer, {'row': args.offset_row, 'col': args.offset_column})
    converter = AnsiArtConverter(args.infile, args.outfile, screen, image_writer, args.palette_offset)
    converter.print_ansi()


class DelayedPrinter(object):
    """Delay the printing to make it match the original display."""

    _delay = 0

    def __init__(self, output=sys.stdout, delay=0):
        """Set the requested output destination for the instance."""
        self._output = output
        if delay:
            self._delay = delay

    def write(self, string):
        """Write a string to the screen."""
        time.sleep(self._delay)
        self._output.write(string)

class TerminalCommands(object):
    """Writes output as ANSI escape codes."""
    def __init__(self, palette_offset = 0):
        self.palette_offset = palette_offset

    def color(self, args):
        """Returns the CSI escape sequence for current color."""
        logger = logging.getLogger(__name__)
        converted_color = self.color_map(args)

        logger.warn("Converting colors {} to {}".format(",".join([str(a) for a in args]), ",".join([str(a) for a in converted_color])))
        return "\033[0;" + (';').join(converted_color) + 'm'

    def color_map(self, arg):
            color = []
            if 'background' in arg:
                color.append("48;5;" + str(arg['background'] - 40 + self.palette_offset))
            else:
                color.append("48;5;64")
            if 'foreground' in arg:
                foreground_index = arg['foreground'] - 30 + self.palette_offset
                if '1' in arg['flags']:
                    foreground_index += 8
                color.append("38;5;" + str(foreground_index))
            elif '1' in arg['flags']: # bright foreground
                color.append("38;5;79")
            else:
                color.append("38;5;71")
            return color

    def color_params(self, color):
        parameters = []
        flags = color['flags']
        for k in sorted(flags.keys()):
            if flags[k]:
                parameters.append(k)

        if 'foreground' in color:
            parameters.append(color['foreground'])


        if 'background' in color:
            parameters.append(color['background'])

        # If there are no color settings, reset to defaults.
        if not parameters:
            parameters.append('0')
        return parameters


    def shift_palette(self, args):
        """Shifts the palette colors according to the offset"""
        return [parameter + self.palette_offset if isinstance(parameter, int) and parameter >= 30 else parameter for parameter in args]

    def forward(self, args = [1]):
        if args[0] == 0:
            return ''
        return "\033[{}C".format(args[0])

    def up(self, args = [1]):
        if args[0] == 0:
            return ''
        return "\033[{}A".format(args[0])

    def hide_cursor(self, args = []):
        return "\033[?25l"

    def show_cursor(self, args = []):
        return "\033[?25h"

    def erase_screen(self, args = []):
        return "\033[2J"

    def erase_line(self, args = []):
        return "\033[2K"


    def cursor_position(self, row, column):
        return "\033[{};{}f".format(row, column)


    def interpret_color(self, color):
        components = []
        for i in range(1, 7, 2):
            components.append(int(int(color[i:i+2],16)/255.0*1000))
        return components

    def init_colors(self, colors):
        curses.setupterm()
        initc = curses.tigetstr("initc")
        for index, color in enumerate(colors):
            red, green, blue = self.interpret_color(color)
            command = curses.tparm(initc, self.palette_offset + index, red, green, blue)
            print command,






class TerminalScreen(object):
    """Represents the terminal screen and it's state."""

    logger = logging.getLogger(__name__)
    auto_newline = False
    max_row = 1
    default_color = {
        'flags': {},
        'background' : 40,
        'foreground' : 30
    }
    current_color =  {
        'flags': {}
    }

    def __init__(self, image_writer, origin = {'row': 1, 'col': 1}, dimensions = {'cols': 80}):
        """Set the screen parameters."""
        self.origin = origin
        self.cursor = copy.deepcopy(origin)
        self.saved_cursor = copy.deepcopy(origin)
        self.bounds = {}
        self.bounds['col'] = origin['col'] + dimensions['cols'] - 1
        if 'rows' in dimensions:
            self.bounds['row'] = origin['row'] + dimensions['rows'] - 1
        self.image_writer = image_writer


    def current_color_debug(self):
        """Returns the current color settings as a readable string."""
        foreground = background = ''
        if 'foreground' in self.current_color:
            foreground = self.current_color['foreground']
        if 'background' in self.current_color:
            background = self.current_color['background']
        flags = ';'.join(self.current_color['flags'].keys())
        return "fg: {} bg: {} flags: {}".format(foreground, background, flags)

    def clear_rows(self):
        output = ''
        num_rows = self.cursor['row'] - self.max_row
        output +=  self.erase_line()

        # If we need to erase more than one line.
        if num_rows > 1:
            for l in range(1, num_rows):
                output += self.image_writer.up()
                output +=  self.erase_line()
            output += self.image_writer.cursor_position(self.cursor['row'], self.cursor['col'])
        return output

    def printable_character(self, char):
        """Handles printable characters."""

        if self.cursor['row'] > self.max_row:
            self.max_row = self.cursor['row']
        if char == "\n":
            self.cursor['row'] += 1
            self.cursor['col'] = copy.deepcopy(self.origin['col'])
            return self.newline()
        elif char == '\r': #  or char == '\0':
            self.cursor['col'] = copy.deepcopy(self.origin['col'])
            # Don't count the CR
            return char
        else:
            self.cursor['col']+=1
            if self.cursor['col'] > self.bounds['col']:
                self.logger.warn('Automatically inserting a newline.')
                self.cursor['row'] += 1
                self.cursor['col'] = copy.deepcopy(self.origin['col'])
                return char + self.newline()
        return char

    def down(self, rows):
        """Changes the tracked cursor position one row down."""
        self.cursor['row'] += rows[0]

    def up(self, rows):
        """Changes the tracked cursor position one row up."""
        self.cursor['row'] -= rows[0]

    def forward(self, cols):
        """Changes the tracked cursor position one column forward."""
        new_col = self.cursor['col'] + cols[0]
        if new_col > self.bounds['col']:
            offset = self.bounds['col'] - self.cursor['col']
            self.cursor['col'] = copy.deepcopy(self.bounds['col'])
        else:
            offset = cols[0]
            self.cursor['col'] = new_col
        command = self.image_writer.forward([offset])
        self.logger.warn(command)
        return command


    def back(self, cols):
        """Changes the tracked cursor position one column back."""
        self.cursor['col'] -= cols[0]
        if self.cursor['col'] < self.origin['col']:
            self.cursor['col'] = copy.deepcopy(self.origin['col'])


    def position(self, pos):
        """Changes the tracked cursor position to requested."""

        # Omitted positions default to 1.
        if pos[0] == '':
            pos[0] = copy.deepcopy(self.origin['row'])

        if len(pos) == 2:
            if pos[1] == '':
                pos[1] = copy.deepcopy(self.origin['col'])
        else:
            pos.append(copy.deepcopy(self.origin['col']))

        self.cursor['row'] = self.origin['row'] + pos[0] - 1
        self.cursor['col'] = self.origin['col'] + pos[1] - 1

    # TODO replace with decrc/decsc for better compatibility with terminals?
    def save_cursor(self, arg = []):
        """Saves the tracked cursor position."""
        self.saved_cursor = copy.deepcopy(self.cursor)

    def restore_cursor(self, arg = []):
        """Restores the tracked cursor position."""
        self.cursor = copy.deepcopy(self.saved_cursor)

    def erase(self, arg):
        """The erase screen command has no effect on cursor position."""
        pass

    def erase_line(self, arg):
        """The erase line command has no effect on cursor position."""
        pass

    def color(self, arg):
        """Sets the current tracked color as requested."""
        current = self.current_color
        for parameter in arg:
            current = self.interpret_color(current, parameter)
        self.current_color = current
        self.logger.warn(self.current_color_debug())
        chars = self.image_writer.color(current)
        return chars


    def interpret_color(self, current, parameter):
        """Interprets the CSI sequence parameters for color setting."""
        self.logger.warn('colorparm: ' + str(parameter))
        if parameter >= 30 and parameter <= 37:
            current['foreground'] = parameter
        elif  parameter >= 40 and parameter <= 47:
            current['background'] = parameter
        elif parameter >=1 and parameter <= 9:
            current['flags'][str(parameter)] = True
        elif parameter == 0:
            current = {
                'flags': {}
            }
        elif parameter >= 21 and parameter <= 25:
            parameter = parameter - 20
            if parameter in current['flags']:
                current['flags'][str(parameter)] = False

                if parameter == 2:
                    if 1 in current['flags']:
                        current['flags']['1'] = False
                if parameter == 5:
                    if 6 in current['flags']:
                        current['flags']['6'] = False
        return current

    def erase_line(self):
        return self.default_color_wrap(self.image_writer.erase_line())

    def newline(self):
        newline = "\n"
        if self.origin['col'] > 1:
            newline += self.image_writer.forward().format(self.origin['col'] - 1)
        return self.default_color_wrap(newline)

    # TODO: this probably belongs to the output class.
    def default_color_wrap(self, chars):
        """Turn off colors when printing a newline.

        This ensures the background color won't run to end of line."""

        default_color = self.image_writer.color(self.default_color)
        current_color = self.image_writer.color(self.current_color)


        return default_color + chars + current_color

    def backspace(self):
        """Delete previous character and go back."""
        self.cursor['col'] -= 1

        if self.cursor['col'] < self.origin['col']:
            self.cursor['col'] = copy.deepcopy(self.bounds['col'])

            if self.cursor['row'] > self.bounds['row']:
                self.cursor['row'] -= 1

class PositionReporter:
    """Check that terminal reports same cursor position as our tracking."""


    logger = logging.getLogger(__name__)

    def __init__(self, screen, input = sys.stdin):
        """Initialise the injected attributes for PositionReporter"""
        self.screen = screen
        self.input = input

    def get_position_report(self):
        """Gets and parses the cursor position reported by the terminal."""
        # Ask for the position, do not print a newline.
        print "\033[6n",
        char = ''
        cursor = ''
        sequence = []
        while True:
            # Look for and read the position report.
            report_chars = self.input.read(1)
            if report_chars[0] == "\033":
                report_chars += self.input.read(1)
                if report_chars[1] != '[':
                    continue
                sequence = self.screen.read_escape_sequence(report_chars, self.input)
                if not sequence:
                    continue
                break
            else:
                self.logger.warn("Unexpected: {}")
        if sequence:
            command_char, parameters, chars = sequence
        position = { 'row': parameters[0] }
        position['col'] = parameters[1]

        return position


class AnsiArtConverter(object):
    """Interprets ANSI commands and transforms the output."""
    logger = logging.getLogger(__name__)
    commands = {
        'A': 'up',
        'B': 'down',
        'C': 'forward',
        'D': 'back',
        'H': 'position',
        'f': 'position',
        'J': 'erase',
        'K': 'erase_line',
        's': 'save_cursor',
        'u': 'restore_cursor',
        'm': 'color',
        'R': 'report_cursor_position'
    }

    vga_colors = [
        '#000000',
        '#aa0000',
        '#00aa00',
        '#aa5500',
        '#0000aa',
        '#aa00aa',
        '#00aaaa',
        '#aaaaaa',
        '#555555',
        '#ff5555',
        '#55ff55',
        '#ffff55',
        '#5555ff',
        '#ff55ff',
        '#55ffff',
        '#ffffff',
    ]


    command_blacklist = set(
        [
            # Setting wraparound mode does not work in rxvt and is the default.
            # SM and DECSET commands should not be present in ANSI art and
            # ANSI.SYS screen modes are not supported.
            'h',
            # In DOS resets screen modes and the real ANSI codes are not useful.
            'l'
        ]
    )

    # Currently these are passed to and handled in printable_character.
    # Most control characters don't affect cursor position so just pass them.
    printable_control_chars = set(
        [
            10, # LF (\n)
            13 # CR (\r)
        ]
    )

    def __init__(self, source_ansi, output, screen, image_writer, palette_offset = 0):
        """Sets the source and destination for the conversion."""
        self._source_ansi = source_ansi
        self._output = DelayedPrinter(output)
        self.position_reporter = PositionReporter(self)
        self.terminalcommands = image_writer
        self.screen = screen

    def process(self, chars, stream):
        """Processes characters that are part of the ANSI art."""
        if chars[0] == '\x1b':
            chars += stream.read(1)
            chars = self.process_escape_code(chars, stream)
        else:
            char_pos = ord(chars[0])
            if 0 <= char_pos <= 31 or char_pos == 127:
                # Nonprintable control characters.
                self.logger.warn("ASCII control code: {}".format(hex(char_pos)))
                if char_pos not in self.printable_control_chars:
                    # del, horizontal tab, vertical tab (others?) not handled.
                    if char_pos == 8:
                        self.screen.backspace()
                    return chars
            output = ''
            if self.screen.cursor['row'] > self.screen.max_row:
                output += self.screen.clear_rows()
            chars = self.screen.printable_character(chars)
            chars = output + chars.decode('cp437').encode('utf-8')
        self.logger.warn("row: {} col: {}".format(self.screen.cursor['row'],
                                                  self.screen.cursor['col']))
        col = self.screen.cursor['col']
        if self.screen.cursor['col'] >= 54:
            col = 54
        return chars

    def process_escape_code(self, chars, stream):
        """Processes all ANSI escape sequences."""
        if chars[1] == '[':
            return self.read_csi_sequence(chars, stream)
        else:
            self.logger.warn("Non CSI escape code: {}".format(hex(ord(val))))
            return chars

    def print_ansi(self):
        """Controls the printing of the ANSI art."""
        self._output.write(self.prepare_screen())

        tty.setcbreak(sys.stdin.fileno())
        while True:
            character = self._source_ansi.read(1)
            if not character:
                break
            # DOS EOF, after it comes SAUCE metadata.
            if character == '\x1a':
                break
            self._output.write(self.process(character, self._source_ansi))

            position = self.position_reporter.get_position_report()
            # this is bugged after processing newlines.
            if  position['col'] != self.screen.cursor['col']:
                message = ("wrong pos ({}, {}), processed to {}, actual row: {} "
                "col: {}")
                row = self.screen.cursor['row']
                col = self.screen.cursor['col']
                offset = self._source_ansi.tell()
                rrow = position['row']
                rcol = position['col']
                self.logger.warn(message.format(row, col, offset, rrow, rcol))
        self._output.write(self.close_screen())

    def read_csi_sequence(self, chars, stream):
        """Reads a CSI escape sequence and calls the appropriate command."""
        sequence = self.read_escape_sequence(chars, stream)
        if sequence:
            command_char, parameters, chars = sequence

            if command_char in self.command_blacklist:
                message = "ignored blacklisted command: {}"
                self.logger.warn(message.format(command_char))
                return ''

            return self.command(command_char, parameters, chars)
        return chars


    def command(self, command_char, parameters, chars):
        replaced_parameters = getattr(self.screen, self.commands[command_char])(parameters)

        if replaced_parameters:
            # Screen needs to provide the complete color setting.
            chars = replaced_parameters
        return chars

    def read_escape_sequence(self, chars, stream):
        """Reads a CSI escape sequence and calls the method that handles it."""
        sequence = ''
        while True:
            character = stream.read(1)
            chars += character
            # command character in CSI sequence is in this range.
            if 64 <= ord(character) <= 126:
                if character in self.commands:
                    if sequence == '':
                        sequence = '1'
                    self.logger.warn(self.commands[character] + " " + sequence)
                    parameters = self._get_csi_parameters(sequence)
                    return [character, parameters, chars]
                    self.logger.warn(self.screen.current_color_debug())
                elif character in self.command_blacklist:
                    return [character, [], []]
                else:
                    message = "Unhandled escape code: {}"
                    self.logger.warn(message.format(character))
                break
            else:
                sequence += character
        return None

    def _get_csi_parameters(self, sequence):
        """Gather the CSI escape sequence parameters in a list."""
        parameters = []
        for parameter in sequence.split(';'):
            # Other possibilities are a letter and the empty string.
            if parameter.isdigit():
                parameter = int(parameter)
            parameters.append(parameter)
        return parameters


    def prepare_screen(self):
        """Prepares the screen for printing ANSI art."""

        self.terminalcommands.init_colors(self.vga_colors)

        # Erase screen and move cursor to top left.
        output =  self.terminalcommands.erase_screen()
        origin_row = self.screen.origin['row']
        origin_col = self.screen.origin['col']
        output += self.terminalcommands.cursor_position(origin_row, origin_col)
        output += self.terminalcommands.hide_cursor()
        return output

    def close_screen(self):
        """Return the screen to interactive state after printing."""

        # Place cursor at the end to not crop it.
        output = self.terminalcommands.cursor_position(self.screen.max_row + 1, self.screen.cursor['col'])
        # show cursor
        output += self.terminalcommands.show_cursor()
        return output


    def convert_from_cp437(f):
        """Removes metadata and encodes the ANSI art to display with unicode."""
        output = io.BytesIO()
        data = f.read().split('\x1aSAUCE')[0]
        output.write(data.decode('cp437').encode('utf-8'))
        output.seek(0)
        return output
