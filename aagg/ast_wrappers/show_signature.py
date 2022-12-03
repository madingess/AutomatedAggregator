import clingo


class ShowSignature(clingo.ast.AST):
    """
        Custom clingo AST show signature  definition
            to correct errors when outputting show
            directives using their __str__ method
    """

    def __init__(self, show_signature):
        self.type = show_signature.type
        self.child_keys = show_signature.child_keys
        self.location = show_signature.location
        self.name = show_signature.name
        self.arity = show_signature.arity
        self.csp = show_signature.csp

    def __str__(self):
        """
            When we encounter a show signature with no XXX
                given, we desire to print
                        #show.
                instead of
                        #show /0.
        """
        if self.name == '':
            return '#show.'
        else:
            return "#show %s/%s." % (self.name, str(self.arity))
