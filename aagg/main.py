#!/usr/bin/env python2.7

import clingo, argparse, sys, json, time
import constants
from transformer import Transformer


def define_args(arg_parser):
    """Defines the arguments for this program, the AAgg"""
    arg_parser.description = 'Rewrite ASP logic programs according to Aggregate Equivalence'

    aggregate_form_help = 'Use the designated form for all created aggregates.  ' + \
                          '(1) b <= #count{ Y : f(Y) }  * * * * * * * * * * * * ' + \
                          '(2) not #count{ Y : f(Y) } < b  * * * * * * * * * * * ' + \
                          '(3) not b - 1 = #count{ Y : f(Y) }, ..., not 0 = #count{ Y : f(Y) } '
    arg_parser.add_argument('encoding', nargs='*', default=[], help='Gringo input files')
    arg_parser.add_argument('-o', '--output', type=str, default='', help='Specify a file name for the output')
    arg_parser.add_argument('--no-rewrite', action='store_true',
                            help='Disables all rewriting and simply parses the given program')
    arg_parser.add_argument('--confirm-rewrite', action='store_true',
                            help='Disables confirmation prompts for proposed rule rewritings')
    arg_parser.add_argument('--use-anonymous-variable', action='store_true',
                            help='Use anonymous variables in the aggregate')
    arg_parser.add_argument('-r', '--run-clingo', action='store_true',
                            help='Run clingo to ground and solve the program after performing any rewriting')
    arg_parser.add_argument('-d', '--debug', action='store_true', help='Run in debug mode')
    arg_parser.add_argument('--aggregate-form', type=int, default=constants.AGGR_FORM1, help=aggregate_form_help)


def open_files(encodings):
    """Used to open list of encodings given via commandline"""
    full_program = ''
    for encoding in encodings:
        with open(encoding, 'r') as enc:
            full_program += enc.read()
    return full_program


def name_outfile(encodings):
    """
        Given an array of encoding names, return an output file name
        This implementation renames the first encoding filename, appending
          '_rewritten.lp' to the end of the filename, rewriting '.lp' if any
    """
    ret = encodings[0]
    if len(ret) > 3:  # index size check
        # remove '.lp' if present
        if ret[(len(ret) - 3):] == '.lp':
            ret = ret[:(len(ret) - 3)]
    return ret + '_rewritten.lp'


def on_model(model):
    """
        Used in Solver callback to print models when they are found
        Does not work; pyclingo documentation seems to be wrong
    """
    print(str(model))


class Setting:
    """Holds arguments to be passed to the transformer"""

    def __init__(self, arguments):
        self.ENCODINGS = arguments.encoding
        self.NO_REWRITE = arguments.no_rewrite
        self.CONFIRM_REWRITE = arguments.confirm_rewrite
        self.USE_ANON = arguments.use_anonymous_variable
        self.RUN_CLINGO = arguments.run_clingo
        self.DEBUG = arguments.debug
        self.AGGR_FORM = arguments.aggregate_form
        if arguments.output != '':
            self.OUTFILE = arguments.output
        else:
            self.OUTFILE = name_outfile(arguments.encoding)


class AutomatedAggregator:
    """Main class. Controls and runs the rewritings"""

    def __init__(self, arguments):
        # Apply arguments to Setting class, to be passed to transformer
        self.setting = Setting(arguments)

        # Create clingo controller for building, grounding, and solving program
        self.control = clingo.Control(['--warn=none'])
        self.control.use_enumeration_assumption = False

    def run_clingo(self):
        """
            Grounds and solves the program while gathering
                timing and satisfiability statistics
            Returns ground and solve times, and if program was satisfiable
        """
        ground_start = time.time()
        self.control.ground([('base', [])])
        ground_time = time.time() - ground_start

        solve_start = time.time()
        ret = self.control.solve()  # on_model)            # TODO: How to get this to output models to console?
        solve_time = time.time() - solve_start

        return ground_time, solve_time, ret.satisfiable

    def log_statistics(self, parse_time, transform_time, ground_time, solve_time, satisfiable):
        """Logs time and satisfiability stats to controller"""
        self.control.statistics['summary']['times']['py-parse'] = parse_time
        self.control.statistics['summary']['times']['py-transform'] = transform_time
        self.control.statistics['summary']['times']['py-solve'] = solve_time
        self.control.statistics['summary']['times']['py-ground'] = ground_time
        self.control.statistics['summary']['satisfiable'] = satisfiable
        self.control.statistics['summary']['times']['py-gs'] = ground_time + solve_time
        self.control.statistics['summary']['times']['py-total'] = parse_time + transform_time + ground_time + solve_time

    def run(self):
        """Parse and transform the program"""
        print("\nRewriting " + ' '.join(self.setting.ENCODINGS) + "\n\n")
        with open(self.setting.OUTFILE, "w") as out_fd:
            with self.control.builder() as b:
                transformer = Transformer(b, self.setting, out_fd)

                parse_start = time.time()
                clingo.parse_program(
                    open_files(self.setting.ENCODINGS),
                    lambda stm: transformer.add_statement(stm))
                parse_time = time.time() - parse_start

                if self.setting.DEBUG:
                    transformer.print_input_statements()

                transform_start = time.time()
                transformer.explore_statements()
                transformer.transform_statements()
                transform_time = time.time() - transform_start

                if self.setting.DEBUG:
                    transformer.print_output_statements()

                transformer.write_statements()
                print("\n\nOutput written to " + self.setting.OUTFILE + "\n")

                if self.setting.RUN_CLINGO:
                    print("\nGrounding and solving...")
                    transformer.build_statements()
                    ground_time, solve_time, satisfiable = self.run_clingo()
                    self.log_statistics(parse_time, transform_time, ground_time, solve_time, satisfiable)
                    if self.setting.DEBUG:
                        print(json.dumps(self.control.statistics, sort_keys=True, indent=2, separators=(',', ': ')))
                    else:
                        print("SAT" if satisfiable else "UNSAT")


parser = argparse.ArgumentParser()
define_args(parser)
args = parser.parse_args()
if not args.encoding:  # close if no input encodings are given
    parser.print_help()
    sys.exit(0)

aagg = AutomatedAggregator(args)
aagg.run()
