from numbers import Number

from jaqal import Interface, TreeRewriteVisitor, TreeManipulators

from qscout.core import (
    ScheduledCircuit, Register, NamedQubit, GateDefinition,
    Parameter
)


def parse_jaqal_file(filename, override_dict=None):
    """Parse a file written in Jaqal into core types.

    filename -- The name of the Jaqal file.

    override_dict -- An optional dictionary of string: number mappings that overrides let statements in the Jaqal code.
    Note: all keys in this dictionary must exist as let statements or an error will be raised.
    """
    with open(filename) as fd:
        return parse_jaqal_string(fd.read(), override_dict=override_dict)


def parse_jaqal_string(jaqal, override_dict=None):
    """Parse a string written in Jaqal into core types.

    jaqal -- The Jaqal code as a string.

    override_dict -- An optional dictionary of string: number mappings that overrides let statements in the Jaqal code.
    Note: all keys in this dictionary must exist as let statements or an error will be raised.
    """

    # The interface will automatically expand macros and scrape let, map, and register metadata.
    iface = Interface(jaqal, allow_no_usepulses=True)
    # Do some minimal processing to fill in all let and map values. The interface does not automatically do this
    # as they may rely on values from override_dict.
    let_dict = iface.make_let_dict(override_dict)
    tree = iface.resolve_let(let_dict=let_dict)
    tree = iface.resolve_map(tree)
    visitor = CoreTypesVisitor(iface.make_register_dict(let_dict))
    circuit = visitor.visit(tree)
    # Note: we also have metadata about register sizes and imported files that we could output here as well.
    return circuit


class CoreTypesVisitor(TreeRewriteVisitor, TreeManipulators):
    """Define a visitor that will rewrite a Jaqal parse tree into objects from the core library."""

    def __init__(self, register_dict):
        super().__init__()
        self.registers = {name: Register(name, size) for name, size in register_dict.items()}
        self.gate_definitions = {}

    ##
    # Visitor Methods
    #

    def visit_program(self, header_statements, body_statements):
        circuit = ScheduledCircuit()
        for stmt in body_statements:
            circuit.gates.append(stmt)
        return circuit

    def visit_gate_statement(self, gate_name, gate_args):
        gate_name = str(self.extract_qualified_identifier(gate_name))
        gate_args = [self.convert_gate_arg(arg) for arg in gate_args]
        gate_def = self.get_gate_definition(gate_name, gate_args)
        gate = gate_def(*gate_args)
        return gate

    def visit_array_element_qual(self, identifier, index):
        index = int(index)
        reg = self.registers[str(identifier)][index]
        return reg

    ##
    # Helper Methods
    #

    def convert_gate_arg(self, arg):
        """Take a gate argument that may still be a parse tree and return
        a type that can be passed to the GateStatement constructor."""

        if self.is_signed_number(arg):
            return float(arg)
        elif isinstance(arg, NamedQubit):
            return arg
        else:
            raise TypeError(f"Unrecognized gate argument {arg}")

    def get_gate_definition(self, gate_name, gate_args):
        """Look up or create a gate definition for a gate with the
        given name and arguments."""
        if gate_name in self.gate_definitions:
            return self.gate_definitions[gate_name]
        else:
            params = [self.make_parameter_from_argument(index, arg)
                      for index, arg in enumerate(gate_args)]
            gate_def = GateDefinition(gate_name, params)
            self.gate_definitions[gate_name] = gate_def
            return gate_def

    @staticmethod
    def make_parameter_from_argument(index, arg):
        """Create a Parameter object with a default name and a type appropriate
        to the given argument."""
        name = f"{index}"
        if isinstance(arg, Number):
            kind = 'float'
        elif isinstance(arg, NamedQubit):
            kind = 'qubit'
        else:
            raise TypeError("Unrecognized argument type to gate")
        return Parameter(name, kind)
