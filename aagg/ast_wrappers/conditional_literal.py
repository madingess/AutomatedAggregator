import clingo


class ConditionalLiteral(clingo.ast.AST):
    """
        Custom clingo AST ConditionalLiteral definition to correct
            errors when outputting conditional literal objects
            using their __str__ method
    """

    def __init__(self, conditional_literal):
        self.type = conditional_literal.type
        self.child_keys = conditional_literal.child_keys
        self.location = conditional_literal.location
        self.literal = conditional_literal.literal
        self.condition = conditional_literal.condition

    def __str__(self):
        """
            When no conditions are present, simply print
                            'literal'
                instead of
                            'literal : '
        """
        if len(self.condition) == 0:
            return "%s" % self.literal

        else:
            condition_strings = ["%s" % condition_atom for condition_atom in self.condition]
            separator = ", "
            return "%s : %s" % (self.literal, separator.join(condition_strings))
