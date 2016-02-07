#!/usr/bin/python

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
                        default=1, help='Column offset to print the art at.')


    args = parser.parse_args()

    if not select.select([args.infile,],[],[],0.0)[0]:
        sys.stderr.write("Error: No input data.")
        return os.EX_DATAERR

    logger.warn("converting from: {}".format(args.infile.name))
    screen = TerminalScreen({'row': args.offset_row, 'col': args.offset_column})
    converter = AnsiArtConverter(args.infile, args.outfile, screen)
    converter.print_ansi()


class DelayedPrinter(object):
    """Delay the printing to make it match the original display."""

    def __init__(self, output=sys.stdout):
        """Set the requested output destination for the instance."""
        self._output = output

    def write(self, string):
        """Write a string to the screen."""
        self._output.write(string)

class TerminalScreen(object):

    logger = logging.getLogger(__name__)
    auto_newline = False
    max_row = 1
    default_color = {
        'flags': {}
    }
    current_color =  {
        'flags': {}
    }

    def __init__(self, origin = {'row': 1, 'col': 1}, dimensions = {'cols': 80}):
        """Set the screen parameters."""
        self.origin = origin
        self.cursor = copy.deepcopy(origin)
        self.saved_cursor = copy.deepcopy(origin)
        self.bounds = {}
        self.bounds['col'] = origin['col'] + dimensions['cols'] - 1

        if 'rows' in dimensions:
            self.bounds['row'] = origin['row'] + dimensions['rows'] - 1




    def current_color_debug(self):
        """Returns the current color settings as a readable string."""
        foreground = background = ''
        if 'foreground' in self.current_color:
            foreground = self.current_color['foreground']
        if 'background' in self.current_color:
            background = self.current_color['background']
        flags = ';'.join(self.current_color['flags'].keys())
        return "fg: {} bg: {} flags: {}".format(foreground, background, flags)


    def printable_character(self, char):
        """Handles printable characters."""

        if self.cursor['row'] > self.max_row:
            self.max_row = self.cursor['row']

        # Ignore a newline if it was already added because of width limit.
        if self.auto_newline and char != "\r":
            self.auto_newline = False
            if char == "\n":
                return ""

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
                self.cursor['row'] += 1
                self.cursor['col'] = copy.deepcopy(self.origin['col'])
                self.auto_newline = True
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
        self.cursor['col'] += cols[0]
        if self.cursor['col'] > self.bounds['col']:
            self.cursor['col'] = copy.deepcopy(self.bounds['col'])

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

    def get_csi_sequence_for_color(self, color):
        """Returns the CSI escape sequence for current color."""
        parameters = []
        flags = color['flags']
        for k in sorted(flags.keys()):
            if flags[k]:
                parameters.append(str(k))

        if 'foreground' in color:
            parameters.append(str(color['foreground']))


        if 'background' in color:
            parameters.append(str(color['background']))

        # If there are no color settings, reset to defaults.
        if not parameters:
            parameters.append('0')

        return "\033[" + (';').join(parameters) + 'm'

    def newline(self):
        """Turn off colors when printing a newline.

        This ensures the background color won't run to end of line."""
        default_color = self.get_csi_sequence_for_color(self.default_color)
        current_color = self.get_csi_sequence_for_color(self.current_color)

        newline = "\n"
        if self.origin['col'] > 1:
            newline += "\033[{}C".format(self.origin['col'] - 1)


        return default_color + newline + current_color

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
        self.screen = screen
        self.input = input

    def get_position_report(self):
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
                    # self.logger.warn("Reporting: " + report_chars)
                    sequence = self.screen.read_escape_sequence(report_chars, self.input)
                    if not sequence:
                        continue
                    break
                    # if not sequence:
                        # continue
                else:
                    self.logger.warn("Unexpected: {}")
            if sequence:
                command_char, parameters, chars = sequence
            position = { 'row': parameters[0] }
            position['col'] = parameters[1]

            return position



class AnsiArtConverter(object):

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

    def __init__(self, source_ansi, output, screen):
        """Sets the source and destination for the conversion."""
        self._source_ansi = source_ansi
        self._output = DelayedPrinter(output)
        self.position_reporter = PositionReporter(self)
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
            chars = self.screen.printable_character(chars)
            chars = chars.decode('cp437').encode('utf-8')
        self.logger.warn("row: {} col: {}".format(self.screen.cursor['row'],
                                                  self.screen.cursor['col']))
        col = self.screen.cursor['col']
        if self.screen.cursor['col'] >= 54:
            col = 54
        # return "\033[{};{}f".format(self.screen.cursor['row'], col) + chars
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
                message = "wrong pos ({}, {}), processed to {}, actual row: {} "
                + "col: {}"
                row = self.screen.cursor['row']
                col = self.screen.cursor['col']
                offset = self._source_ansi.tell()
                rrow = position['row']
                rcol = position['col']
                self.logger.warn(message.format(row, col, offset, rrow, rcol))
        self._output.write(self.close_screen())

    def read_csi_sequence(self, chars, stream):
        sequence = self.read_escape_sequence(chars, stream)
        if sequence:
            command_char, parameters, chars = sequence

            if command_char in self.command_blacklist:
                message = "ignored blacklisted command: {}"
                self.logger.warn(message.format(command_char))
                return ''

            getattr(self.screen, self.commands[command_char])(parameters)
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
        # Erase screen and move cursor to top left.
        output =  "\033[2J"
        origin_row = self.screen.origin['row']
        origin_col = self.screen.origin['col']
        output += "\033[{};{}f".format(origin_row, origin_col)
        # Hide cursor.
        output += "\033[?25l"
        return output

    def close_screen(self):
        """Return the screen to interactive state after printing."""
        # Place cursor at the end to not crop it.
        output = "\033[{};1H".format(self.screen.max_row + 1)
        # show cursor
        output += "\033[?25h"
        return output


    def convert_from_cp437(f):
        """Removes metadata and encodes the ANSI art to display with unicode."""
        output = io.BytesIO()
        data = f.read().split('\x1aSAUCE')[0]
        output.write(data.decode('cp437').encode('utf-8'))
        output.seek(0)
        return output
