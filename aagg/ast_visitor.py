import clingo
from tree_data import TreeData
from predicate import Predicate
from ast_wrappers.conditional_literal import ConditionalLiteral
from ast_wrappers.definition import Definition
from ast_wrappers.show_signature import ShowSignature


class ASTVisitor(object):

    def visit(self, x, data=TreeData()):
        if isinstance(x, clingo.ast.AST):
            attr = "visit_" + str(x.type)
            if hasattr(self, attr):
                return getattr(self, attr)(x, data)
            else:
                after = self.visit_children(x, data)
                return after
        elif isinstance(x, list):
            return [self.visit(y, data) for y in x]
        elif x is None:
            return x
        else:
            raise TypeError("unexpected type (%s)" % type(x))

    def visit_children(self, x, data=TreeData()):
        for key in x.child_keys:
            child_x = self.visit(getattr(x, key), data)
            x[key] = child_x
        return x


class ASTReplacer(ASTVisitor):
    """
        Some AST objects have string representations which do not
            match the Gringo syntax for that object. We can define
            our own AST objects identical to the original, with an
            overridden __str__ method.
        This visits the AST, replacing all encountered AST objects with
            custom-defined AST objects where appropriate

    """

    def replace(self, stm):
        return super(ASTReplacer, self).visit(stm)

    # Must be named with capital letter to match the class name
    # noinspection PyPep8Naming
    def visit_ConditionalLiteral(self, conditional_literal, data=TreeData()):
        fixed_conditional_literal = ConditionalLiteral(conditional_literal)
        return super(ASTReplacer, self).visit_children(fixed_conditional_literal, data)

    # noinspection PyPep8Naming
    def visit_Definition(self, definition, data=TreeData()):
        fixed_definition = Definition(definition)
        return super(ASTReplacer, self).visit_children(fixed_definition, data)

    # noinspection PyPep8Naming
    def visit_ShowSignature(self, show_signature, data=TreeData()):
        fixed_show_signature = ShowSignature(show_signature)
        return super(ASTReplacer, self).visit_children(fixed_show_signature, data)


def pool_and_arg_hash(pool, arg):
    """
        Helper function for the ASTPoolInstantiator class
        Given a pool and one if its arguments,
        Returns a string value of the form:
            "pool_location - argument_list - argument"
    """
    return "Pool+Arg Hash:  L%sC%s-%s-%s" % \
           (pool['location']['begin']['line'], pool['location']['begin']['column'], pool['arguments'], arg)


class ASTPoolInstantiator(ASTVisitor):
    """
        AST tree visitor class for recursively instantiating
            a rule containing a pool into multiple rules
            containing no pools
    """

    def __init__(self):
        self.stm = None
        self.instantiations = None
        self.operational_pool_hash = None
        self.astCopier = ASTCopier()
        self.astPoolInstantiator = None

    def instantiate_pools(self, stm):
        """
            Given a statement, possibly containing pool objects.
            Resets the class' values because no data needs to be
                kept for different rule instantiations; this allows
                this class to be constructed once and only once.
            Visits the rule recursively using the ASTVisitor.
            When a Pool object is first encountered, this adds the
                result of visit(stm) to a list of instantiations, where
                we visit the statement with a flag indicating which
                argument in the encountered rule we are expanding.
                The pool is eliminated for each argument, and only the
                result of visit(that argument) is returned put in
                place of the pool.
            Then recursively call the ASTPoolInstantiator on each
                instantiation of that pool, in order to instantiate
                other pools in the rule (if any exist)
            Returns the list of pool instantiations
        """
        self.stm = stm
        self.instantiations = []
        self.operational_pool_hash = None

        stm = super(ASTPoolInstantiator, self).visit(self.stm)
        if len(self.instantiations) > 0:
            return self.instantiations
        else:
            return [stm]

    # noinspection PyPep8Naming
    def visit_Pool(self, pool, data=TreeData()):
        if self.operational_pool_hash is None:
            # Encountered a pool while we are not actively replacing a pool with a specific one of its arguments

            instantiations = []
            for arg in pool['arguments']:
                # Store a flag (string hash) of the argument we wish to use to replace its parent pool;
                # Add a rule with that argument in place of its parent pool to a list of instantiations
                self.operational_pool_hash = pool_and_arg_hash(pool, arg)
                instantiations.append(super(ASTPoolInstantiator, self).visit(self.astCopier.deep_copy(self.stm)))

            # Class-recursive part; instantiate all instantiations, in case multiple pools exist within the rule
            self.astPoolInstantiator = ASTPoolInstantiator()
            for instantiation in instantiations:
                for instantiation_instantiation in self.astPoolInstantiator.instantiate_pools(instantiation):
                    self.instantiations.append(instantiation_instantiation)
        else:
            # Encountered a pool while we are actively replacing a pool with a specific one of its arguments
            #   If this is that specific pool, replace it with its visited argument
            #   Otherwise, visit the pool's children as normal
            for arg in pool['arguments']:
                if self.operational_pool_hash == pool_and_arg_hash(pool, arg):
                    return super(ASTPoolInstantiator, self).visit(arg, data)

            return super(ASTPoolInstantiator, self).visit_children(pool, data)


class ASTCopier(ASTVisitor):

    def deep_copy(self, ast):
        return self.visit(ast)

    def visit(self, x, data=TreeData()):  # 'data' needed in arguments list so ASTVisitor will call this visit
        if isinstance(x, clingo.ast.AST):
            x = clingo.ast.AST(x.type, **dict(x))
            return super(ASTCopier, self).visit(x, data)
        else:
            return super(ASTCopier, self).visit(x, data)


class ASTPredicateMapper(ASTVisitor):
    """
        Want to create an adjacency list where we have an edge from 
         x to y if x is in the head of a rule in which y is in the body.
        Thus we obtain a map
                {x : (y,z)}            (note: (y,z) is a set of y and z)
         after observing a rule 'x :- y, z.' where y and z may be
         preceded by 'not'
    """

    def __init__(self):
        self.predicate_map = {}
        self.head_predicates = set()
        self.body_predicates = set()

    def clear_map(self):
        self.predicate_map = {}

    def map_rule_predicates(self, rule):
        """
            Finds all predicates in the head and the body and constructs
             a predicate map (a.k.a. and adjacency list) according to 
             the above description
            Must be given a rule at the top-level, where child keys 
             are ["head", "body"]
            Otherwise performs no operations
        """
        if isinstance(rule, clingo.ast.AST) and rule.type == clingo.ast.ASTType.Rule:
            # Reset head and body predicate lists such that this class 
            #  may be reused for all rules in the program
            self.head_predicates = set()
            self.body_predicates = set()

            super(ASTPredicateMapper, self).visit(rule["head"], TreeData(head=True))
            super(ASTPredicateMapper, self).visit(rule["body"], TreeData(head=False))

            for head_predicate in self.head_predicates:

                if head_predicate not in self.predicate_map.keys():
                    self.predicate_map[head_predicate] = set()

                self.predicate_map[head_predicate].update(self.body_predicates)

    # Must be named with capital letter to match the class name
    # noinspection PyPep8Naming
    def visit_ConditionalLiteral(self, conditional_literal, data=TreeData()):
        """
            If we encounter a conditional literal in the head, we are 
                within either an Aggregate, Head Aggregate, or a Disjoint.
            In all cases, we have a conditional literal of the form
                            literal : conditions
                    where conditions are a set of literals.
            We want predicates in the literal to be marked as in the head,
                and predicates in the conditions to be marked as in the
                body.
        """
        if data.head:
            conditional_literal['literal'] = super(ASTPredicateMapper, self).visit(conditional_literal['literal'], data)
            conditional_literal['condition'] = super(ASTPredicateMapper, self).visit(conditional_literal['condition'],
                                                                                     TreeData(head=False))
            return conditional_literal
        else:
            return super(ASTPredicateMapper, self).visit_children(conditional_literal, data)

    # Must be named with capital letter to match the class name
    # noinspection PyPep8Naming
    def visit_Function(self, function, data=TreeData()):
        predicate = Predicate(function['name'], len(function['arguments']))
        if data.head:
            self.head_predicates.add(predicate)
        else:
            self.body_predicates.add(predicate)

        return super(ASTPredicateMapper, self).visit_children(function, data)
