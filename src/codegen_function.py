from __future__ import print_function
import argparse
import itertools
import os
import sys
import tempfile
import subprocess


class TermColors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


# TODO: Check that your compiler supports __float128
NUMPY_ARRAY_TYPES_TO_CPP = {
    # Dense types
    'dense_f32': ('float', 'f32', 'float32'),
    'dense_f64': ('double', 'f64', 'float64'),
    'dense_f128': ('__float128', 'f128', 'float128'),
    'dense_i8': ('std::int8_t', 'i8', 'int8'),
    'dense_i16': ('std::int16_t', 'i16', 'int16'),
    'dense_i32': ('std::int32_t', 'i32', 'int32'),
    'dense_i64': ('std::int64_t', 'i64', 'int64'),
    'dense_u8': ('std::uint8_t', 'u8', 'uint8'),
    'dense_u16': ('std::uint16_t', 'u16', 'uint16'),
    'dense_u32': ('std::uint32_t', 'u32', 'uint32'),
    'dense_u64': ('std::uint64_t', 'u64', 'uint64'),
    'dense_c64': ('std::complex<float>', 'c64', 'complex64'),
    'dense_c128': ('std::complex<double>', 'c128', 'complex128'),
    'dense_c256': ('std::complex<__float128>', 'c256', 'complex256'),

    # Sparse types
    'sparse_f32': ('float', 'f32', 'float32'),
    'sparse_f64': ('double', 'f64', 'float64'),
    'sparse_f128': ('__float128', 'f128', 'float128'),
    'sparse_i8': ('std::int8_t', 'i8', 'int8'),
    'sparse_i16': ('std::int16_t', 'i16', 'int16'),
    'sparse_i32': ('std::int32_t', 'i32', 'int32'),
    'sparse_i64': ('std::int64_t', 'i64', 'int64'),
    'sparse_u8': ('std::uint8_t', 'u8', 'uint8'),
    'sparse_u16': ('std::uint16_t', 'u16', 'uint16'),
    'sparse_u32': ('std::uint32_t', 'u32', 'uint32'),
    'sparse_u64': ('std::uint64_t', 'u64', 'uint64'),
    'sparse_c64': ('std::complex<float>', 'c64', 'complex64'),
    'sparse_c128': ('std::complex<double>', 'c128', 'complex128'),
    'sparse_c256': ('std::complex<__float128>', 'c256', 'complex256')}

NUMPY_ARRAY_TYPES = list(NUMPY_ARRAY_TYPES_TO_CPP.keys())
NUMPY_SCALAR_TYPES = list(set([v[2] for v in NUMPY_ARRAY_TYPES_TO_CPP.values()]))
MATCHES_TOKEN = "npe_matches"
ARG_TOKEN = "npe_arg"
DEFAULT_ARG_TOKEN = "npe_default_arg"
BEGIN_CODE_TOKEN = "npe_begin_code"
END_CODE_TOKEN = "npe_end_code"
FUNCTION_TOKEN = "npe_function"
DTYPE_TOKEN = "npe_dtype"
DOC_TOKEN = "npe_doc"
COMMENT_TOKEN = "//"

CPP_COMMAND = None  # Name of the command to run for the C preprocessor. Set at input.

LOG_DEBUG = 3
LOG_INFO = 1
LOG_INFO_VERBOSE = 2
LOG_ERROR = 0
verbosity_level = 1  # Integer representing the level of verbosity 0 = only log errors, 1 = normal, 2 = verbose


class ParseError(Exception):
    pass


class SemanticError(Exception):
    pass


def log(log_level, logstr, end='\n', file=sys.stdout):
    if log_level <= verbosity_level:
        print(logstr, end=end, file=file)


def tokenize_npe_line(stmt_token, line, line_number, max_iters=64, split_token="__NPE_SPLIT_NL__"):
    """
    Tokenize an NPE statement of the forn STMT(arg1, ..., argN)
    :param stmt_token: The name of the statement to parse.
    :param line: The line to tokenize.
    :param line_number: The line number in the file being parsed.
    :param max_iters: The number of iterations of the C preprocessor to parse everything.
                      This has the side effect of setting the max number of arguments.
    :param split_token: The split token for the C preprocessor to use. Don't change this unless you have a good reason.
    :return:
    """
    def run_cpp(input_str):
        tmpf = tempfile.NamedTemporaryFile(mode="w+", suffix=".cc")
        tmpf.write(input_str)
        tmpf.flush()
        cmd = CPP_COMMAND + " -w " + tmpf.name
        p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output, err = p.communicate()
        tmpf.close()
        return output.decode('utf-8'), err

    cpp_str = "#define %s(arg, ...) arg %s %s(__VA_ARGS__)" % (stmt_token, split_token, stmt_token)

    cpp_input_str = cpp_str + "\n" + line + "\n"

    exited_before_max_iters = False

    for i in range(max_iters):
        output, err = run_cpp(cpp_input_str)

        if err:
            raise ParseError("Invalid code at line %d:\nCPP Error message:\n%s" %
                             (line_number, err.decode("utf-8")))

        output = output.split('\n')

        parsed_string = ""
        for out_line in output:
            if str(out_line).strip().startswith("#"):
                continue
            else:
                parsed_string += str(out_line) + "\n"

        tokens = parsed_string.split(split_token)

        if tokens[-1].strip().startswith("%s()" % stmt_token) and tokens[-1].strip() != "%s()" % stmt_token:
            raise ParseError("Extra tokens after `%s` statement on line %d" % (stmt_token, line_number))
        elif tokens[-1].strip() == "%s()" % stmt_token:
            exited_before_max_iters = True
            tokens.pop()
            break

        cpp_input_str = cpp_str + "\n" + parsed_string

    if not exited_before_max_iters:
        raise ParseError("Reached token parser maximum recursion depth (%d) at line %d" % (max_iters, line_number))

    tokens = [s.strip() for s in tokens]

    return tokens


def validate_identifier_name(var_name):
    """
    Returns True if var_name is a valid C++ identifier, otherwise throws a ParseError
    :param var_name: The name of the identifier to check
    :return: True if var_name is a valid C++ identifier
    """
    # TODO: Validate identifier name
    pass


def is_numpy_type(typestr):
    """
    Return True if typestr refers to a NPE type corresponding to a Numpy/Eigen type
    :param typestr: The type string to check
    :return: True if typestr names a Numpy/Eigen type (e.g. dense_f64, sparse_i32)
    """
    global NUMPY_ARRAY_TYPES
    return typestr.lower() in NUMPY_ARRAY_TYPES


def is_sparse_type(type_name):
    """
    Return True if typestr refers to a NPE type corresponding to a Numpy/Eigen sparse type
    :param typestr: The type string to check
    :return: True if typestr names a Numpy/Eigen sparse type (e.g. sparse_f64, sparse_i32)
    """
    return is_numpy_type(type_name) and type_name.startswith("sparse_")


def is_dense_type(type_name):
    """
    Return True if typestr refers to a NPE type corresponding to a Numpy/Eigen dense type
    :param typestr: The type string to check
    :return: True if typestr names a Numpy/Eigen dense type (e.g. dense_f64, dense_i32)
    """
    return is_numpy_type(type_name) and type_name.startswith("dense_")


def consume_token(line, token, line_number, case_sensitive=True):
    """
    Consume the token, token, from the input line, ignoring leading whitespace. If the line
    does not start with token, then throw a ParseError
    :param line: The line from which to consume the token
    :param token: The token string to consume
    :param line_number: The line number in the file being read used for error reporting
    :param case_sensitive: Whether parsing is case sensitive or not
    :return: The line with the input token stripped
    """
    check_line = line if case_sensitive else line.lower()
    check_token = token if case_sensitive else token.lower()
    if not check_line.startswith(check_token):
        # TODO: Pretty error message
        raise ParseError("Missing '%s' at line %d" % (token, line_number))

    return line[len(token):]


def consume_eol(line, line_number):
    """
    Consumes whitespace at the end of a line
    :param line: The line from which to consume from
    :param line_number: The number of the line in the file being parsed, used for error reporting
    :return: An empty string on success
    """
    if len(line.strip()) != 0:
        # TODO: Pretty error message
        raise ParseError("Expected end-of-line after ')' token on line %d. Got '%s'" % (line_number, line.strip()))
    return line.strip()


def consume_call_statement(token, line, line_number, throw=True):
    """
    Consume the tokens <token> and <(> from the input line ignoring whitespace
    :param token: The name of the call token
    :param line: The line to check
    :param line_number: The number of the line in the file being read
    :param throw: Whether to throw an exception or simply return False if the line does not start with "token("
    :return: The line with the start tokens consumed or False if throw=False and the line did not start with "token("
    """
    try:
        line = consume_token(line.strip(), token, line_number)
        consume_token(line.strip(), '(', line_number)
    except ParseError:
        if throw:
            raise ParseError("Got invalid token at line %d. Expected `%s`" % (line_number, token))
        else:
            return False
    return line


class NpeFileReader(object):
    def __init__(self, name):
        self.file_name = name
        self.file = open(name, 'r')
        self.line_number = 0
        self.line = ""

    def close(self):
        return self.file.close()

    def readline(self):
        self.line_number += 1
        return self.file.readline()

    def peekline(self):
        pos = self.file.tell()
        line = self.readline()
        f.seek(pos)
        return line

    # to allow using in 'with' statements
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __next__(self):
        self.line = self.file.readline()
        if len(self.line) == 0:
            raise StopIteration()
        else:
            return self.line

    def __iter__(self):
        return self


class NpeArgument(object):
    def __init__(self, name, is_matches, name_or_type, line_number, default_value):
        self.name = name
        self.is_matches = is_matches
        self.name_or_type = name_or_type
        self.line_number = line_number
        self.is_sparse = False
        self.is_dense = False
        self.default_value = default_value
        self.group = None
        self.matches_name = ""

    @property
    def is_numpy_type(self):
        return self.is_sparse or self.is_dense

    def __repr__(self):
        return str(self.__dict__)


class NpeArgumentGroup(object):
    def __init__(self, types=[], arguments=[]):
        self.arguments = arguments
        self.types = types

    def __repr__(self):
        return str(self.__dict__)


class NpeFunction(object):
    def __init__(self, file_reader):
        self.name = ""                     # The name of the function we are binding
        self._input_type_groups = []       # Set of allowed types for each group of variables
        self._argument_name_to_group = {}  # Dictionary mapping input variable names to type groups
        self._argument_names = []          # List of input variable names in order
        self._arguments = {}       # Dictionary mapping variable names to types
        self._source_code = ""             # The source code of the binding
        self._preamble = ""                # The code that comes before npe_* statements
        self._docstr = ""                  # Function documentation

        self._parse(file_reader)
        self._validate()

    @property
    def arguments(self):
        """
        Iterate over the arguments and their meta data in the order they were passed in
        :return: An iterator over (argument_name, argument_metadata)
        """
        for arg_name in self._argument_names:
            arg_meta = self._arguments[arg_name]
            yield arg_meta

    @property
    def array_arguments(self):
        for arg_name in self._argument_names:
            arg_meta = self._arguments[arg_name]
            if arg_meta.is_numpy_type:
                yield arg_meta

    @property
    def num_args(self):
        return len(self._argument_names)

    @property
    def num_type_groups(self):
        return len(self._input_type_groups)

    @property
    def has_array_arguments(self):
        """
        Returns true if any of the arguments are numpy or scipy types
        :return: true if any of the input arguments are numpy or scipy types
        """
        has = False
        for arg in self.arguments:
            if is_numpy_type(arg.name_or_type[0]) or arg.is_matches:
                has = True
                break
        return has

    @property
    def argument_groups(self):
        return self._input_type_groups

    @property
    def docstring(self):
        return self._docstr

    def _parse_arg_statement(self, line, line_number, is_default):
        global NUMPY_ARRAY_TYPES, MATCHES_TOKEN, ARG_TOKEN

        def _parse_matches_statement(line, line_number):
            """
            Parse a matches(<type>) statement, returning the the type inside the parentheses
            :param line: The current line being parsed
            :param line_number: The number of the line in the file being parsed
            :return: The name of the type inside the matches statement as a string
            """
            global MATCHES_TOKEN

            line = consume_token(line.strip(), MATCHES_TOKEN, line_number=line_number, case_sensitive=False)
            line = consume_token(line.strip(), '(', line_number=line_number).strip()
            if not line.endswith(')'):
                # TODO: Pretty error message
                raise ParseError("Missing ')' for matches() token at line %d" % line_number)

            return line[:-1]

        stmt_token = DEFAULT_ARG_TOKEN if is_default else ARG_TOKEN

        tokens = tokenize_npe_line(stmt_token, line.strip(), line_number)

        var_name = tokens[0]
        var_types = tokens[1:]
        validate_identifier_name(var_name)
        var_value = var_types.pop() if is_default else None

        var_meta = NpeArgument(name=var_name,
                               is_matches=False,
                               name_or_type=var_types,
                               line_number=line_number,
                               default_value=var_value)

        group_id = -1

        if len(var_types) == 0:
            # TODO: Pretty error message
            raise ParseError('%s("%s") got no type arguments' % (stmt_token, var_name))
        elif len(var_types) > 1 or (len(var_types) == 1 and is_numpy_type(var_types[0])):
            # We're binding a scipy dense or sparse array. Check that the types are valid.
            for type_str in var_types:
                if not is_numpy_type(type_str):
                    # TODO: Pretty error message
                    raise ParseError("Got invalid type, `%s` in %s() at line %d. "
                                     "If multiple types are specified, "
                                     "they must be one of %s" % (type_str, stmt_token, line_number, NUMPY_ARRAY_TYPES))

            if var_name in self._argument_name_to_group:
                # There was a matches() done before the group was created, fix the data structure
                group_id = self._argument_name_to_group[var_name]
                assert len(self._input_type_groups[group_id].types) == 0
                self._input_type_groups[group_id].types = var_types
                self._input_type_groups[group_id].arguments.append(var_meta)
            else:
                # This is the first time we're seeing this group
                var_group = NpeArgumentGroup(types=var_types)
                self._input_type_groups.append(var_group)
                group_id = len(self._input_type_groups) - 1
                self._argument_name_to_group[var_name] = group_id
                self._input_type_groups[group_id].arguments = [var_meta]
        else:
            assert len(var_types) == 1

            if var_types[0].startswith(MATCHES_TOKEN):
                var_meta.is_matches = True

                # If the type was enforcing a match on another type, then handle that case
                matches_name = _parse_matches_statement(var_types[0], line_number=line_number)

                if matches_name in self._argument_name_to_group:
                    group_id = self._argument_name_to_group[matches_name]
                    self._argument_name_to_group[var_name] = group_id
                    self._input_type_groups[group_id].arguments.append(var_meta)
                else:
                    group_id = len(self._input_type_groups) - 1
                    self._argument_name_to_group[var_name] = group_id
                    self._argument_name_to_group[matches_name] = group_id
                    var_meta.matches_name = matches_name

                    var_group = NpeArgumentGroup(types=[], arguments=[var_meta])
                    self._input_type_groups.append(var_group)
            else:
                # TODO: Check that type requested is valid? - I'm not sure if we can really do this though.
                pass

        var_meta.group = self._input_type_groups[group_id] if group_id >= 0 else None
        self._argument_names.append(var_name)
        self._arguments[var_name] = var_meta

        return var_name, var_types, var_value

    def _parse_doc_statement(self, line, line_number, skip):
        global DOC_TOKEN
        if not skip:
            return

        tokens = tokenize_npe_line(DOC_TOKEN, line, line_number)

        if len(tokens) == 0:
            raise ParseError("Got %s statement at line %d but no documentation string." % (DOC_TOKEN, line_number))

        if len(tokens) > 1:
            raise ParseError("Got more than one documentation token at in %s statement at line %d. "
                             "Did you forget quotes around the docstring?" % (DOC_TOKEN, line_number))

        self._docstr = tokens[0]

        log(LOG_INFO_VERBOSE,
            TermColors.OKGREEN + "NumpyEigen Docstring - %s" % self._docstr)

    def _parse(self, file_reader):
        global ARG_TOKEN, BEGIN_CODE_TOKEN, END_CODE_TOKEN, FUNCTION_TOKEN

        def _parse_npe_function_statement(line, line_number):
            global FUNCTION_TOKEN

            tokens = tokenize_npe_line(FUNCTION_TOKEN, line, line_number)
            if len(tokens) > 1:
                raise ParseError(FUNCTION_TOKEN + " got extra tokens, %s, at line %d. "
                                                      "Expected only the name of the function." %
                                 (tokens[1, :], line_number))
            binding_name = tokens[0]
            validate_identifier_name(binding_name)

            return binding_name

        def _parse_begin_code_statement(line, line_number):
            global BEGIN_CODE_TOKEN
            line = consume_token(line.strip(), BEGIN_CODE_TOKEN, line_number=line_number, case_sensitive=False)
            line = consume_token(line.strip(), '(', line_number=line_number)
            line = consume_token(line.strip(), ')', line_number=line_number)
            consume_eol(line.strip(), line_number=line_number)

        def _parse_end_code_statement(line, line_number):
            global END_CODE_TOKEN
            line = consume_token(line.strip(), END_CODE_TOKEN, line_number=line_number, case_sensitive=False)
            line = consume_token(line.strip(), '(', line_number=line_number)
            line = consume_token(line.strip(), ')', line_number=line_number)
            consume_eol(line.strip(), line_number=line_number)

        binding_start_line_number = -1

        for line in file_reader:
            if len(line.strip()) == 0:
                continue
            elif consume_call_statement(ARG_TOKEN, line, line_number=file_reader.line_number + 1, throw=False):
                raise ParseError("Got `%s` statement before `%s` at line %d" %
                                 (ARG_TOKEN, FUNCTION_TOKEN, file_reader.line_number + 1))
            elif consume_call_statement(DEFAULT_ARG_TOKEN, line, line_number=file_reader.line_number + 1, throw=False):
                raise ParseError("Got `%s` statement before `%s` at line %d" %
                                 (DEFAULT_ARG_TOKEN, FUNCTION_TOKEN, file_reader.line_number + 1))
            elif consume_call_statement(BEGIN_CODE_TOKEN, line, line_number=file_reader.line_number + 1, throw=False):
                raise ParseError("Got `%s` statement before `%s` at line %d" %
                                 (BEGIN_CODE_TOKEN, FUNCTION_TOKEN, file_reader.line_number + 1))
            elif consume_call_statement(END_CODE_TOKEN, line, line_number=file_reader.line_number + 1, throw=False):
                raise ParseError("Got `%s` statement before `%s` at line %d" %
                                 (END_CODE_TOKEN, FUNCTION_TOKEN, file_reader.line_number + 1))
            elif consume_call_statement(DTYPE_TOKEN, line, line_number=file_reader.line_number + 1, throw=False):
                raise ParseError("Got `%s` statement before `%s` at line %d" %
                                 (DTYPE_TOKEN, FUNCTION_TOKEN, file_reader.line_number + 1))
            elif consume_call_statement(DOC_TOKEN, line, line_number=file_reader.line_number + 1, throw=False):
                raise ParseError("Got `%s` statement before `%s` at line %d" %
                                 (DOC_TOKEN, FUNCTION_TOKEN, file_reader.line_number + 1))
            elif consume_call_statement(FUNCTION_TOKEN, line, line_number=file_reader.line_number + 1, throw=False):
                self.name = _parse_npe_function_statement(line, line_number=file_reader.line_number + 1)
                binding_start_line_number = file_reader.line_number + 1
                break
            else:
                self._preamble += line
                # raise ParseError("Unexpected tokens at line %d: %s" % (line_number, lines[line_number]))

        if binding_start_line_number < 0:
            raise ParseError("Invalid binding file. Must begin with %s(<function_name>)." % FUNCTION_TOKEN)

        log(LOG_INFO_VERBOSE, TermColors.OKGREEN + "NumpyEigen Function: " + TermColors.ENDC + self.name)

        code_start_line_number = -1

        parsing_doc = False
        doc_lines = ""
        for line in file_reader:
            if consume_call_statement(ARG_TOKEN, line, line_number=file_reader.line_number + 1, throw=False):
                var_name, var_types, _ = self._parse_arg_statement(line, line_number=file_reader.line_number + 1,
                                                                   is_default=False)
                log(LOG_INFO_VERBOSE,
                    TermColors.OKGREEN + "NumpyEigen Arg: " + TermColors.ENDC + var_name + " - " + str(var_types))

                self._parse_doc_statement(doc_lines, line_number=file_reader.line_number + 1, skip=parsing_doc)
                parsing_doc = False
            elif consume_call_statement(DEFAULT_ARG_TOKEN, line, line_number=file_reader.line_number + 1, throw=False):
                var_name, var_types, var_value = \
                    self._parse_arg_statement(line, line_number=file_reader.line_number + 1, is_default=True)
                log(LOG_INFO_VERBOSE,
                    TermColors.OKGREEN + "NumpyEigen Default Arg: " + TermColors.ENDC + var_name + " - " +
                    str(var_types) + " - " + str(var_value))

                # If we were parsing a multiline npe_doc, we've now reached the end so parse the whole statement
                self._parse_doc_statement(doc_lines, line_number=file_reader.line_number + 1, skip=parsing_doc)
                parsing_doc = False

            elif consume_call_statement(DOC_TOKEN, line, line_number=file_reader.line_number + 1, throw=False):
                if self._docstr != "":
                    raise ParseError(
                        "Multiple `%s` statements for one function at line %d." % (DOC_TOKEN, file_reader.line_number + 1))

                doc_lines += line
                parsing_doc = True

            elif consume_call_statement(BEGIN_CODE_TOKEN, line, line_number=file_reader.line_number + 1, throw=False):
                _parse_begin_code_statement(line, line_number=file_reader.line_number + 1)
                code_start_line_number = file_reader.line_number + 1

                # If we were parsing a multiline npe_doc, we've now reached the end so parse the whole statement
                self._parse_doc_statement(doc_lines, line_number=file_reader.line_number + 1, skip=parsing_doc)
                break

            elif parsing_doc:
                # If we're parsing a multiline doc string, accumulate the line
                doc_lines += line
                continue

            elif len(line.strip()) == 0:
                # Ignore newlines and whitespace
                continue

            elif line.strip().lower().startswith(COMMENT_TOKEN):
                # Ignore commented lines
                continue

            else:
                raise ParseError("Unexpected tokens at line %d: %s" % (file_reader.line_number + 1, line))

        if code_start_line_number < 0:
            raise ParseError("Invalid binding file. Must does not contain a %s() statement." % BEGIN_CODE_TOKEN)

        reached_end_token = False
        for line in file_reader:
            if consume_call_statement(END_CODE_TOKEN, line, line_number=file_reader.line_number + 1, throw=False):
                _parse_end_code_statement(line, line_number=file_reader.line_number + 1)
                reached_end_token = True
            elif not reached_end_token:
                self._source_code += line
            elif reached_end_token and len(line.strip()) != 0:
                raise ParseError("Expected end of file after %s(). Line %d: %s" %
                                 (END_CODE_TOKEN, file_reader.line_number + 1, line))

        if not reached_end_token:
            raise ParseError("Unexpected EOF. Binding file must end with a %s() statement." % END_CODE_TOKEN)

    def _validate(self):
        for arg in self.arguments:
            is_sparse = is_sparse_type(arg.name_or_type[0])
            is_dense = is_dense_type(arg.name_or_type[0])

            for type_name in arg.name_or_type:
                if is_sparse_type(type_name) != is_sparse or is_dense_type(type_name) != is_dense:
                    raise SemanticError("Input Variable %s (line %d) has a mix of sparse and dense types."
                                        % (arg.name, arg.line_number))
            if arg.name in self._argument_name_to_group:
                arg.group = self._argument_name_to_group[arg.name]

            arg.is_sparse = is_sparse
            arg.is_dense = is_dense

        for arg in self.arguments:
            if arg.is_matches:
                group_idx = self._argument_name_to_group[arg.name]
                matches_name = arg.name_or_type[0]
                if len(self._input_type_groups[group_idx].types) == 0:
                    raise SemanticError("Input Variable %s (line %d) was declared with type %s but was "
                                        "unmatched with a numpy type." %
                                        (arg.name, arg.line_number, matches_name))
                arg.is_sparse = is_sparse_type(self._input_type_groups[group_idx].types[0])
                arg.is_dense = is_dense_type(self._input_type_groups[group_idx].types[0])


class NpeAST(object):
    def __init__(self, file_reader):
        self._file_name = file_reader.file_name
        self._preamble = [""]
        self.children = []

    def _parse(self, file_reader: NpeFileReader):

        while True:
            line = file_reader.peekline()
            if len(line) == 0:
                break

            if len(line.strip()) == 0:
                continue
            elif consume_call_statement(ARG_TOKEN, line, line_number=file_reader.line_number + 1, throw=False):
                raise ParseError("Got unexpected `%s`  at line %d" %
                                 (ARG_TOKEN, file_reader.line_number + 1))
            elif consume_call_statement(DEFAULT_ARG_TOKEN, line, line_number=file_reader.line_number + 1, throw=False):
                raise ParseError("Got unexpected `%s`  at line %d" %
                                 (DEFAULT_ARG_TOKEN, file_reader.line_number + 1))
            elif consume_call_statement(BEGIN_CODE_TOKEN, line, line_number=file_reader.line_number + 1, throw=False):
                raise ParseError("Got unexpected `%s`  at line %d" %
                                 (BEGIN_CODE_TOKEN, file_reader.line_number + 1))
            elif consume_call_statement(END_CODE_TOKEN, line, line_number=file_reader.line_number + 1, throw=False):
                raise ParseError("Got unexpected `%s`  at line %d" %
                                 (END_CODE_TOKEN, file_reader.line_number + 1))
            elif consume_call_statement(DTYPE_TOKEN, line, line_number=file_reader.line_number + 1, throw=False):
                raise ParseError("Got unexpected `%s`  at line %d" %
                                 (DTYPE_TOKEN, file_reader.line_number + 1))
            elif consume_call_statement(DOC_TOKEN, line, line_number=file_reader.line_number + 1, throw=False):
                raise ParseError("Got unexpected `%s`  at line %d" %
                                 (DOC_TOKEN, file_reader.line_number + 1))
            elif consume_call_statement(FUNCTION_TOKEN, line, line_number=file_reader.line_number + 1, throw=False):
                self.children = NpeFunction(file_reader)
            else:
                self._preamble[-1] += file_reader.readline()


def codegen_ast(fun, out_file):
    PRIVATE_ID_PREFIX = "_NPE_PY_BINDING_"
    PRIVATE_NAMESPACE = "npe::detail"
    STORAGE_ORDER_ENUM = "StorageOrder"
    ALIGNED_ENUM = "Alignment"
    TYPE_ID_ENUM = "TypeId"
    TYPE_CHAR_ENUM = "NumpyTypeChar"
    STORAGE_ORDER_SUFFIXES = ['_cm', '_rm', '_x']
    STORAGE_ORDER_SUFFIX_CM = STORAGE_ORDER_SUFFIXES[0]
    STORAGE_ORDER_SUFFIX_RM = STORAGE_ORDER_SUFFIXES[1]
    STORAGE_ORDER_SUFFIX_XM = STORAGE_ORDER_SUFFIXES[2]
    STORAGE_ORDER_CM = "ColMajor"
    STORAGE_ORDER_RM = "RowMajor"
    STORAGE_ORDER_XM = "NoOrder"
    MAP_TYPE_PREFIX = "npe_Map_"
    MATRIX_TYPE_PREFIX = "npe_Matrix_"
    SCALAR_TYPE_PREFIX = "npe_Scalar_"

    def type_name_var(var_name):
        return PRIVATE_ID_PREFIX + var_name + "_type_s"

    def storage_order_var(var_name):
        return PRIVATE_ID_PREFIX + var_name + "_so"

    def type_id_var(var_name):
        return PRIVATE_ID_PREFIX + var_name + "_t_id"

    def storage_order_for_suffix(suffix):
        if suffix == STORAGE_ORDER_SUFFIX_CM:
            return PRIVATE_NAMESPACE + "::" + STORAGE_ORDER_ENUM + "::" + STORAGE_ORDER_CM
        elif suffix == STORAGE_ORDER_SUFFIX_RM:
            return PRIVATE_NAMESPACE + "::" + STORAGE_ORDER_ENUM + "::" + STORAGE_ORDER_RM
        elif suffix == STORAGE_ORDER_SUFFIX_XM:
            return PRIVATE_NAMESPACE + "::" + STORAGE_ORDER_ENUM + "::" + STORAGE_ORDER_XM
        else:
            assert False, "major wtf"

    def aligned_enum_for_suffix(suffix):
        if suffix == STORAGE_ORDER_SUFFIX_CM or suffix == STORAGE_ORDER_SUFFIX_RM:
            return PRIVATE_NAMESPACE + "::" + ALIGNED_ENUM + "::" + "Aligned"
        elif suffix == STORAGE_ORDER_SUFFIX_XM:
            return PRIVATE_NAMESPACE + "::" + ALIGNED_ENUM + "::" + "Unaligned"
        else:
            assert False, "major wtf"

    def type_char_for_numpy_type(np_type):
        return PRIVATE_NAMESPACE + "::" + TYPE_CHAR_ENUM + "::char_" + NUMPY_ARRAY_TYPES_TO_CPP[np_type][1]

    def write_flags_getter(var_name):
        storage_order_var_name = storage_order_var(var_name)
        row_major = PRIVATE_NAMESPACE + "::RowMajor"
        col_major = PRIVATE_NAMESPACE + "::ColMajor"
        no_order = PRIVATE_NAMESPACE + "::NoOrder"
        out_str = "const " + PRIVATE_NAMESPACE + "::" + STORAGE_ORDER_ENUM + " " + storage_order_var_name + " = "
        out_str += "(" + var_name + ".flags() & NPY_ARRAY_F_CONTIGUOUS) ? " + col_major + " : "
        out_str += "(" + var_name + ".flags() & NPY_ARRAY_C_CONTIGUOUS ? " + row_major + " : " + no_order + ");\n"
        out_file.write(out_str)

    def write_type_id_getter(var_name):
        out_str = "const int " + type_id_var(var_name) + " = "
        type_name = type_name_var(var_name)
        storate_order_name = storage_order_var(var_name)
        is_sparse = PRIVATE_NAMESPACE + "::is_sparse<decltype(" + var_name + ")>::value"
        out_str += PRIVATE_NAMESPACE + "::get_type_id(" + is_sparse + ", " + type_name + ", " + storate_order_name + ");\n"
        out_file.write(out_str)

    def write_declaration():
        # ast = NpeAST(None)
        #
        # for child in ast.children:
        #     if type(child) == NpeFunction:
        out_file.write(fun._preamble + "\n")

        write_code_function_definition()

        # TODO: Use the function name properly
        func_name = "pybind_output_fun_" + os.path.basename(input_file_name).replace(".", "_")
        out_file.write("void %s(pybind11::module& m) {\n" % func_name)
        out_file.write('m.def(')
        out_file.write('"%s"' % fun.name)
        out_file.write(", [](")

        # Write the argument list
        i = 0
        for arg in fun.arguments:
            if arg.is_sparse:
                out_file.write("npe::sparse_array ")
                out_file.write(arg.name)
            elif arg.is_dense:
                out_file.write("pybind11::array ")
                out_file.write(arg.name)
            else:
                assert len(arg.name_or_type) == 1
                var_type = arg.name_or_type[0]
                out_file.write(var_type + " ")
                out_file.write(arg.name)
            next_token = ", " if i < fun.num_args - 1 else ") {\n"
            out_file.write(next_token)
            i += 1

        # Declare variables used to determine the type at runtime
        for arg in fun.array_arguments:
            out_file.write("const char %s = %s.dtype().type();\n" % (type_name_var(arg.name), arg.name))
            out_file.write("ssize_t %s_shape_0 = 0;\n" % arg.name)
            out_file.write("ssize_t %s_shape_1 = 0;\n" % arg.name)
            out_file.write("if (%s.ndim() == 1) {\n" % arg.name)
            out_file.write("%s_shape_0 = %s.shape()[0];\n" % (arg.name, arg.name))
            out_file.write("%s_shape_1 = %s.shape()[0] == 0 ? 0 : 1;\n" % (arg.name, arg.name))
            out_file.write("} else if (%s.ndim() == 2) {\n" % arg.name)
            out_file.write("%s_shape_0 = %s.shape()[0];\n" % (arg.name, arg.name))
            out_file.write("%s_shape_1 = %s.shape()[1];\n" % (arg.name, arg.name))
            out_file.write("} else if (%s.ndim() > 2) {\n" % arg.name)
            out_file.write("  throw std::invalid_argument(\"Argument " + arg.name +
                           " has invalid number of dimensions. Must be 1 or 2.\");\n")
            out_file.write("}\n")

            write_flags_getter(arg.name)
            write_type_id_getter(arg.name)

        # Ensure the types in each group match
        for group_id in range(fun.num_type_groups):
            group_var_names = [vm.name for vm in fun.argument_groups[group_id].arguments]
            group_types = fun.argument_groups[group_id].types
            pretty_group_types = [NUMPY_ARRAY_TYPES_TO_CPP[gt][2] for gt in group_types]

            out_str = "if ("
            for i in range(len(group_types)):
                type_name = group_types[i]
                out_str += type_name_var(group_var_names[0]) + " != " + type_char_for_numpy_type(type_name)
                next_token = " && " if i < len(group_types) - 1 else ") {\n"
                out_str += next_token
            out_str += 'throw std::invalid_argument("Invalid type (%s) for argument \'%s\'. ' \
                       'Expected one of %s.");\n' % (
                       pretty_group_types[0], group_var_names[0], pretty_group_types)
            out_str += "}\n"
            out_file.write(out_str)

            assert len(group_var_names) >= 1
            if len(group_var_names) == 1:
                continue

            for i in range(1, len(group_var_names)):
                out_str = "if ("
                out_str += type_id_var(group_var_names[0]) + " != " + type_id_var(group_var_names[i]) + ") {\n"
                out_str += 'std::string err_msg = std::string("Invalid type (") + %s::type_to_str(%s) + ' \
                           'std::string(") for argument \'%s\'. Expected it to match argument \'%s\' ' \
                           'which is of type ") + %s::type_to_str(%s) + std::string(".");\n' \
                           % (PRIVATE_NAMESPACE, type_name_var(group_var_names[i]), group_var_names[i],
                              group_var_names[0], PRIVATE_NAMESPACE, type_name_var(group_var_names[0]))
                out_str += 'throw std::invalid_argument(err_msg);\n'

                out_str += "}\n"

            out_file.write(out_str)

    def write_code_block(combo):
        out_file.write("{\n")
        for group_id in range(len(combo)):
            type_prefix = combo[group_id][0]
            type_suffix = combo[group_id][1]
            for arg in fun.argument_groups[group_id].arguments:
                cpp_type = NUMPY_ARRAY_TYPES_TO_CPP[type_prefix][0]
                storage_order_enum = storage_order_for_suffix(type_suffix)
                aligned_enum = aligned_enum_for_suffix(type_suffix)

                out_file.write("typedef " + cpp_type + " Scalar_" + arg.name + ";\n")
                if is_sparse_type(combo[group_id][0]):
                    eigen_type = "Eigen::SparseMatrix<" + cpp_type + ", " + \
                                 storage_order_enum + ", int>"
                    out_file.write("typedef " + eigen_type + " Matrix_%s" % arg.name + ";\n")
                    out_file.write("#if EIGEN_WORLD_VERSION == 3 && EIGEN_MAJOR_VERSION <= 2\n")
                    out_file.write("typedef Eigen::MappedSparseMatrix<" + cpp_type + ", " +
                                   storage_order_enum + ", int> Map_" + arg.name + ";\n")
                    out_file.write("#elif (EIGEN_WORLD_VERSION == 3 && "
                                   "EIGEN_MAJOR_VERSION > 2) || (EIGEN_WORLD_VERSION > 3)\n")
                    out_file.write("typedef Eigen::Map<Matrix_" + arg.name + "> Map_" + arg.name + ";\n")
                    out_file.write("#endif\n")

                else:
                    eigen_type = "Eigen::Matrix<" + cpp_type + ", " + "Eigen::Dynamic, " + "Eigen::Dynamic, " + \
                                 storage_order_enum + ">"
                    out_file.write("typedef " + eigen_type + " Matrix_%s" % arg.name + ";\n")
                    out_file.write("typedef Eigen::Map<" + eigen_type + ", " +
                                   aligned_enum + "> Map_" + arg.name + ";\n")

        call_str = "return callit"
        template_str = "<"
        for arg in fun.arguments:
            if arg.is_numpy_type:
                template_str += "Map_" + arg.name + ", Matrix_" + arg.name + ", Scalar_" + arg.name + ","
        template_str = template_str[:-1] + ">("

        call_str = call_str + template_str if fun.has_array_arguments else call_str + "("

        for arg in fun.arguments:
            if arg.is_numpy_type:
                if not arg.is_sparse:
                    call_str += "Map_" + arg.name + "((Scalar_" + arg.name + "*) " + arg.name + ".data(), " + \
                                arg.name + "_shape_0, " + arg.name + "_shape_1),"
                else:
                    call_str += arg.name + ".as_eigen<Matrix_" + arg.name + ">(),"
            else:
                call_str += arg.name + ","

        call_str = call_str[:-1] + ");\n"
        out_file.write(call_str)
        # out_file.write(binding_source_code + "\n")
        out_file.write("}\n")

    def write_code_function_definition():
        template_str = "template <"
        for arg in fun.arguments:
            if arg.is_numpy_type:
                template_str += "typename " + MAP_TYPE_PREFIX + arg.name + ","
                template_str += "typename " + MATRIX_TYPE_PREFIX + arg.name + ","
                template_str += "typename " + SCALAR_TYPE_PREFIX + arg.name + ","
        template_str = template_str[:-1] + ">\n"
        if fun.has_array_arguments:
            out_file.write(template_str)
        out_file.write("static auto callit(")

        argument_str = ""
        for arg in fun.arguments:
            if arg.is_numpy_type:
                argument_str += "%s%s %s," % (MAP_TYPE_PREFIX, arg.name, arg.name)
            else:
                argument_str += arg.name_or_type[0] + " " + arg.name + ","
        argument_str = argument_str[:-1] + ") {\n"
        out_file.write(argument_str)
        out_file.write(fun._source_code)
        out_file.write("}\n")

    def write_body():
        expanded_type_groups = [itertools.product(group.types, STORAGE_ORDER_SUFFIXES) for group in fun.argument_groups]
        group_combos = itertools.product(*expanded_type_groups)

        branch_count = 0

        if fun.has_array_arguments:
            for combo in group_combos:
                if_or_elseif = "if " if branch_count == 0 else " else if "
                out_str = if_or_elseif + "("

                skip = False
                for group_id in range(len(combo)):
                    # Sparse types only have column (csc) and row (csr) matrix types,
                    #  so don't output a branch for unaligned
                    if is_sparse_type(combo[group_id][0]) and combo[group_id][1] == STORAGE_ORDER_SUFFIX_XM:
                        skip = True
                        break
                    repr_var = fun.argument_groups[group_id].arguments[0]
                    typename = combo[group_id][0] + combo[group_id][1]
                    out_str += type_id_var(
                        repr_var.name) + " == " + PRIVATE_NAMESPACE + "::" + TYPE_ID_ENUM + "::" + typename
                    next_token = " && " if group_id < len(combo) - 1 else ")"
                    out_str += next_token

                if skip:
                    continue

                out_str += " {\n"
                out_file.write(out_str)
                write_code_block(combo)
                out_file.write("}")
                branch_count += 1
            out_file.write(" else {\n")
            out_file.write('throw std::invalid_argument("This should never happen but clearly it did. '
                           'File a github issue at https://github.com/fwilliams/numpyeigen");\n')
            out_file.write("}\n")
        else:
            group_combos = list(group_combos)
            assert len(group_combos) == 1, "This should never happen but clearly it did. " \
                                           "File a github issue at https://github.com/fwilliams/numpyeigen"
            for _ in group_combos:
                out_file.write("{\n")
                out_file.write(fun._source_code + "\n")
                out_file.write("}\n")
        out_file.write("\n")
        out_file.write("}")

    def write_end():
        if len(fun.docstring) > 0:
            out_file.write(", " + fun.docstring)

        arg_list = ""
        for arg in fun.arguments:
            arg_list += ", pybind11::arg(\"" + arg.name + "\")"
            arg_list += "=" + arg.default_value if arg.default_value else ""

        out_file.write(arg_list)
        out_file.write(");\n")
        out_file.write("}\n")
        out_file.write("\n")

    write_declaration()
    write_body()
    write_end()


if __name__ == "__main__":

    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("file", type=str)
    arg_parser.add_argument("cpp_cmd", type=str)
    arg_parser.add_argument("-o", "--output", type=str, default="a.out")
    arg_parser.add_argument("-v", "--verbosity-level", type=int, default=LOG_INFO,
                            help="How verbose is the output. < 0 = silent, "
                                 "0 = only errors, 1 = normal, 2 = verbose, > 3 = debug")

    args = arg_parser.parse_args()

    CPP_COMMAND = args.cpp_cmd
    verbosity_level = args.verbosity_level
    input_file_name = args.file

    with open(args.file, 'r') as f:
        line_list = f.readlines()

    try:
        with NpeFileReader(args.file) as infile:
            f = NpeFunction(infile)

        with open(args.output, 'w+') as outfile:
            FOR_REAL_DEFINE = "__NPE_FOR_REAL__"
            outfile.write("#define " + FOR_REAL_DEFINE + "\n")
            outfile.write("#include <npe.h>\n")
            codegen_ast(f, outfile)
    except SemanticError as e:
        # TODO: Pretty printer
        log(LOG_ERROR, TermColors.FAIL + TermColors.BOLD + "NumpyEigen Semantic Error: " +
              TermColors.ENDC + TermColors.ENDC + str(e), file=sys.stderr)
        sys.exit(1)
    except ParseError as e:
        # TODO: Pretty printer
        log(LOG_ERROR, TermColors.FAIL + TermColors.BOLD + "NumpyEigen Syntax Error: " +
              TermColors.ENDC + TermColors.ENDC + str(e), file=sys.stderr)
        sys.exit(1)
