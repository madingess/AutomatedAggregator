import clingo


class Definition(clingo.ast.AST):
    """
        Custom clingo AST Definition object definition to correct
            errors when outputting constant definitions
            using their __str__ method
    """

    def __init__(self, definition):
        self.type = definition.type
        self.child_keys = definition.child_keys
        self.location = definition.location
        self.name = definition.name
        self.value = definition.value
        self.is_default = definition.is_default

    def __str__(self):
        """
            Do not print the appended '[Default]' for definitions
                when the is_default value is true
        """
        return "#const %s = %s." % (self.name, str(self.value))
